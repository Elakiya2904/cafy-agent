import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as auth from "./auth.js";

const json = (body, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

const sessionBody = (token, email = "ada@example.com") => ({
  access_token: token, token_type: "bearer", expires_in: 900, user: { id: "u1", email, full_name: "Ada" },
});

let fetchMock;

beforeEach(() => {
  vi.useFakeTimers();
  auth.__resetAuthForTests();
  // Unless a test queues a response, only the (guest-less) config lookup is answered; anything else fails loudly.
  fetchMock = vi.fn((url) => String(url).endsWith("/api/auth/config")
    ? Promise.resolve(json({ guest_mode: false }))
    : Promise.reject(new TypeError(`unexpected request: ${url}`)));
  window.fetch = fetchMock;
  auth.installAuthFetch();
});

afterEach(() => {
  vi.useRealTimers();
});

const authCalls = (path) => fetchMock.mock.calls.filter(([url]) => String(url).endsWith(path));

describe("session restore", () => {
  it("restores a session from the refresh cookie and announces it", async () => {
    fetchMock.mockResolvedValueOnce(json(sessionBody("t1")));
    const seen = [];
    auth.trackSession((s) => seen.push(s?.user.email ?? null));
    await vi.advanceTimersByTimeAsync(0);

    expect(seen).toEqual(["ada@example.com"]);
    expect(auth.getAccessToken()).toBe("t1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/refresh");
    expect(init.credentials).toBe("same-origin");
    expect(init.headers["X-Cafy-Client"]).toBe("web");
  });

  it("announces signed-out when there is no session", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "Sign in required." }, 401));
    const seen = [];
    auth.trackSession((s) => seen.push(s));
    await vi.advanceTimersByTimeAsync(0);
    expect(seen).toEqual([null]);
    expect(auth.getAccessToken()).toBeNull();
  });

  it("makes one refresh request however many subscribers there are", async () => {
    fetchMock.mockResolvedValue(json(sessionBody("t1")));
    auth.trackSession(() => {});
    auth.trackSession(() => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(authCalls("/api/auth/refresh")).toHaveLength(1);
  });

  it("keeps the session when the network drops during a renewal", async () => {
    fetchMock.mockResolvedValueOnce(json(sessionBody("t1")));
    auth.trackSession(() => {});
    await vi.advanceTimersByTimeAsync(0);

    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    await vi.advanceTimersByTimeAsync(900_000 - 60_000);
    expect(auth.getAccessToken()).toBe("t1");
  });
});

describe("guest login", () => {
  const configResponse = (allowed) => json({ guest_mode: allowed });

  it("is offered only when the server says so", async () => {
    fetchMock.mockImplementation((url) => Promise.resolve(
      String(url).endsWith("/config") ? configResponse(true) : json({ detail: "Sign in required." }, 401)));
    auth.trackSession(() => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(auth.isGuestAvailable()).toBe(true);
  });

  it("is not offered when the server says no, or cannot be reached", async () => {
    fetchMock.mockImplementation((url) => Promise.resolve(
      String(url).endsWith("/config") ? configResponse(false) : json({ detail: "Sign in required." }, 401)));
    auth.trackSession(() => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(auth.isGuestAvailable()).toBe(false);

    auth.__resetAuthForTests();
    window.fetch = fetchMock.mockImplementation(() => Promise.reject(new TypeError("offline")));
    auth.installAuthFetch();
    auth.trackSession(() => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(auth.isGuestAvailable()).toBe(false);
  });

  it("sends the guest header without a session, and never when guests are not allowed", async () => {
    auth.__setGuestAvailableForTests(true);
    auth.setGuestMode(true);
    fetchMock.mockResolvedValue(json({}));
    await window.fetch("/api/jobs");
    expect(new Headers(fetchMock.mock.calls.at(-1)[1].headers).get("X-Cafy-Guest")).toBe("true");

    auth.__setGuestAvailableForTests(false);
    await window.fetch("/api/jobs");
    expect(new Headers(fetchMock.mock.calls.at(-1)[1].headers).get("X-Cafy-Guest")).toBeNull();
  });
});

describe("sign in / out", () => {
  it("signs in, stores the token in memory only and renews before expiry", async () => {
    fetchMock.mockResolvedValueOnce(json(sessionBody("t1")));
    await auth.signIn({ email: "ada@example.com", password: "pw" });
    expect(auth.getAccessToken()).toBe("t1");
    expect(JSON.stringify({ ...localStorage })).not.toContain("t1");
    expect(JSON.stringify({ ...sessionStorage })).not.toContain("t1");

    fetchMock.mockResolvedValueOnce(json(sessionBody("t2")));
    await vi.advanceTimersByTimeAsync(900_000 - 60_000);
    expect(auth.getAccessToken()).toBe("t2");
  });

  it("surfaces the server's message on a failed sign-in", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "Incorrect email or password." }, 401));
    await expect(auth.signIn({ email: "a@b.co", password: "x" })).rejects.toMatchObject({
      message: "Incorrect email or password.", status: 401,
    });
    expect(auth.getAccessToken()).toBeNull();
  });

  it("reports Retry-After for throttled attempts", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "Too many failed attempts. Try again later." }, 429, { "Retry-After": "300" }));
    await expect(auth.signIn({ email: "a@b.co", password: "x" })).rejects.toMatchObject({ status: 429, retryAfter: 300 });
  });

  it("turns a network failure into a readable error", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(auth.signIn({ email: "a@b.co", password: "x" })).rejects.toThrow(/Unable to reach the server/);
  });

  it("signs out locally even if the server call fails", async () => {
    fetchMock.mockResolvedValueOnce(json(sessionBody("t1")));
    await auth.signIn({ email: "a@b.co", password: "x" });
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    const seen = [];
    auth.trackSession((s) => seen.push(s));
    await auth.signOut();
    expect(auth.getAccessToken()).toBeNull();
    expect(seen.at(-1)).toBeNull();
  });
});

describe("API requests", () => {
  beforeEach(async () => {
    fetchMock.mockResolvedValueOnce(json(sessionBody("t1")));
    await auth.signIn({ email: "ada@example.com", password: "pw" });
    fetchMock.mockReset();
  });

  it("adds the bearer token to this app's API calls", async () => {
    fetchMock.mockResolvedValueOnce(json({ ok: true }));
    await window.fetch("/api/jobs");
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("Authorization")).toBe("Bearer t1");
  });

  it("never sends the token to another origin, even for /api/ paths", async () => {
    fetchMock.mockResolvedValueOnce(json({}));
    await window.fetch("https://third-party.example/api/data");
    expect(fetchMock.mock.calls[0][1]).toBeUndefined();
  });

  it("refreshes once and retries when the server answers 401", async () => {
    fetchMock
      .mockResolvedValueOnce(json({ detail: "Session expired." }, 401))
      .mockResolvedValueOnce(json(sessionBody("t2")))
      .mockResolvedValueOnce(json({ jobs: [] }));
    const response = await window.fetch("/api/jobs");

    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls.map(([u]) => u)).toEqual(["/api/jobs", "/api/auth/refresh", "/api/jobs"]);
    expect(new Headers(fetchMock.mock.calls[2][1].headers).get("Authorization")).toBe("Bearer t2");
  });

  it("signs the user out when the refresh is rejected", async () => {
    const seen = [];
    auth.trackSession((s) => seen.push(s));
    fetchMock
      .mockResolvedValueOnce(json({ detail: "Session expired." }, 401))
      .mockResolvedValueOnce(json({ detail: "Session expired." }, 401));
    const response = await window.fetch("/api/jobs");

    expect(response.status).toBe(401);
    expect(auth.getAccessToken()).toBeNull();
    expect(seen.at(-1)).toBeNull();
  });

  it("does not loop on the auth endpoints themselves", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "nope" }, 401));
    await window.fetch("/api/auth/login", { method: "POST" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("appends the token to file-download links", () => {
    expect(auth.withToken("/api/export")).toBe("/api/export?access_token=t1");
    expect(auth.withToken("/api/x?a=1")).toBe("/api/x?a=1&access_token=t1");
  });
});

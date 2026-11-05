import { afterEach, describe, expect, it, vi } from "vitest";

describe("guest API authentication", () => {
  afterEach(() => {
    window.fetch = originalFetch;
    delete window.__cafyAuthFetch;
    window.sessionStorage.clear();
    vi.resetModules();
  });

  const originalFetch = window.fetch;

  it("requests a signed guest token and sends it to protected APIs", async () => {
    const fetchMock = vi.fn(async (input, init) => {
      if (input === "/api/auth/guest") {
        return { ok: true, status: 200, json: async () => ({ access_token: "signed-guest-token" }) };
      }
      return { ok: true, status: 200, input, init };
    });
    window.fetch = fetchMock;
    window.sessionStorage.clear();
    delete window.__cafyAuthFetch;
    vi.resetModules();

    const { installAuthFetch, setGuestMode } = await import("./auth.js");
    setGuestMode(true);
    installAuthFetch();

    await window.fetch("/api/resume/current");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/guest");
    expect(new Headers(fetchMock.mock.calls[1][1].headers).get("Authorization"))
      .toBe("Bearer signed-guest-token");
  });
});

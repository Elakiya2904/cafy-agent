// Browser session for Cafy's own account system (see backend/auth_api.py).
//
// * The short-lived access token lives only in memory; it is never written to localStorage.
// * The refresh token is an HttpOnly cookie the browser sends to /api/auth/* by itself, so no script can read it.
// * On load the app asks /api/auth/refresh for a session, renews it shortly before it expires, and retries a
//   request once when the server answers 401.

const AUTH_PATH = "/api/auth"; // same-origin on purpose (Vite proxies /api in development) so the cookie is first-party
const CLIENT_HEADER = { "X-Cafy-Client": "web" };
const RENEW_BEFORE_EXPIRY_MS = 60_000;
const MIN_RENEW_DELAY_MS = 5_000;
const GUEST_KEY = "cafy_guest_mode";
// A guest's signed token is kept for this browser tab only, so reloading does not start a new, empty guest account.
const GUEST_SESSION_KEY = "cafy_guest_session";
// In development the pages are served by Vite but API calls go straight to the backend.
const DEV_API_ORIGIN = "http://127.0.0.1:8000";

export class AuthApiError extends Error {
  constructor(message, status = 0, retryAfter = 0) {
    super(message);
    this.name = "AuthApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

let session = null; // { accessToken, expiresAt, user }
let bootstrapped = false;
let renewTimer = null;
let refreshInFlight = null;
let originalFetch = null;
let guestActive = readGuestFlag();
let guestAvailable = false; // the server decides (GET /api/auth/config); testing only, never in production
const listeners = new Set();

function readGuestFlag() {
  try {
    return typeof window !== "undefined" && window.sessionStorage?.getItem(GUEST_KEY) === "true";
  } catch {
    return false;
  }
}

const rawFetch = (...args) => (originalFetch || globalThis.fetch)(...args);
const publicSession = () => (session ? { user: session.user, expiresAt: session.expiresAt } : null);
const notify = () => listeners.forEach((listener) => listener(publicSession()));

export const getAccessToken = () => session?.accessToken || null;
export const getCurrentUser = () => session?.user || null;
export const isGuestAvailable = () => guestAvailable;
export const isGuestMode = () => guestAvailable && guestActive;

export function setGuestMode(enabled) {
  guestActive = guestAvailable && Boolean(enabled);
  try {
    if (guestActive) window.sessionStorage?.setItem(GUEST_KEY, "true");
    else window.sessionStorage?.removeItem(GUEST_KEY);
  } catch {
    /* storage unavailable (private mode): guest state simply lasts for this page view */
  }
}

/** For file previews/downloads opened in a new tab, which cannot send an Authorization header. */
export function withToken(path) {
  const token = getAccessToken();
  if (!token) return path;
  return `${path}${path.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(token)}`;
}

// ------------------------------------------------------------------ talking to /api/auth
function friendlyMessage(status, detail) {
  if (typeof detail === "string" && detail) return detail;
  if (status === 422) return "Check the details you entered and try again.";
  if (status === 429) return "Too many attempts. Please wait a few minutes and try again.";
  return "Something went wrong. Please try again.";
}

async function authRequest(path, body) {
  let response;
  try {
    response = await rawFetch(`${AUTH_PATH}${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...CLIENT_HEADER },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new AuthApiError("Unable to reach the server. Check your connection and try again.");
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new AuthApiError(friendlyMessage(response.status, data?.detail), response.status, Number(response.headers.get("Retry-After")) || 0);
  }
  return data;
}

/** Ask the server whether guest login is offered. Any failure simply means "not offered". */
async function loadConfig() {
  try {
    const response = await rawFetch(`${AUTH_PATH}/config`, { credentials: "same-origin" });
    guestAvailable = response.ok && Boolean((await response.json())?.guest_mode);
  } catch {
    guestAvailable = false;
  }
}

function applySession(payload) {
  session = {
    accessToken: payload.access_token,
    expiresAt: Date.now() + payload.expires_in * 1000,
    user: payload.user,
  };
  saveGuestSession(session.user?.guest ? session : null);
  bootstrapped = true; // we now know the session state; no need to probe the refresh cookie again
  scheduleRenewal();
  notify();
}

function clearSession() {
  clearTimeout(renewTimer);
  renewTimer = null;
  saveGuestSession(null);
  if (!session) return;
  session = null;
  notify();
}

function saveGuestSession(value) {
  try {
    if (value) window.sessionStorage?.setItem(GUEST_SESSION_KEY, JSON.stringify(value));
    else window.sessionStorage?.removeItem(GUEST_SESSION_KEY);
  } catch {
    /* storage unavailable: the guest session lasts for this page view only */
  }
}

function readGuestSession() {
  try {
    const saved = JSON.parse(window.sessionStorage?.getItem(GUEST_SESSION_KEY) || "null");
    return saved?.accessToken && saved.user?.guest && saved.expiresAt > Date.now() + RENEW_BEFORE_EXPIRY_MS ? saved : null;
  } catch {
    return null;
  }
}

function scheduleRenewal() {
  clearTimeout(renewTimer);
  if (!session) return;
  if (session.user?.guest) {
    // Guest tokens cannot be refreshed; the guest session simply ends when the token expires.
    renewTimer = setTimeout(clearSession, Math.max(0, session.expiresAt - Date.now()));
    return;
  }
  const delay = Math.max(MIN_RENEW_DELAY_MS, session.expiresAt - Date.now() - RENEW_BEFORE_EXPIRY_MS);
  renewTimer = setTimeout(() => { refreshSession(); }, delay);
}

/** Exchange the refresh cookie for a new session. One request at a time, however many callers ask. */
export function refreshSession() {
  if (!refreshInFlight) {
    refreshInFlight = authRequest("/refresh")
      .then((payload) => {
        applySession(payload);
        return true;
      })
      .catch((error) => {
        // Only a definitive rejection ends the session; a network blip keeps it so the user can retry.
        if (error.status === 400 || error.status === 401) clearSession();
        else if (session) scheduleRetry();
        return false;
      })
      .finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

function scheduleRetry() {
  clearTimeout(renewTimer);
  renewTimer = setTimeout(() => { refreshSession(); }, MIN_RENEW_DELAY_MS * 3);
}

export async function signUp({ fullName, email, password }) {
  applySession(await authRequest("/signup", { full_name: fullName, email, password }));
  setGuestMode(false);
}

export async function signIn({ email, password }) {
  applySession(await authRequest("/login", { email, password }));
  setGuestMode(false);
}

/** Start a temporary guest account of your own (no email or password). The server must offer guest access. */
export async function signInAsGuest() {
  const payload = await authRequest("/guest");
  applySession({
    ...payload,
    expires_in: Number(payload?.expires_in) || 12 * 60 * 60,
    user: { ...(payload?.user || {}), guest: true },
  });
  setGuestMode(false);
}

export async function signOut() {
  try {
    await authRequest("/logout");
  } catch {
    /* the cookie expires on its own; the local session is cleared regardless */
  }
  setGuestMode(false);
  clearSession();
}

/** Subscribe to session changes. The first call restores a session from the refresh cookie, if there is one. */
export function trackSession(onChange) {
  listeners.add(onChange);
  if (bootstrapped) {
    onChange(publicSession());
  } else if (!refreshInFlight) {
    const savedGuest = readGuestSession();
    const restore = savedGuest
      ? Promise.resolve().then(() => {
        session = savedGuest;
        scheduleRenewal();
        notify();
        return true;
      })
      : refreshSession();
    Promise.all([restore, loadConfig()]).finally(() => {
      bootstrapped = true;
      // refreshSession already notified on success; on failure there was no session, so announce "signed out".
      if (!session) listeners.forEach((listener) => listener(null));
    });
  }
  return () => listeners.delete(onChange);
}

// ------------------------------------------------------------------ attach the token to API calls
function isApiRequest(url) {
  try {
    const target = new URL(url, window.location.href);
    const sameApp = target.origin === window.location.origin || target.origin === DEV_API_ORIGIN;
    return sameApp && target.pathname.startsWith("/api/") && !target.pathname.startsWith(`${AUTH_PATH}/`);
  } catch {
    return false;
  }
}

function withAuthHeaders(headers) {
  const merged = new Headers(headers);
  if (merged.has("Authorization")) return merged;
  if (session) merged.set("Authorization", `Bearer ${session.accessToken}`);
  else if (isGuestMode()) merged.set("X-Cafy-Guest", "true");
  return merged;
}

/** Attach the signed-in user's token to calls to this app's API only (never to other origins). */
export function installAuthFetch() {
  if (originalFetch || typeof window === "undefined") return;
  originalFetch = window.fetch.bind(window);

  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input?.url || "";
    if (!isApiRequest(url)) return originalFetch(input, init);

    const attempt = () => {
      if (input instanceof Request) {
        const copy = input.clone();
        return originalFetch(new Request(copy, { headers: withAuthHeaders(copy.headers) }));
      }
      return originalFetch(input, { ...init, headers: withAuthHeaders(init?.headers) });
    };

    const hadToken = Boolean(session);
    let response = await attempt();
    if (response.status === 401 && hadToken) {
      if (session?.user?.guest) clearSession(); // an expired or rejected guest token cannot be refreshed
      else if (await refreshSession()) response = await attempt();
    }
    return response;
  };

  document.addEventListener("visibilitychange", () => {
    // Timers are throttled in background tabs, so renew on return if the token ran out meanwhile.
    if (document.visibilityState === "visible" && session && session.expiresAt - Date.now() < RENEW_BEFORE_EXPIRY_MS) {
      refreshSession();
    }
  });
}

/** Test hook: pretend the server does (not) offer guest login. */
export function __setGuestAvailableForTests(value) {
  guestAvailable = value;
}

/** Test hook: forget all module state. */
export function __resetAuthForTests() {
  clearTimeout(renewTimer);
  session = null;
  bootstrapped = false;
  renewTimer = null;
  refreshInFlight = null;
  originalFetch = null;
  guestActive = false;
  guestAvailable = false;
  listeners.clear();
}

export const authEnabled = true;
export const guestModeEnabled = authEnabled && import.meta.env.VITE_ENABLE_GUEST_MODE !== "false";

let accessToken = null;
let refreshToken = null;
const listeners = new Set();
let guestModeActive = typeof window !== 'undefined' && window.sessionStorage?.getItem('cafy_guest_mode') === 'true';
export const getAccessToken = () => accessToken;

const customStorageKey = "cafy_custom_session";
const guestTokenStorageKey = "cafy_guest_access_token";
let guestTokenRequest = null;

function readCustomSession() {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(window.localStorage?.getItem(customStorageKey) || "null");
  } catch {
    return null;
  }
}

function saveCustomSession(session) {
  accessToken = session?.access_token || null;
  refreshToken = session?.refresh_token || null;
  if (typeof window !== "undefined") {
    if (session) window.localStorage?.setItem(customStorageKey, JSON.stringify(session));
    else window.localStorage?.removeItem(customStorageKey);
  }
}

async function customRequest(path, body) {
  const response = await window.fetch(`/api/auth/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) return { data: null, error: { message: data.detail || "Authentication request failed." } };
  return { data, error: null };
}

function customUser(session) {
  return session?.user || null;
}

export const auth = {
  async getSession() {
    const session = readCustomSession();
    saveCustomSession(session);
    return { data: { session } };
  },
  async getUser() {
    return { data: { user: customUser(readCustomSession()) } };
  },
  async signUp({ email, password, options }) {
    const result = await customRequest("register", {
      email,
      password,
      full_name: options?.data?.full_name || "",
    });
    if (result.error) return result;
    saveCustomSession(result.data);
    listeners.forEach((listener) => listener("SIGNED_IN", result.data));
    return { data: { session: result.data, user: result.data.user }, error: null };
  },
  async signInWithPassword({ email, password }) {
    const result = await customRequest("login", { email, password });
    if (result.error) return result;
    saveCustomSession(result.data);
    listeners.forEach((listener) => listener("SIGNED_IN", result.data));
    return { data: { session: result.data, user: result.data.user }, error: null };
  },
  async resetPasswordForEmail() {
    return { error: { message: "Password reset is not configured on this server yet." } };
  },
  async signOut() {
    if (refreshToken) await customRequest("logout", { refresh_token: refreshToken });
    saveCustomSession(null);
    listeners.forEach((listener) => listener("SIGNED_OUT", null));
  },
  onAuthStateChange(listener) {
    listeners.add(listener);
    return { data: { subscription: { unsubscribe: () => listeners.delete(listener) } } };
  },
};

export function getCurrentUser() {
  return customUser(readCustomSession());
}

export function setGuestMode(enabled) {
  guestModeActive = guestModeEnabled && enabled;
  if (typeof window !== 'undefined') {
    if (guestModeActive) {
      window.sessionStorage?.setItem('cafy_guest_mode', 'true');
    } else {
      window.sessionStorage?.removeItem('cafy_guest_mode');
      window.sessionStorage?.removeItem(guestTokenStorageKey);
    }
  }
}

async function getGuestAccessToken(originalFetch) {
  const cached = window.sessionStorage?.getItem(guestTokenStorageKey);
  if (cached) return cached;
  if (!guestTokenRequest) {
    guestTokenRequest = originalFetch("/api/auth/guest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.access_token) {
          throw new Error(data.detail || "Could not start temporary guest access.");
        }
        window.sessionStorage?.setItem(guestTokenStorageKey, data.access_token);
        return data.access_token;
      })
      .finally(() => {
        guestTokenRequest = null;
      });
  }
  return guestTokenRequest;
}

/** For file previews/downloads opened in a new tab, which cannot send an Authorization header. */
export function withToken(path) {
  const token = accessToken || (guestModeActive && window.sessionStorage?.getItem(guestTokenStorageKey));
  if (!authEnabled || !token) return path;
  return `${path}${path.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(token)}`;
}

export function trackSession(onChange) {
  auth.getSession().then(({ data }) => {
    saveCustomSession(data.session);
    onChange(data.session);
  });
  const { data } = auth.onAuthStateChange((_event, session) => {
    saveCustomSession(session);
    onChange(session);
  });
  return () => data.subscription.unsubscribe();
}

/** Attach the signed-in user's token to every call to this app's API. */
export function installAuthFetch() {
  if (!authEnabled || window.__cafyAuthFetch) return;
  window.__cafyAuthFetch = true;
  const original = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const target = typeof input === "string" ? input : input?.url || "";
    if (!target.includes("/api/")) return original(input, init);
    const headers = new Headers(init.headers || (typeof input !== "string" ? input.headers : undefined));
    if (accessToken && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    } else if (guestModeActive && !headers.has("Authorization")) {
      const token = await getGuestAccessToken(original);
      headers.set("Authorization", `Bearer ${token}`);
    } else if (!accessToken) {
      return original(input, init);
    }
    const response = await original(input, { ...init, headers });
    if (response.status === 401 && guestModeActive && !accessToken) {
      window.sessionStorage?.removeItem(guestTokenStorageKey);
    }
    if (response.status === 401 && accessToken) auth.signOut();  // expired or revoked session
    return response;
  };
}

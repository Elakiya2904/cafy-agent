import { createClient } from "@supabase/supabase-js";

// Public values by design (the anon key only works together with Row Level Security / the backend's own checks).
const url = import.meta.env.VITE_SUPABASE_URL || "https://tgeuiemybetiiwblhdbr.supabase.co";
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || "sb_publishable_PlCIZydM_pmkafPXKCWliA_RegTigST";

export const authEnabled = Boolean(url && anonKey);
export const guestModeEnabled = authEnabled && import.meta.env.VITE_ENABLE_GUEST_MODE !== "false";
export const supabase = authEnabled ? createClient(url, anonKey) : null;

let accessToken = null;
let guestModeActive = typeof window !== 'undefined' && window.sessionStorage?.getItem('cafy_guest_mode') === 'true';
export const getAccessToken = () => accessToken;

export function setGuestMode(enabled) {
  guestModeActive = guestModeEnabled && enabled;
  if (typeof window !== 'undefined') {
    if (guestModeActive) {
      window.sessionStorage?.setItem('cafy_guest_mode', 'true');
    } else {
      window.sessionStorage?.removeItem('cafy_guest_mode');
    }
  }
}

/** For file previews/downloads opened in a new tab, which cannot send an Authorization header. */
export function withToken(path) {
  if (!authEnabled || !accessToken) return path;
  return `${path}${path.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(accessToken)}`;
}

export function trackSession(onChange) {
  if (!supabase) return () => {};
  supabase.auth.getSession().then(({ data }) => {
    accessToken = data.session?.access_token || null;
    onChange(data.session);
  });
  const { data } = supabase.auth.onAuthStateChange((_event, session) => {
    accessToken = session?.access_token || null;
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
      headers.set("X-Cafy-Guest", "true");
    } else if (!accessToken) {
      return original(input, init);
    }
    const response = await original(input, { ...init, headers });
    if (response.status === 401 && supabase) supabase.auth.signOut();  // expired or revoked session
    return response;
  };
}

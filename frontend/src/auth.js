import { createClient } from "@supabase/supabase-js";

// Public values by design (the anon key only works together with Row Level Security / the backend's own checks).
const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const authEnabled = Boolean(url && anonKey);
export const supabase = authEnabled ? createClient(url, anonKey) : null;

let accessToken = null;
export const getAccessToken = () => accessToken;

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
    if (!target.includes("/api/") || !accessToken) return original(input, init);
    const headers = new Headers(init.headers || (typeof input !== "string" ? input.headers : undefined));
    if (!headers.has("Authorization")) headers.set("Authorization", `Bearer ${accessToken}`);
    const response = await original(input, { ...init, headers });
    if (response.status === 401 && supabase) supabase.auth.signOut();  // expired or revoked session
    return response;
  };
}

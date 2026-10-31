import React, { useEffect, useState } from "react";
import { authEnabled, getAccessToken, installAuthFetch, supabase, trackSession } from "./auth.js";
import "./authGate.css";

installAuthFetch();

function SignIn() {
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    const { data, error } = mode === "signin"
      ? await supabase.auth.signInWithPassword({ email, password })
      : await supabase.auth.signUp({ email, password });
    setBusy(false);
    if (error) setMessage({ kind: "error", text: error.message });
    else if (mode === "signup" && !data.session) setMessage({ kind: "ok", text: "Check your email to confirm your account, then sign in." });
  };

  const reset = async () => {
    if (!email) return setMessage({ kind: "error", text: "Enter your email first." });
    const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
    setMessage(error ? { kind: "error", text: error.message } : { kind: "ok", text: "Password reset email sent." });
  };

  return (
    <div className="ag-wrap">
      <form className="ag-card" onSubmit={submit}>
        <h1>Cafy</h1>
        <p className="ag-sub">{mode === "signin" ? "Sign in to your account" : "Create your account"}</p>
        <label>Email<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label>Password<input type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} required minLength={8}
          value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {message && <div className={`ag-msg ag-${message.kind}`} role="alert">{message.text}</div>}
        <button className="ag-btn" disabled={busy}>{busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Sign up"}</button>
        <div className="ag-links">
          <button type="button" onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setMessage(null); }}>
            {mode === "signin" ? "Create an account" : "I already have an account"}
          </button>
          {mode === "signin" && <button type="button" onClick={reset}>Forgot password?</button>}
        </div>
      </form>
    </div>
  );
}

export default function AuthGate({ children }) {
  const [session, setSession] = useState(undefined);  // undefined = still loading

  useEffect(() => trackSession(setSession), []);

  if (!authEnabled) return children;  // local development without Supabase configured
  if (session === undefined) return <div className="ag-wrap"><p className="ag-sub">Loading…</p></div>;
  if (!session) return <SignIn />;
  return (
    <>
      <div className="ag-bar">
        <span>{session.user.email}</span>
        <button onClick={() => navigator.clipboard?.writeText(getAccessToken() || "")} title="Paste into the extension settings (valid ~1 hour)">Copy extension token</button>
        <button onClick={() => supabase.auth.signOut()}>Sign out</button>
      </div>
      {children}
    </>
  );
}

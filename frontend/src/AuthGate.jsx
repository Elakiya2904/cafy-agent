import React, { useEffect, useState } from "react";
import { Eye, EyeOff, LockKeyhole, Mail, UserRound } from "lucide-react";
import { authEnabled, getAccessToken, guestModeEnabled, installAuthFetch, setGuestMode, supabase, trackSession } from "./auth.js";
import logo from "./logo.png";
import "./authGate.css";

installAuthFetch();

function SignIn({ onGuestMode }) {
  const [mode, setMode] = useState("signup");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const isSignUp = mode === "signup";

  const changeMode = (nextMode) => {
    setMode(nextMode);
    setMessage(null);
  };

  const submit = async (event) => {
    event.preventDefault();
    setMessage(null);

    if (isSignUp && password !== confirmPassword) {
      setMessage({ kind: "error", text: "Passwords do not match." });
      return;
    }

    setBusy(true);
    try {
      const { data, error } = isSignUp
        ? await supabase.auth.signUp({
            email,
            password,
            options: { data: { full_name: fullName.trim() } },
          })
        : await supabase.auth.signInWithPassword({ email, password });

      if (error) {
        setMessage({ kind: "error", text: error.message });
      } else if (isSignUp && !data.session) {
        setMessage({ kind: "ok", text: "Account created. Check your email to confirm it, then sign in." });
      }
    } catch {
      setMessage({ kind: "error", text: "Unable to reach the authentication service. Check your connection and try again." });
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!email) {
      setMessage({ kind: "error", text: "Enter your email address first." });
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
      setMessage(error
        ? { kind: "error", text: error.message }
        : { kind: "ok", text: "Password reset email sent." });
    } catch {
      setMessage({ kind: "error", text: "Unable to send the reset email. Check your connection and try again." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className={`ag-wrap ${isSignUp ? "ag-signup" : "ag-signin"}`}>
      <section className="ag-panel" aria-label={isSignUp ? "Create your Cafy account" : "Sign in to Cafy"}>
        <div className="ag-brand">
          <img src={logo} alt="" />
          <span>{isSignUp ? "Join Us!" : "Welcome Back!"}</span>
        </div>
        <h1>{isSignUp ? "Create Account" : "Welcome Back"}</h1>

        <form className="ag-form" onSubmit={submit}>
          {isSignUp && (
            <label className="ag-field">
              <UserRound aria-hidden="true" />
              <input
                type="text"
                autoComplete="name"
                placeholder="Full Name"
                aria-label="Full name"
                required
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
              />
            </label>
          )}
          <label className="ag-field">
            <Mail aria-hidden="true" />
            <input
              type="email"
              autoComplete="email"
              placeholder="Email Address"
              aria-label="Email address"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label className="ag-field">
            <LockKeyhole aria-hidden="true" />
            <input
              type={showPassword ? "text" : "password"}
              autoComplete={isSignUp ? "new-password" : "current-password"}
              placeholder="Password"
              aria-label="Password"
              required
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <button
              className="ag-reveal"
              type="button"
              aria-label={showPassword ? "Hide password" : "Show password"}
              onClick={() => setShowPassword((visible) => !visible)}
            >
              {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
            </button>
          </label>
          {isSignUp && (
            <label className="ag-field">
              <LockKeyhole aria-hidden="true" />
              <input
                type={showConfirmPassword ? "text" : "password"}
                autoComplete="new-password"
                placeholder="Confirm Password"
                aria-label="Confirm password"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
              <button
                className="ag-reveal"
                type="button"
                aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
                onClick={() => setShowConfirmPassword((visible) => !visible)}
              >
                {showConfirmPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
              </button>
            </label>
          )}

          {message && <div className={`ag-msg ag-${message.kind}`} role="alert">{message.text}</div>}

          <button className="ag-submit" type="submit" disabled={busy}>
            {busy ? "Please wait…" : isSignUp ? "SIGN UP" : "SIGN IN"}
          </button>
          {!isSignUp && (
            <button className="ag-forgot" type="button" onClick={reset} disabled={busy}>
              Forgot password?
            </button>
          )}
        </form>

        {guestModeEnabled && (
          <div className="ag-guest-wrapper">
            <div className="ag-divider">
              <span>or</span>
            </div>
            <button className="ag-guest-btn" type="button" onClick={onGuestMode}>
              <UserRound size={17} aria-hidden="true" />
              <span>Continue as Guest</span>
            </button>
          </div>
        )}

        <p className="ag-switch">
          {isSignUp ? "Already have an account?" : "Don't have an account?"}{" "}
          <button type="button" onClick={() => changeMode(isSignUp ? "signin" : "signup")}>
            {isSignUp ? "Sign In" : "Sign Up"}
          </button>
        </p>
      </section>

      <aside className="ag-welcome">
        <div className="ag-welcome-content">
          <h2>{isSignUp ? "Welcome Back!" : "Join Cafy Agent!"}</h2>
          <p>
            {isSignUp
              ? "To keep connected with us please login with your personal info"
              : "Create an account to find opportunities that fit your skills"}
          </p>
          <button type="button" onClick={() => changeMode(isSignUp ? "signin" : "signup")}>
            {isSignUp ? "SIGN IN" : "SIGN UP"}
          </button>
        </div>
      </aside>
    </main>
  );
}

export default function AuthGate({ children }) {
  const [session, setSession] = useState(undefined);
  const [guestMode, setGuestModeState] = useState(() => {
    if (typeof window !== "undefined") {
      return window.sessionStorage?.getItem("cafy_guest_mode") === "true";
    }
    return false;
  });

  useEffect(() => trackSession((nextSession) => {
    if (nextSession) {
      setGuestMode(false);
      setGuestModeState(false);
    }
    setSession(nextSession);
  }), []);

  if (!authEnabled) return children;
  if (session === undefined) {
    return <div className="ag-loading" role="status">Loading Cafy Agent…</div>;
  }
  if (!session && guestMode) {
    return (
      <React.Fragment key="guest">
        <div className="ag-bar">
          <span>Guest mode — use test data only</span>
          <button
            onClick={() => {
              setGuestMode(false);
              setGuestModeState(false);
            }}
          >
            Sign in
          </button>
        </div>
        {children}
      </React.Fragment>
    );
  }
  if (!session) {
    return (
      <SignIn
        onGuestMode={() => {
          setGuestMode(true);
          setGuestModeState(true);
        }}
      />
    );
  }

  return (
    <React.Fragment key={session.user.id}>
      <div className="ag-bar">
        <span>{session.user.email}</span>
        <button onClick={() => navigator.clipboard?.writeText(getAccessToken() || "")} title="Paste into the extension settings (valid ~1 hour)">Copy extension token</button>
        <button onClick={() => supabase.auth.signOut()}>Sign out</button>
      </div>
      {children}
    </React.Fragment>
  );
}

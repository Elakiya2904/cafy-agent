import React, { useEffect, useState } from "react";
import { Eye, EyeOff, LockKeyhole, Mail, UserRound } from "lucide-react";
import {
  AuthApiError,
  getAccessToken,
  installAuthFetch,
  isGuestAvailable,
  isGuestMode,
  setGuestMode,
  signIn,
  signOut,
  signUp,
  trackSession,
} from "./auth.js";
import logo from "./logo.png";
import "./authGate.css";

installAuthFetch();

const MIN_PASSWORD_LENGTH = 8;
const MAX_PASSWORD_LENGTH = 128;

function PasswordField({ label, placeholder = label, autoComplete, value, onChange, validateLength }) {
  const [visible, setVisible] = useState(false);
  return (
    <label className="ag-field">
      <LockKeyhole aria-hidden="true" />
      <input
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        placeholder={placeholder}
        aria-label={label}
        required
        minLength={validateLength ? MIN_PASSWORD_LENGTH : undefined}
        maxLength={MAX_PASSWORD_LENGTH}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        className="ag-reveal"
        type="button"
        aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
        onClick={() => setVisible((shown) => !shown)}
      >
        {visible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
      </button>
    </label>
  );
}

function describeFailure(error) {
  if (error instanceof AuthApiError && error.status === 429 && error.retryAfter) {
    const minutes = Math.max(1, Math.ceil(error.retryAfter / 60));
    return `Too many failed attempts. Try again in ${minutes} minute${minutes === 1 ? "" : "s"}.`;
  }
  return error instanceof AuthApiError ? error.message : "Something went wrong. Please try again.";
}

function SignIn({ onGuestMode }) {
  const [mode, setMode] = useState("signup");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const isSignUp = mode === "signup";

  const changeMode = (nextMode) => {
    setMode(nextMode);
    setError(null);
    setPassword("");
    setConfirmPassword("");
  };

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setError(null);

    if (isSignUp && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setBusy(true);
    try {
      const credentials = { email: email.trim(), password };
      if (isSignUp) await signUp({ ...credentials, fullName: fullName.trim() });
      else await signIn(credentials);
      // Success: trackSession() reports the new session and AuthGate swaps this screen out.
    } catch (failure) {
      setError(describeFailure(failure));
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
                maxLength={100}
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
              maxLength={320}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <PasswordField
            label="Password"
            autoComplete={isSignUp ? "new-password" : "current-password"}
            value={password}
            onChange={setPassword}
            validateLength={isSignUp}
          />
          {isSignUp && (
            <PasswordField
              label="Confirm password"
              placeholder="Confirm Password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={setConfirmPassword}
              validateLength
            />
          )}

          {error && <div className="ag-msg ag-error" role="alert">{error}</div>}

          <button className="ag-submit" type="submit" disabled={busy}>
            {busy ? "Please wait…" : isSignUp ? "SIGN UP" : "SIGN IN"}
          </button>
        </form>

        {isGuestAvailable() && (
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
  const [session, setSession] = useState(undefined); // undefined = still restoring the session
  const [guestMode, setGuestModeState] = useState(false);

  useEffect(() => trackSession((next) => {
    if (next) setGuestMode(false);
    setGuestModeState(next ? false : isGuestMode()); // a remembered guest session resumes once the server confirms guests are allowed
    setSession(next);
  }), []);

  const updateGuestMode = (enabled) => {
    setGuestMode(enabled);
    setGuestModeState(enabled);
  };

  if (session === undefined) {
    return <div className="ag-loading" role="status">Loading Cafy Agent…</div>;
  }
  if (!session && guestMode) {
    return (
      <React.Fragment key="guest">
        <div className="ag-bar">
          <span>Guest mode — use test data only</span>
          <button onClick={() => updateGuestMode(false)}>Sign in</button>
        </div>
        {children}
      </React.Fragment>
    );
  }
  if (!session) {
    return <SignIn onGuestMode={() => updateGuestMode(true)} />;
  }

  return (
    <React.Fragment key={session.user.id}>
      <div className="ag-bar">
        <span>{session.user.email}</span>
        <button
          onClick={() => navigator.clipboard?.writeText(getAccessToken() || "")}
          title="Paste into the extension settings (valid for about 15 minutes)"
        >
          Copy extension token
        </button>
        <button onClick={signOut}>Sign out</button>
      </div>
      {children}
    </React.Fragment>
  );
}

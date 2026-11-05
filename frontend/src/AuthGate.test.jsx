/**
 * Tests account form switching, session changes, and guest-mode navigation.
 * Uses mocked auth services to verify the gate's visible states and callbacks.
 */
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const authMock = vi.hoisted(() => {
  class AuthApiError extends Error {
    constructor(message, status = 0, retryAfter = 0) {
      super(message);
      this.status = status;
      this.retryAfter = retryAfter;
    }
  }
  return {
    onChange: null, guest: false, setGuestMode: vi.fn(), signIn: vi.fn(), signUp: vi.fn(), signOut: vi.fn(),
    signInAsGuest: vi.fn(), AuthApiError,
  };
});

vi.mock("./auth.js", () => ({
  AuthApiError: authMock.AuthApiError,
  getAccessToken: vi.fn(() => "token"),
  isGuestAvailable: () => true,
  installAuthFetch: vi.fn(),
  isGuestMode: () => authMock.guest,
  setGuestMode: (enabled) => { authMock.guest = enabled; authMock.setGuestMode(enabled); },
  signIn: authMock.signIn,
  signInAsGuest: authMock.signInAsGuest,
  signUp: authMock.signUp,
  signOut: authMock.signOut,
  trackSession: (onChange) => {
    authMock.onChange = onChange;
    onChange(null);
    return vi.fn();
  },
}));

import AuthGate, { SidebarAccount } from "./AuthGate.jsx";

beforeEach(() => {
  authMock.guest = false;
  vi.clearAllMocks();
});
afterEach(cleanup);

function StatefulChild() {
  const [draft, setDraft] = React.useState(0);
  return <button onClick={() => setDraft((value) => value + 1)}>Draft: {draft}</button>;
}

const type = (name, value) => fireEvent.change(screen.getByLabelText(name), { target: { value } });

describe("AuthGate", () => {
  it("reverses the sign-up and sign-in sides from the welcome button", async () => {
    const { container } = render(<AuthGate />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Create Account" })).toBeInTheDocument());
    expect(container.querySelector("main")).toHaveClass("ag-signup");

    fireEvent.click(screen.getByRole("button", { name: "SIGN IN" }));

    expect(screen.getByRole("heading", { name: "Welcome Back" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Join Cafy Agent!" })).toBeInTheDocument();
    expect(container.querySelector("main")).toHaveClass("ag-signin");
    expect(screen.queryByRole("textbox", { name: "Full name" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /forgot/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "SIGN UP" }));

    expect(screen.getByRole("heading", { name: "Create Account" })).toBeInTheDocument();
    expect(container.querySelector("main")).toHaveClass("ag-signup");
  });

  it("creates an account with trimmed values", async () => {
    authMock.signUp.mockResolvedValue();
    render(<AuthGate />);
    await screen.findByRole("heading", { name: "Create Account" });

    type("Full name", "  Ada Lovelace ");
    type("Email address", " ada@example.com ");
    type("Password", "correct-horse-battery");
    type("Confirm password", "correct-horse-battery");
    fireEvent.click(screen.getByRole("button", { name: "SIGN UP" }));

    await waitFor(() => expect(authMock.signUp).toHaveBeenCalledWith({
      fullName: "Ada Lovelace", email: "ada@example.com", password: "correct-horse-battery",
    }));
  });

  it("blocks a sign-up whose passwords differ without calling the server", async () => {
    render(<AuthGate />);
    await screen.findByRole("heading", { name: "Create Account" });

    type("Full name", "Ada");
    type("Email address", "ada@example.com");
    type("Password", "correct-horse-battery");
    type("Confirm password", "something-different");
    fireEvent.click(screen.getByRole("button", { name: "SIGN UP" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(authMock.signUp).not.toHaveBeenCalled();
  });

  it("shows the server's message and re-enables the form when sign-in fails", async () => {
    authMock.signIn.mockRejectedValue(new authMock.AuthApiError("Incorrect email or password.", 401));
    render(<AuthGate />);
    fireEvent.click(await screen.findByRole("button", { name: "SIGN IN" }));

    type("Email address", "ada@example.com");
    type("Password", "wrong-password");
    fireEvent.click(screen.getByRole("button", { name: "SIGN IN" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(screen.getByRole("button", { name: "SIGN IN" })).toBeEnabled();
  });

  it("tells the user how long to wait when throttled", async () => {
    authMock.signIn.mockRejectedValue(new authMock.AuthApiError("Too many failed attempts. Try again later.", 429, 600));
    render(<AuthGate />);
    fireEvent.click(await screen.findByRole("button", { name: "SIGN IN" }));
    type("Email address", "ada@example.com");
    type("Password", "wrong-password");
    fireEvent.click(screen.getByRole("button", { name: "SIGN IN" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 10 minutes.");
  });

  it("clears mounted profile state when the authenticated user changes", async () => {
    render(<AuthGate><StatefulChild /></AuthGate>);
    await waitFor(() => expect(authMock.onChange).toBeInstanceOf(Function));

    act(() => authMock.onChange({ user: { id: "alice", email: "alice@example.com" } }));
    fireEvent.click(await screen.findByRole("button", { name: "Draft: 0" }));
    expect(screen.getByRole("button", { name: "Draft: 1" })).toBeInTheDocument();

    act(() => authMock.onChange({ user: { id: "bob", email: "bob@example.com" } }));

    expect(await screen.findByRole("button", { name: "Logout" })).toBeInTheDocument();
    expect(screen.queryByText("bob@example.com")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Draft: 0" })).toBeInTheDocument();
  });

  it("shows only a logout action in the signed-in account bar", async () => {
    render(<AuthGate><StatefulChild /></AuthGate>);
    await waitFor(() => expect(authMock.onChange).toBeInstanceOf(Function));
    act(() => authMock.onChange({ user: { id: "alice", email: "alice@example.com" } }));

    expect(await screen.findByRole("button", { name: "Logout" })).toBeInTheDocument();
    expect(screen.queryByText("alice@example.com")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /extension token/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Logout" }));
    expect(authMock.signOut).toHaveBeenCalled();
  });

  it("shows a Log Out button in the sidebar for signed-in users", async () => {
    render(<AuthGate><SidebarAccount /></AuthGate>);
    await waitFor(() => expect(authMock.onChange).toBeInstanceOf(Function));
    act(() => authMock.onChange({ user: { id: "alice", email: "alice@example.com" } }));

    fireEvent.click(await screen.findByRole("button", { name: "Log Out" }));
    expect(authMock.signOut).toHaveBeenCalled();
  });

  it("renders nothing in the sidebar outside the auth gate", () => {
    const { container } = render(<SidebarAccount />);
    expect(container).toBeEmptyDOMElement();
  });

  it("starts a private guest session from Continue as Guest and leaves it with Sign in", async () => {
    authMock.signInAsGuest.mockImplementation(async () => {
      authMock.onChange({ user: { id: "guest_abc", full_name: "Guest", guest: true } });
    });
    render(<AuthGate><StatefulChild /><SidebarAccount /></AuthGate>);
    await screen.findByRole("heading", { name: "Create Account" });

    fireEvent.click(screen.getByRole("button", { name: "Continue as Guest" }));
    expect(await screen.findByText("Guest mode — use test data only")).toBeInTheDocument();
    expect(authMock.signInAsGuest).toHaveBeenCalled();
    expect(authMock.setGuestMode).not.toHaveBeenCalledWith(true); // not the shared local guest
    expect(screen.getByRole("button", { name: "Draft: 0" })).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Sign In" }).at(-1)); // sidebar button
    expect(authMock.signOut).toHaveBeenCalled();
  });

  it("falls back to local guest mode when the server cannot issue a guest session", async () => {
    authMock.signInAsGuest.mockRejectedValue(new Error("Not Found"));
    render(<AuthGate><StatefulChild /></AuthGate>);
    await screen.findByRole("heading", { name: "Create Account" });

    fireEvent.click(screen.getByRole("button", { name: "Continue as Guest" }));
    expect(await screen.findByText("Guest mode — use test data only")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Draft: 0" })).toBeInTheDocument();
    expect(authMock.setGuestMode).toHaveBeenCalledWith(true);

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Create Account" })).toBeInTheDocument();
    expect(authMock.setGuestMode).toHaveBeenCalledWith(false);
  });
});

import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";

const authMock = vi.hoisted(() => ({ onChange: null, setGuestMode: vi.fn() }));

vi.mock("./auth.js", () => ({
  authEnabled: true,
  getAccessToken: vi.fn(() => null),
  guestModeEnabled: true,
  installAuthFetch: vi.fn(),
  setGuestMode: authMock.setGuestMode,
  auth: { signOut: vi.fn() },
  trackSession: (onChange) => {
    authMock.onChange = onChange;
    onChange(null);
    return vi.fn();
  },
}));

import AuthGate from "./AuthGate.jsx";

afterEach(cleanup);

function StatefulChild() {
  const [draft, setDraft] = React.useState(0);
  return <button onClick={() => setDraft((value) => value + 1)}>Draft: {draft}</button>;
}

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

    fireEvent.click(screen.getByRole("button", { name: "SIGN UP" }));

    expect(screen.getByRole("heading", { name: "Create Account" })).toBeInTheDocument();
    expect(container.querySelector("main")).toHaveClass("ag-signup");
  });

  it("clears mounted profile state when the authenticated user changes", async () => {
    render(<AuthGate><StatefulChild /></AuthGate>);
    await waitFor(() => expect(authMock.onChange).toBeInstanceOf(Function));

    act(() => authMock.onChange({ user: { id: "alice", email: "alice@example.com" } }));
    fireEvent.click(await screen.findByRole("button", { name: "Draft: 0" }));
    expect(screen.getByRole("button", { name: "Draft: 1" })).toBeInTheDocument();

    act(() => authMock.onChange({ user: { id: "bob", email: "bob@example.com" } }));

    expect(await screen.findByText("bob@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Draft: 0" })).toBeInTheDocument();
  });

  it("enters and exits guest mode without authenticating", async () => {
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

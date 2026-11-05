import React from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./NangoConnectPanel.jsx", () => ({ default: ({ children }) => <div data-testid="nango">{children}</div> }));
import EmailAgentDashboard from "./EmailAgentDashboard.jsx";

const dashboard = {
  accounts: [{ id: "a1", email: "me@example.com", provider: "gmail", status: "connected" }],
  inbox: [
    { id: "m1", company: "Stripe", job_title: "Cloud Architect", subject: "Interview request", category: "interview_invitation", confidence: 0.92, received_at: new Date().toISOString(), application_status: "interview" },
    { id: "m2", company: "Acme", job_title: "Data Engineer", subject: "Thanks for applying", category: "rejection", received_at: new Date().toISOString() },
  ],
  interviews: [],
  pending_approvals: [{ id: "d1", company: "Stripe", kind: "reply", subject: "Re: Interview request", body: "Hi Sarah, thanks!", to_email: "s@stripe.com" }],
  application_updates: { offers: [{ id: "o1", company: "Globex", job_title: "SWE", updated_at: new Date().toISOString() }] },
  history: { sent: [], failed: [], received: [], follow_ups: [] },
  needs_confirmation: [],
  applications: [],
  notifications: [],
  providers: {},
};

describe("EmailAgentDashboard", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => ({ ok: true, json: async () => dashboard }));
  });
  afterEach(cleanup);

  it("shows real counts, filters the inbox, and switches sections", async () => {
    render(<EmailAgentDashboard />);
    expect(await screen.findByRole("heading", { name: "Email Agent" })).toBeInTheDocument();
    expect(screen.getByText("1 inbox monitored")).toBeInTheDocument();

    const stats = screen.getByRole("region", { name: "Email Agent summary" });
    expect(within(stats).getByText("Job emails").parentElement).toHaveTextContent("2");
    expect(within(stats).getByText("Awaiting approval").parentElement).toHaveTextContent("1");

    // Category chips narrow the inbox list.
    fireEvent.click(screen.getByRole("button", { name: /Rejection/ }));
    expect(screen.queryByText("Stripe")).not.toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Pending Approvals/ }));
    expect(screen.getByLabelText("Suggested response")).toHaveValue("Hi Sarah, thanks!");
    expect(screen.getByRole("button", { name: /Approve & Send/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Application Updates/ }));
    expect(screen.getByText("Globex")).toBeInTheDocument();
  });
});

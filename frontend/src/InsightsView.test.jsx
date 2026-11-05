import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InsightsView } from "./App.jsx";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Analytics insights dashboard", () => {
  const platforms = [
    { id: "greenhouse", name: "Greenhouse", color: "#10b981", stored_jobs_count: 70 },
    { id: "ashby", name: "Ashby", color: "#a855f7", stored_jobs_count: 30 },
  ];

  it("renders live metrics, skill rankings, and ATS distribution from API data", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => ({
      ok: true,
      json: async () => url.includes("/api/platforms") ? { platforms } : ({
        total_active_jobs: 100,
        by_platform: { greenhouse: 70, ashby: 30 },
        recent_runs: [{ platform: "greenhouse", status: "success", jobs_found: 12, duration_seconds: 4, finished_at: "2026-11-05T10:00:00Z" }],
        top_skills: [{ skill: "Python", count: 40 }, { skill: "Project Management", count: 25 }],
      }),
    })));

    render(<InsightsView platforms={platforms} />);

    expect(await screen.findByText("100")).toBeInTheDocument();
    expect(screen.getAllByText("Python").length).toBeGreaterThan(0);
    expect(screen.getByText("70 jobs")).toBeInTheDocument();
    expect(screen.getByText("+12")).toBeInTheDocument();
  });

  it("filters skill rankings and starts a crawler sync", async () => {
    const fetch = vi.fn((url) => ({
      ok: true,
      json: async () => url.includes("/api/scrape")
        ? { status: "started", message: "Crawler sync started." }
        : url.includes("/api/platforms")
          ? { platforms }
          : {
            total_active_jobs: 100,
            by_platform: { greenhouse: 70, ashby: 30 },
            top_skills: [{ skill: "Python", count: 40 }, { skill: "Project Management", count: 25 }],
          },
    }));
    vi.stubGlobal("fetch", fetch);

    render(<InsightsView platforms={platforms} />);

    await screen.findAllByText("Python");
    fireEvent.click(screen.getByRole("button", { name: "Tech & Data" }));
    const skillRows = document.querySelectorAll(".analytics-skill-row");
    expect(skillRows).toHaveLength(1);
    expect(skillRows[0]).toHaveTextContent("Python");
    expect(skillRows[0]).not.toHaveTextContent("Project Management");
    expect(screen.queryByRole("button", { name: "Operations" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Sync All Crawlers" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Crawler sync started.");
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/scrape?platform=all"),
      expect.objectContaining({ method: "POST" })
    ));
  });
});

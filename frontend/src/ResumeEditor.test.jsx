import React, { useState } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ResumeEditor, { bulletHints } from "./ResumeEditor.jsx";

vi.mock("./PdfPreview.jsx", () => ({ default: () => <div data-testid="pdf-preview" /> }));

const base = () => ({
  personal_info: { name: "Ada", email: "a@b.co", phone: "", location: "", linkedin: "", github: "", portfolio: "" },
  professional_summary: "Engineer.",
  experience: [{ title: "Dev", organization: "Acme", dates: "2020", location: "", bullets: ["Built an API that cut latency by 30%."] }],
  projects: [], education: [], certifications: [], skills: ["Python"],
});

function Harness({ onSave = vi.fn(), initial = base(), recommended = [] }) {
  const [resume, setResume] = useState(initial);
  const [snapshot, setSnapshot] = useState(initial);
  const [saving, setSaving] = useState(false);
  return (
    <ResumeEditor
      resume={resume}
      setResume={setResume}
      job={{ company: "Acme" }}
      savedSnapshot={snapshot}
      isSaving={saving}
      onSave={async () => {
        setSaving(true);
        onSave(resume);
        setSnapshot(resume);
        setSaving(false);
      }}
      isRewriting={false}
      onImprove={() => {}}
      scoring={{}}
      recommendedSkills={recommended}
    />
  );
}

const goTo = (name) => fireEvent.click(within(screen.getByRole("navigation", { name: "Structured editor sections" })).getByRole("button", { name }));

describe("bulletHints", () => {
  it("flags a weak, unmeasured bullet and accepts a strong one", () => {
    expect(bulletHints("Responsible for the backend")).toEqual(expect.arrayContaining([expect.stringMatching(/action verb/), expect.stringMatching(/measurable/)]));
    expect(bulletHints("Built an API that cut latency by 30% for all customers")).toEqual([]);
    expect(bulletHints("")).toEqual([]);
  });
});

describe("ResumeEditor", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("autosaves two seconds after the last edit and shows the status", () => {
    const onSave = vi.fn();
    render(<Harness onSave={onSave} />);
    expect(screen.getByRole("status")).toHaveTextContent("All changes saved");

    fireEvent.change(screen.getByLabelText("Professional summary"), { target: { value: "Senior engineer." } });
    expect(screen.getByRole("status")).toHaveTextContent("Unsaved changes");
    act(() => { vi.advanceTimersByTime(1500); });
    expect(onSave).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(600); });
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0].professional_summary).toBe("Senior engineer.");
    expect(screen.getByRole("status")).toHaveTextContent("All changes saved");
  });

  it("undoes and redoes edits", () => {
    render(<Harness />);
    const box = () => screen.getByLabelText("Professional summary");
    fireEvent.change(box(), { target: { value: "Changed." } });
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(box()).toHaveValue("Engineer.");
    fireEvent.click(screen.getByRole("button", { name: "Redo" }));
    expect(box()).toHaveValue("Changed.");
  });

  it("adds a bullet on Enter, removes an empty one on Backspace, and splits pasted lists", () => {
    render(<Harness />);
    goTo(/Work Experience/);
    const first = screen.getByLabelText("Experience bullet 1");
    fireEvent.keyDown(first, { key: "Enter" });
    const second = screen.getByLabelText("Experience bullet 2");
    expect(second).toHaveValue("");
    expect(second).toHaveFocus();

    fireEvent.keyDown(second, { key: "Backspace" });
    expect(screen.queryByLabelText("Experience bullet 2")).not.toBeInTheDocument();

    fireEvent.paste(screen.getByLabelText("Experience bullet 1"), { clipboardData: { getData: () => "- Led a team of 4\n- Shipped v2 in 3 weeks" } });
    expect(screen.getByLabelText("Experience bullet 1")).toHaveValue("Led a team of 4");
    expect(screen.getByLabelText("Experience bullet 2")).toHaveValue("Shipped v2 in 3 weeks");
  });

  it("shows writing tips only for the bullet being edited", () => {
    render(<Harness initial={{ ...base(), experience: [{ ...base().experience[0], bullets: ["Responsible for servers"] }] }} />);
    goTo(/Work Experience/);
    expect(screen.queryByLabelText("Writing tips")).not.toBeInTheDocument();
    fireEvent.focus(screen.getByLabelText("Experience bullet 1"));
    expect(screen.getByLabelText("Writing tips")).toHaveTextContent(/action verb/);
  });

  it("adds many skills from a pasted list without duplicates and offers job skills", () => {
    render(<Harness recommended={["Docker", "python"]} />);
    goTo(/Skills/);
    fireEvent.paste(screen.getByLabelText("Add new skill"), { clipboardData: { getData: () => "Go, Rust, python" } });
    expect(screen.getByRole("button", { name: "Remove skill Go" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove skill Rust" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Remove skill (Python|python)/ })).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "+ Docker" }));
    expect(screen.getByRole("button", { name: "Remove skill Docker" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ Docker" })).not.toBeInTheDocument();
  });
});

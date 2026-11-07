import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it } from "vitest";
import JobFilterPanel, { EMPTY_JOB_FILTERS, getEmploymentType } from "./JobFilterPanel.jsx";

let latest;
function Harness({ suggestions = [] }) {
  const [filters, setFilters] = useState(EMPTY_JOB_FILTERS);
  latest = filters;
  return (
    <JobFilterPanel
      filters={filters}
      onChange={setFilters}
      onReset={() => setFilters(EMPTY_JOB_FILTERS)}
      matchCount={3}
      salaryStats={{ values: [], bins: [] }}
      skillSuggestions={suggestions}
    />
  );
}

// The panel starts closed; tests open it the way a user does.
const openFilters = () => fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));

describe("JobFilterPanel", () => {
  afterEach(cleanup);

  it("starts with the filter panel closed until the user clicks Filters", () => {
    render(<Harness />);
    expect(screen.queryByLabelText("Include skills")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Filters/ })).toHaveAttribute("aria-expanded", "false");
    openFilters();
    expect(screen.getByLabelText("Include skills")).toBeInTheDocument();
  });

  it("keeps a typed comma in the role box while filtering on the finished terms", () => {
    render(<Harness />);
    const role = screen.getByRole("searchbox", { name: "Job role" });
    fireEvent.change(role, { target: { value: "Data Engineer," } });
    expect(role).toHaveValue("Data Engineer,");
    expect(latest.roles).toEqual(["Data Engineer"]);
  });

  it("adds skills as tags, shows them as removable chips, and switches Any/All", () => {
    render(<Harness suggestions={["Docker"]} />);
    openFilters();
    const include = screen.getByLabelText("Include skills");
    fireEvent.change(include, { target: { value: "Python" } });
    fireEvent.keyDown(include, { key: "Enter" });
    fireEvent.change(include, { target: { value: "React," } });
    expect(latest.tech).toEqual(["Python", "React"]);

    fireEvent.click(screen.getByRole("button", { name: "+ Docker" }));
    expect(latest.tech).toEqual(["Python", "React", "Docker"]);
    expect(screen.getByText("1 active")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(latest.techMode).toBe("and");

    fireEvent.click(screen.getByRole("button", { name: "Remove filter React" }));
    expect(latest.tech).toEqual(["Python", "Docker"]);
  });

  it("clears every filter and the search text with Clear all", () => {
    render(<Harness />);
    openFilters();
    fireEvent.change(screen.getByRole("searchbox", { name: "Job role" }), { target: { value: "Designer" } });
    fireEvent.click(screen.getByRole("button", { name: "Senior" }));
    expect(screen.getByText("1 active")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Clear all/ }));
    expect(latest).toEqual(EMPTY_JOB_FILTERS);
    expect(screen.getByRole("searchbox", { name: "Job role" })).toHaveValue("");
  });

  it("sets work mode and job type filters", () => {
    render(<Harness />);
    openFilters();
    fireEvent.click(screen.getByRole("button", { name: "Remote" }));
    fireEvent.click(screen.getByRole("button", { name: "Contract" }));
    expect(latest.workModes).toEqual(["remote"]);
    expect(latest.jobTypes).toEqual(["contract"]);
    expect(screen.getByText("2 active")).toBeInTheDocument();
    expect(screen.queryByText(/Visa sponsors only|Minimum match/)).not.toBeInTheDocument();
  });

  it("classifies employment types from the listing field and title", () => {
    expect(getEmploymentType({ employment_type: "Full-time", title: "Engineer" })).toBe("full-time");
    expect(getEmploymentType({ employment_type: "", title: "Software Engineering Intern" })).toBe("internship");
    expect(getEmploymentType({ employment_type: "Contract", title: "Data Engineer" })).toBe("contract");
    expect(getEmploymentType({ employment_type: "Part time", title: "Analyst" })).toBe("part-time");
  });
});

import React from "react";
import { MapPin, Search, SlidersHorizontal, X } from "lucide-react";

export const EMPTY_JOB_FILTERS = {
  roles: [],
  location: "",
  levels: [],
  salaryMin: "",
  salaryMax: "",
  currency: "GBP",
  equityOnly: false,
  tech: [],
  excludeTech: [],
  techMode: "or",
};

export const LEVEL_BANDS = [
  { id: "entry", label: "Entry level", levels: ["entry"] },
  { id: "graduate", label: "Graduate scheme", levels: ["graduate"] },
  { id: "junior", label: "Junior", levels: ["junior"] },
  { id: "mid", label: "Mid-level", levels: ["mid"] },
  { id: "senior", label: "Senior", levels: ["senior"] },
];

function terms(value) {
  return value.split(",").map((term) => term.trim()).filter(Boolean);
}

function Field({ icon, label, children, className = "" }) {
  return (
    <label className={`jd-quick-search-field ${className}`}>
      {icon}
      <span className="jd-visually-hidden">{label}</span>
      {children}
    </label>
  );
}

export default function JobFilterPanel({
  filters,
  onChange,
  onReset,
  matchCount,
  salaryStats,
  skillSuggestions = [],
}) {
  const set = (key, value) => onChange((current) => ({ ...current, [key]: value }));
  const setText = (key, value) => set(key, terms(value));
  const rolesValue = filters.roles.join(", ");

  return (
    <div className="jd-filter-panel">
      <div className="jd-searchbar">
        <Field icon={<Search size={17} aria-hidden="true" />} label="Job role" className="jd-search">
          <input
            type="search"
            aria-label="Job role"
            placeholder="Job role"
            value={rolesValue}
            onChange={(event) => setText("roles", event.target.value)}
          />
        </Field>
        <Field icon={<MapPin size={17} aria-hidden="true" />} label="Company or location">
          <input
            type="search"
            aria-label="Company or location"
            placeholder="Company or location"
            value={filters.location}
            onChange={(event) => set("location", event.target.value)}
          />
          <input
            className="jd-visually-hidden"
            type="search"
            aria-label="City or Location"
            tabIndex={-1}
            value={filters.location}
            onChange={(event) => set("location", event.target.value)}
          />
        </Field>
        <button type="button" className="jd-search-submit" onClick={() => {}}>
          <Search size={15} aria-hidden="true" />
          Show {matchCount.toLocaleString()} matching jobs
        </button>
        <button type="button" className="jd-clear" onClick={onReset}>
          <X size={14} aria-hidden="true" /> Clear
        </button>
      </div>

      <details className="jd-advanced-filters">
        <summary><SlidersHorizontal size={14} aria-hidden="true" /> Advanced filters</summary>
        <div className="job-discovery-form">
          <div className="discovery-row">
            <fieldset className="discovery-choice-group">
              <legend>Experience level</legend>
              <div className="discovery-options">
                {LEVEL_BANDS.map((band) => (
                  <button
                    key={band.id}
                    type="button"
                    className={`discovery-chip ${filters.levels.includes(band.id) ? "selected" : ""}`}
                    aria-pressed={filters.levels.includes(band.id)}
                    onClick={() => set("levels", filters.levels.includes(band.id)
                      ? filters.levels.filter((level) => level !== band.id)
                      : [...filters.levels, band.id])}
                  >
                    {band.label}
                  </button>
                ))}
              </div>
            </fieldset>
            <fieldset className="discovery-field">
              <legend>Salary range</legend>
              <div className="salary-range-inputs">
                <input
                  type="number"
                  aria-label="Minimum salary"
                  min="0"
                  placeholder="Min"
                  value={filters.salaryMin}
                  onChange={(event) => set("salaryMin", event.target.value)}
                />
                <span>to</span>
                <input
                  type="number"
                  aria-label="Maximum salary"
                  min="0"
                  placeholder="Max"
                  value={filters.salaryMax}
                  onChange={(event) => set("salaryMax", event.target.value)}
                />
                <select
                  aria-label="Salary currency"
                  value={filters.currency}
                  onChange={(event) => set("currency", event.target.value)}
                >
                  <option value="GBP">GBP</option>
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                </select>
              </div>
              {salaryStats?.values?.length > 0 && (
                <span className="discovery-hint">{salaryStats.values.length} jobs include salary data.</span>
              )}
            </fieldset>
          </div>
          <div className="discovery-row">
            <label className="discovery-checkbox">
              <input
                type="checkbox"
                checked={filters.equityOnly}
                onChange={(event) => set("equityOnly", event.target.checked)}
              />
              Equity or stock options only
            </label>
            <label className="discovery-field">
              <span>Include skills</span>
              <input
                type="text"
                aria-label="Include skills"
                placeholder="Python, React"
                value={filters.tech.join(", ")}
                onChange={(event) => setText("tech", event.target.value)}
              />
            </label>
            <label className="discovery-field">
              <span>Exclude skills</span>
              <input
                type="text"
                aria-label="Exclude skills"
                placeholder="Java, PHP"
                value={filters.excludeTech.join(", ")}
                onChange={(event) => setText("excludeTech", event.target.value)}
              />
            </label>
          </div>
        </div>
      </details>
    </div>
  );
}

/**
 * Search and filtering controls for the job directory.
 * Role and location search, then grouped filters: experience, salary, date posted, skills and perks.
 */
import React, { useEffect, useState } from "react";
import {
  Ban,
  Banknote,
  BriefcaseBusiness,
  CalendarClock,
  Check,
  ChevronDown,
  Globe2,
  Laptop,
  MapPin,
  Plus,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Wrench,
  X,
} from "lucide-react";
import "./jobFilterPanel.css";

export const EMPTY_JOB_FILTERS = {
  roles: [],
  location: "",
  levels: [],
  salaryMin: "",
  salaryMax: "",
  currency: "GBP",
  postedWithin: "0",
  workModes: [],
  jobTypes: [],
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

const POSTED_OPTIONS = [
  ["0", "Any time"],
  ["1", "Past 24 hours"],
  ["7", "Past week"],
  ["14", "Past 2 weeks"],
  ["30", "Past month"],
];

const CURRENCY_SYMBOL = { GBP: "£", USD: "$", EUR: "€" };

const WORK_MODES = [
  ["remote", "Remote"],
  ["hybrid", "Hybrid"],
  ["on-site", "On-site"],
];

const JOB_TYPES = [
  ["full-time", "Full-time"],
  ["part-time", "Part-time"],
  ["contract", "Contract"],
  ["internship", "Internship"],
];

/** Normalises a job's employment type (from the listing field, then the title) to a JOB_TYPES id. */
export function getEmploymentType(job) {
  const text = `${job?.employment_type || ""} ${job?.title || ""}`.toLowerCase();
  if (/\bintern(ship)?\b|\bplacement\b/.test(text)) return "internship";
  if (/\bcontract(or)?\b|\bfixed[- ]term\b|\bfreelance\b|\btemporary\b/.test(text)) return "contract";
  if (/\bpart[- ]?time\b/.test(text)) return "part-time";
  if (/\bfull[- ]?time\b|\bpermanent\b/.test(text) || !job?.employment_type) return "full-time";
  return "";
}

const toggle = (list, id) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

function terms(value) {
  return value.split(",").map((term) => term.trim()).filter(Boolean);
}

function formatMoney(amount, currency) {
  const symbol = CURRENCY_SYMBOL[currency] || "";
  if (amount >= 1000) return `${symbol}${Math.round(amount / 1000)}k`;
  return `${symbol}${Math.round(amount)}`;
}

/** Comma-separated text box that keeps what the user typed (including a trailing comma). */
function useTermsText(list, onCommit) {
  const [text, setText] = useState(list.join(", "));
  useEffect(() => {
    // Follow outside changes (Clear, chip removal) without fighting the user's typing.
    if (terms(text).join("|").toLowerCase() !== list.join("|").toLowerCase()) setText(list.join(", "));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list.join("|")]);
  return [text, (value) => {
    setText(value);
    onCommit(terms(value));
  }];
}

function Section({ icon, title, hint, action, children, className = "" }) {
  return (
    <section className={`jfp-section ${className}`}>
      <header className="jfp-section-head">
        <span className="jfp-section-icon" aria-hidden="true">{icon}</span>
        <span className="jfp-section-titles">
          <h3>{title}</h3>
          {hint && <p>{hint}</p>}
        </span>
        {action}
      </header>
      {children}
    </section>
  );
}

function TagInput({ label, placeholder, values, onChange, tone = "include" }) {
  const [draft, setDraft] = useState("");
  const add = (raw) => {
    const next = [...values];
    terms(raw).forEach((t) => {
      if (!next.some((v) => v.toLowerCase() === t.toLowerCase())) next.push(t);
    });
    onChange(next);
    setDraft("");
  };
  return (
    <div className={`jfp-tags ${tone}`}>
      {values.map((v) => (
        <span key={v} className="jfp-tag">
          {v}
          <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(values.filter((x) => x !== v))}>
            <X size={12} aria-hidden="true" />
          </button>
        </span>
      ))}
      <input
        type="text"
        aria-label={label}
        placeholder={values.length ? "Add another…" : placeholder}
        value={draft}
        onChange={(e) => {
          const value = e.target.value;
          if (value.includes(",")) add(value);
          else setDraft(value);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && draft.trim()) {
            e.preventDefault();
            add(draft);
          } else if (e.key === "Backspace" && !draft && values.length) {
            onChange(values.slice(0, -1));
          }
        }}
        onBlur={() => draft.trim() && add(draft)}
      />
    </div>
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
  // Closed until the user clicks "Filters"; active filters still show as chips.
  const [open, setOpen] = useState(false);
  const set = (key, value) => onChange((current) => ({ ...current, [key]: value }));
  const [rolesText, setRolesText] = useTermsText(filters.roles, (list) => set("roles", list));

  const salaryActive = Boolean(filters.salaryMin || filters.salaryMax);
  const activeFilterCount = [
    filters.levels.length > 0,
    salaryActive,
    filters.postedWithin !== "0",
    (filters.workModes || []).length > 0,
    (filters.jobTypes || []).length > 0,
    filters.tech.length > 0,
    filters.excludeTech.length > 0,
  ].filter(Boolean).length;

  const currency = filters.currency;
  const salaryLabel = salaryActive
    ? `${filters.salaryMin ? formatMoney(Number(filters.salaryMin), currency) : "Any"} – ${filters.salaryMax ? formatMoney(Number(filters.salaryMax), currency) : "Any"}`
    : "";
  const salaryCount = salaryStats?.values?.length || 0;
  const suggestions = skillSuggestions.filter(
    (s) => ![...filters.tech, ...filters.excludeTech].some((t) => t.toLowerCase() === String(s).toLowerCase())
  ).slice(0, 8);

  // Removable summary chips for everything that is narrowing the list.
  const chips = [
    ...filters.levels.map((id) => ({
      key: `level-${id}`,
      label: LEVEL_BANDS.find((b) => b.id === id)?.label || id,
      clear: () => set("levels", filters.levels.filter((l) => l !== id)),
    })),
    salaryActive && { key: "salary", label: `Salary ${salaryLabel}`, clear: () => onChange((c) => ({ ...c, salaryMin: "", salaryMax: "" })) },
    filters.postedWithin !== "0" && {
      key: "posted",
      label: POSTED_OPTIONS.find(([v]) => v === filters.postedWithin)?.[1] || "Recent",
      clear: () => set("postedWithin", "0"),
    },
    ...(filters.workModes || []).map((id) => ({
      key: `mode-${id}`,
      label: WORK_MODES.find(([v]) => v === id)?.[1] || id,
      clear: () => set("workModes", filters.workModes.filter((m) => m !== id)),
    })),
    ...(filters.jobTypes || []).map((id) => ({
      key: `type-${id}`,
      label: JOB_TYPES.find(([v]) => v === id)?.[1] || id,
      clear: () => set("jobTypes", filters.jobTypes.filter((t) => t !== id)),
    })),
    ...filters.tech.map((t) => ({ key: `tech-${t}`, label: t, clear: () => set("tech", filters.tech.filter((x) => x !== t)) })),
    ...filters.excludeTech.map((t) => ({
      key: `ex-${t}`,
      label: `Not ${t}`,
      tone: "exclude",
      clear: () => set("excludeTech", filters.excludeTech.filter((x) => x !== t)),
    })),
  ].filter(Boolean);

  return (
    <div className="jfp">
      <form className="jfp-search" role="search" onSubmit={(e) => e.preventDefault()}>
        <label className="jfp-field">
          <Search size={18} aria-hidden="true" />
          <span className="jd-visually-hidden">Job role</span>
          <input
            type="search"
            aria-label="Job role"
            placeholder="Job title, e.g. Data Engineer, Product Designer"
            value={rolesText}
            onChange={(event) => setRolesText(event.target.value)}
          />
        </label>
        <label className="jfp-field">
          <MapPin size={18} aria-hidden="true" />
          <span className="jd-visually-hidden">Company or location</span>
          <input
            type="search"
            aria-label="Company or location"
            placeholder="Company, city or “UK”"
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
        </label>
        <button type="submit" className="jfp-submit">
          <Search size={16} aria-hidden="true" />
          Show {matchCount.toLocaleString()} matching jobs
        </button>
      </form>

      <div className="jfp-bar">
        <button
          type="button"
          className="jfp-toggle"
          aria-expanded={open}
          aria-controls="jfp-body"
          onClick={() => setOpen((v) => !v)}
        >
          <SlidersHorizontal size={16} aria-hidden="true" />
          <span>Filters</span>
          {activeFilterCount > 0 && <span className="jfp-count">{activeFilterCount} active</span>}
          <ChevronDown size={16} aria-hidden="true" className={`jfp-chevron ${open ? "open" : ""}`} />
        </button>

        <div className="jfp-chips" aria-label="Active filters">
          {chips.map((chip) => (
            <span key={chip.key} className={`jfp-chip ${chip.tone || ""}`}>
              {chip.label}
              <button type="button" aria-label={`Remove filter ${chip.label}`} onClick={chip.clear}>
                <X size={12} aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>

        <button type="button" className="jfp-reset" onClick={onReset} disabled={!activeFilterCount && !filters.roles.length && !filters.location}>
          <RotateCcw size={14} aria-hidden="true" /> Clear all
        </button>
      </div>

      {open && (
        <div className="jfp-body" id="jfp-body">
          <Section
            className="jfp-experience"
            icon={<BriefcaseBusiness size={16} />}
            title="Experience level"
            hint="Select one or more levels."
          >
            <fieldset className="jfp-fieldset">
              <legend className="jd-visually-hidden">Experience level</legend>
              <div className="jfp-options">
                {LEVEL_BANDS.map((band) => {
                  const on = filters.levels.includes(band.id);
                  return (
                    <button
                      key={band.id}
                      type="button"
                      className={`jfp-option ${on ? "on" : ""}`}
                      aria-pressed={on}
                      onClick={() => set("levels", on ? filters.levels.filter((l) => l !== band.id) : [...filters.levels, band.id])}
                    >
                      {on && <Check size={14} aria-hidden="true" />}
                      {band.label}
                    </button>
                  );
                })}
              </div>
            </fieldset>
          </Section>

          <Section
            className="jfp-posted"
            icon={<CalendarClock size={16} />}
            title="Date posted"
            hint="Focus on fresh listings."
          >
            <label className="jfp-select">
              <span className="jd-visually-hidden">Posted within</span>
              <select aria-label="Posted within" value={filters.postedWithin} onChange={(e) => set("postedWithin", e.target.value)}>
                {POSTED_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <ChevronDown size={16} aria-hidden="true" />
            </label>
          </Section>

          <Section className="jfp-mode" icon={<Laptop size={16} />} title="Work mode" hint="Where you'll work.">
            <fieldset className="jfp-fieldset">
              <legend className="jd-visually-hidden">Work mode</legend>
              <div className="jfp-options compact">
                {WORK_MODES.map(([id, label]) => {
                  const on = (filters.workModes || []).includes(id);
                  return (
                    <button key={id} type="button" className={`jfp-option ${on ? "on" : ""}`} aria-pressed={on} onClick={() => set("workModes", toggle(filters.workModes || [], id))}>
                      {on && <Check size={14} aria-hidden="true" />}
                      {id === "remote" && !on && <Globe2 size={14} aria-hidden="true" />}
                      {label}
                    </button>
                  );
                })}
              </div>
            </fieldset>
          </Section>

          <Section
            className="jfp-salary"
            icon={<Banknote size={16} />}
            title="Salary range"
            hint={salaryCount ? `${salaryCount.toLocaleString()} jobs list a salary in ${currency}. Jobs without one are hidden when this is set.` : `No listings show a salary in ${currency} yet.`}
            action={(
              <div className="jfp-segment" role="group" aria-label="Salary currency">
                {Object.keys(CURRENCY_SYMBOL).map((c) => (
                  <button key={c} type="button" className={currency === c ? "on" : ""} aria-pressed={currency === c} onClick={() => set("currency", c)}>
                    {c}
                  </button>
                ))}
              </div>
            )}
          >
            <div className="jfp-range">
              <label className="jfp-money">
                <span>Minimum</span>
                <span className="jfp-money-box">
                  <b>{CURRENCY_SYMBOL[currency]}</b>
                  <input
                    type="number"
                    inputMode="numeric"
                    aria-label="Minimum salary"
                    min="0"
                    step="1000"
                    placeholder="No min"
                    value={filters.salaryMin}
                    onChange={(e) => set("salaryMin", e.target.value)}
                  />
                </span>
              </label>
              <span className="jfp-range-dash" aria-hidden="true">–</span>
              <label className="jfp-money">
                <span>Maximum</span>
                <span className="jfp-money-box">
                  <b>{CURRENCY_SYMBOL[currency]}</b>
                  <input
                    type="number"
                    inputMode="numeric"
                    aria-label="Maximum salary"
                    min="0"
                    step="1000"
                    placeholder="No max"
                    value={filters.salaryMax}
                    onChange={(e) => set("salaryMax", e.target.value)}
                  />
                </span>
              </label>
            </div>
          </Section>

          <Section
            className="jfp-skills"
            icon={<Wrench size={16} />}
            title="Skills"
            hint="Press Enter or comma to add a skill."
            action={(
              <div className="jfp-segment" role="group" aria-label="Skill match mode">
                <button type="button" className={filters.techMode !== "and" ? "on" : ""} aria-pressed={filters.techMode !== "and"} onClick={() => set("techMode", "or")}>
                  Any
                </button>
                <button type="button" className={filters.techMode === "and" ? "on" : ""} aria-pressed={filters.techMode === "and"} onClick={() => set("techMode", "and")}>
                  All
                </button>
              </div>
            )}
          >
            <div className="jfp-skill-row">
              <span className="jfp-skill-label"><Plus size={13} aria-hidden="true" /> Include</span>
              <TagInput label="Include skills" placeholder="Python, React" values={filters.tech} onChange={(v) => set("tech", v)} />
            </div>
            <div className="jfp-skill-row">
              <span className="jfp-skill-label exclude"><Ban size={13} aria-hidden="true" /> Exclude</span>
              <TagInput label="Exclude skills" placeholder="Java, PHP" values={filters.excludeTech} onChange={(v) => set("excludeTech", v)} tone="exclude" />
            </div>
            {suggestions.length > 0 && (
              <div className="jfp-suggest">
                <span>Suggested</span>
                {suggestions.map((s) => (
                  <button key={s} type="button" onClick={() => set("tech", [...filters.tech, s])}>+ {s}</button>
                ))}
              </div>
            )}
          </Section>

          <Section className="jfp-type" icon={<BriefcaseBusiness size={16} />} title="Job type" hint="Contract style of the role.">
            <fieldset className="jfp-fieldset">
              <legend className="jd-visually-hidden">Job type</legend>
              <div className="jfp-options">
                {JOB_TYPES.map(([id, label]) => {
                  const on = (filters.jobTypes || []).includes(id);
                  return (
                    <button key={id} type="button" className={`jfp-option ${on ? "on" : ""}`} aria-pressed={on} onClick={() => set("jobTypes", toggle(filters.jobTypes || [], id))}>
                      {on && <Check size={14} aria-hidden="true" />}
                      {label}
                    </button>
                  );
                })}
              </div>
            </fieldset>
          </Section>

        </div>
      )}
    </div>
  );
}

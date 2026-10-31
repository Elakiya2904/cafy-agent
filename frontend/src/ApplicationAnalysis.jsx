import React, { useState } from "react";
import {
  AlertCircle,
  Award,
  Briefcase,
  FileText,
  FolderGit2,
  GraduationCap,
  Loader2,
  Plus,
  Wrench,
} from "lucide-react";
import { useJobMatchAnalysis } from "./JobMatchScore.jsx";
import "./applicationAnalysis.css";

// Pre-generation analysis shown on the Application tab after Apply:
// Profile Completeness, Job Match Score, section scores and gap analysis.

const API_BASE =
  typeof window !== "undefined" &&
  (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") &&
  window.location?.port &&
  ["5173", "5174", "3000"].includes(window.location?.port)
    ? "http://127.0.0.1:8000"
    : "";

const SECTION_ROWS = [
  { key: "summary", label: "Professional Summary", icon: FileText },
  { key: "skills", label: "Skills", icon: Wrench },
  { key: "experience", label: "Work Experience", icon: Briefcase },
  { key: "education", label: "Education", icon: GraduationCap },
  { key: "projects", label: "Projects", icon: FolderGit2 },
  { key: "certifications", label: "Certifications", icon: Award },
];

const GAP_FILTERS = [
  { key: "all", label: "All" },
  { key: "missing_from_profile", label: "Missing from Profile" },
  { key: "missing_qualification", label: "Missing Qualification" },
];

function tone(score) {
  if (score >= 75) return "strong";
  if (score >= 45) return "partial";
  return "weak";
}

function Ring({ score }) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100);
  return (
    <svg width="104" height="104" viewBox="0 0 104 104" aria-hidden="true" className={`aa-ring tone-${tone(score)}`}>
      <circle cx="52" cy="52" r={radius} className="aa-ring-track" />
      <circle
        cx="52"
        cy="52"
        r={radius}
        className="aa-ring-value"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform="rotate(-90 52 52)"
      />
      <text x="52" y="58" textAnchor="middle" className="aa-ring-text">{score}%</text>
    </svg>
  );
}

function ScoreCard({ title, score, caption, actionLabel, onAction }) {
  return (
    <div className="aa-card aa-score-card">
      <h4>{title}</h4>
      <Ring score={score} />
      <p className="aa-caption">{caption}</p>
      {onAction && (
        <button type="button" className="aa-btn-outline" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}

export default function ApplicationAnalysis({ job, resume, onResumeUpdated, onImproveProfile, onViewDetails }) {
  const { analysis, isAnalyzing, error } = useJobMatchAnalysis(job?.id, resume);
  const [gapFilter, setGapFilter] = useState("all");
  const [addingSkill, setAddingSkill] = useState("");
  const [addError, setAddError] = useState("");

  const addSkillToProfile = async (skill) => {
    setAddingSkill(skill);
    setAddError("");
    try {
      const resp = await fetch(`${API_BASE}/api/resume/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skills: [...(resume?.skills || []), skill] }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `Update failed (${resp.status})`);
      // The new resume flows back in as a prop, which re-runs the analysis.
      if (onResumeUpdated) onResumeUpdated(data.resume);
    } catch (err) {
      setAddError(err.message || `Could not add ${skill} to your profile.`);
    } finally {
      setAddingSkill("");
    }
  };

  if (!analysis) {
    return (
      <div className="aa-card aa-loading">
        {error ? (
          <span className="aa-error"><AlertCircle size={16} aria-hidden="true" /> {error}</span>
        ) : (
          <span><Loader2 size={16} className="aa-spin" aria-hidden="true" /> Analysing your profile against this job...</span>
        )}
      </div>
    );
  }

  const gaps = analysis.gaps || [];
  const counts = {
    all: gaps.length,
    missing_from_profile: gaps.filter((g) => g.type === "missing_from_profile").length,
    missing_qualification: gaps.filter((g) => g.type === "missing_qualification").length,
  };
  const visibleGaps = gapFilter === "all" ? gaps : gaps.filter((g) => g.type === gapFilter);
  const completeness = analysis.profile_completeness || { overall_score: 0 };

  return (
    <div className="aa-grid" data-testid="application-analysis">
      <div className="aa-left">
        <div className="aa-score-row">
          <ScoreCard
            title="Profile Completeness"
            score={completeness.overall_score}
            caption="Based on your master profile"
            actionLabel="Improve Profile"
            onAction={onImproveProfile}
          />
          <ScoreCard
            title="Job Match Score"
            score={analysis.job_match_score}
            caption="Based on this job's requirements"
            actionLabel="View details"
            onAction={onViewDetails}
          />
        </div>

        <div className="aa-card">
          <h4>Profile Section Scores</h4>
          <ul className="aa-section-scores">
            {SECTION_ROWS.map(({ key, label, icon: Icon }) => {
              // null = the job does not ask for this section, so it has no score.
              const score = analysis.sections?.[key]?.score ?? null;
              return (
                <li key={key} className={score == null ? "tone-na" : `tone-${tone(score)}`}>
                  <span className="aa-section-icon"><Icon size={14} aria-hidden="true" /></span>
                  <span className="aa-section-label">{label}</span>
                  <span className="aa-bar" aria-hidden="true"><span style={{ width: `${score ?? 0}%` }} /></span>
                  <span className="aa-section-value" title={score == null ? "Not required by this job" : undefined}>
                    {score == null ? "N/A" : `${score}%`}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      <div className="aa-card aa-gaps">
        <h4>
          Gap Analysis
          {isAnalyzing && <Loader2 size={14} className="aa-spin" aria-label="Updating" />}
        </h4>
        <div className="aa-gap-filters" role="tablist" aria-label="Gap filters">
          {GAP_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              role="tab"
              aria-selected={gapFilter === f.key}
              className={`aa-filter aa-filter-${f.key} ${gapFilter === f.key ? "active" : ""}`}
              onClick={() => setGapFilter(f.key)}
            >
              {f.label} ({counts[f.key]})
            </button>
          ))}
        </div>

        {addError && <div className="aa-error">{addError}</div>}

        <ul className="aa-gap-list">
          {visibleGaps.map((gap) => (
            <li key={`${gap.type}-${gap.title}`} className={`aa-gap aa-gap-${gap.type}`}>
              <span className="aa-gap-icon"><FileText size={15} aria-hidden="true" /></span>
              <span className="aa-gap-text">
                <strong>{gap.title}</strong>
                <small>{gap.detail}</small>
              </span>
              {gap.skill && (
                <button
                  type="button"
                  className="aa-btn-add"
                  onClick={() => addSkillToProfile(gap.skill)}
                  disabled={Boolean(addingSkill)}
                  aria-label={`Add ${gap.skill} to profile`}
                >
                  {addingSkill === gap.skill ? <Loader2 size={13} className="aa-spin" aria-hidden="true" /> : <Plus size={13} aria-hidden="true" />}
                  Add to Profile
                </button>
              )}
            </li>
          ))}
          {visibleGaps.length === 0 && <li className="aa-empty">No gaps in this category.</li>}
        </ul>

        <div className="aa-legend">
          <div className="aa-legend-item aa-gap-missing_from_profile">
            <strong>Missing from Profile</strong>
            <small>You may have this skill or experience, but it is not in your profile.</small>
          </div>
          <div className="aa-legend-item aa-gap-missing_qualification">
            <strong>Missing Qualification</strong>
            <small>This requirement is not satisfied by your current profile.</small>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Live job-match scoring hook and compact score components for resume tailoring.
 * Requests analysis as the working profile changes and exposes score status.
 */
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import "./jobMatchScore.css";

// Live job-match scoring for the Resume Editor. Scores come from POST /api/resumes/pre-analysis.

// Mirrors App.jsx: talk to the FastAPI port directly when served from the Vite dev server.
const API_BASE =
  typeof window !== "undefined" &&
  (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") &&
  window.location?.port &&
  ["5173", "5174", "3000"].includes(window.location?.port)
    ? "http://127.0.0.1:8000"
    : "";

const SECTION_ORDER = ["summary", "skills", "experience", "education", "projects", "certifications"];

function scoreTone(score) {
  if (score >= 75) return "strong";
  if (score >= 45) return "partial";
  return "weak";
}

async function fetchJobMatchAnalysis(jobId, profile, jobDescription = null) {
  const resp = await fetch(`${API_BASE}/api/resumes/pre-analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: jobId,
      resume_data: profile,
      ...(jobDescription == null ? {} : { job_description: jobDescription }),
    }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.detail || `Analysis failed (${resp.status})`);
  if (typeof data?.job_match_score !== "number" || !data.sections) throw new Error("Analysis returned an unexpected response.");
  return { matched_skills: [], missing_skills: [], missing_information: [], suggestions: [], ...data };
}

/** Converts the tailored-resume shape used by the Resume Editor into the profile shape the analysis expects. */
export function tailoredResumeToProfile(tailored, masterResume) {
  const t = tailored || {};
  const p = t.personal_info || {};
  return {
    ...(masterResume || {}),
    candidate_name: p.name || masterResume?.candidate_name,
    email: p.email || masterResume?.email,
    phone: p.phone || masterResume?.phone,
    linkedin: p.linkedin || masterResume?.linkedin,
    github: p.github || masterResume?.github,
    portfolio: p.portfolio || masterResume?.portfolio,
    summary: t.professional_summary || "",
    skills: t.skills || [],
    experience: (t.experience || []).map((e) => ({ ...e, company: e.company || e.organization })),
    education: t.education || [],
    projects: t.projects || [],
    certifications: t.certifications || [],
  };
}

/**
 * Scores `profile` against job `jobId`, re-running (debounced) whenever the profile changes.
 * Pass a null jobId to pause. `previousScore` is the overall score before the latest change.
 */
export function useJobMatchAnalysis(jobId, profile, debounceMs = 0, jobDescription = null) {
  const [analysis, setAnalysis] = useState(null);
  const [previousScore, setPreviousScore] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const lastScoreRef = useRef({ jobId: null, score: null });
  const profileKey = JSON.stringify(profile ?? null);
  const requestKey = JSON.stringify([jobId || "", profileKey, jobDescription]);

  useEffect(() => {
    if (!jobId || !profile) {
      setIsAnalyzing(false);
      setError("");
      return undefined;
    }
    let cancelled = false;
    setIsAnalyzing(true);
    setError("");
    const timer = setTimeout(async () => {
      try {
        const data = await fetchJobMatchAnalysis(jobId, profile, jobDescription);
        if (cancelled) return;
        const lastScore = lastScoreRef.current;
        setPreviousScore(lastScore.jobId === jobId ? lastScore.score : null);
        lastScoreRef.current = { jobId, score: data.job_match_score };
        setAnalysis({ key: requestKey, data });
      } catch (err) {
        if (!cancelled) setError(err.message || "Could not analyse this job match.");
      } finally {
        if (!cancelled) setIsAnalyzing(false);
      }
    }, debounceMs);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // profileKey captures profile content; the object identity changes on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, profileKey, debounceMs, requestKey, jobDescription]);

  return {
    analysis: analysis?.key === requestKey ? analysis.data : null,
    previousScore: analysis?.key === requestKey ? previousScore : null,
    isAnalyzing,
    error: jobId && !profile ? "Upload a résumé to calculate this job match." : error,
  };
}

export function SectionScoreBadge({ section, variant = "badge" }) {
  if (!section) return null;
  const dot = variant === "dot";
  const cls = dot ? "jms-score-dot" : "jms-score-badge";
  if (section.score == null) {
    return (
      <span className={`${cls} tone-na`} title={`${section.name}: not required by this job`}>
        {dot ? null : "N/A"}
      </span>
    );
  }
  return (
    <span className={`${cls} tone-${scoreTone(section.score)}`} title={`${section.name}: ${section.score}% match for this job`}>
      {dot ? null : `${section.score}%`}
    </span>
  );
}

/** Compact live score bar shown at the top of the Resume Editor. */
export function EditorMatchScore({ analysis, previousScore, isAnalyzing, error, targetRole, onInspect }) {
  if (!analysis) {
    return (
      <div className="jms-editor-score">
        {error ? (
          <span className="jms-muted"><AlertTriangle size={14} aria-hidden="true" /> {error}</span>
        ) : (
          <span className="jms-muted"><Loader2 size={14} className="jms-spin" aria-hidden="true" /> Scoring your resume against this job...</span>
        )}
      </div>
    );
  }
  const delta = previousScore === null ? 0 : analysis.job_match_score - previousScore;
  const metricSections = [
    ["summary", "Summary"],
    ["experience", "Work Exp"],
    ["skills", "Core Tech"],
    ["keywords", "Keywords"],
  ];
  return (
    <div className={`jms-editor-score tone-${scoreTone(analysis.job_match_score)}`} data-testid="editor-match-score">
      <div className="jms-editor-score-main">
        <strong className="jms-score-ring">{analysis.job_match_score}%</strong>
        <span className="jms-score-head">
          <b>JOB MATCH SCORE <i className="jms-tier">{analysis.match_tier || "Current draft"}</i></b>
          <small>Optimized for: <strong>{targetRole || "this target role"}</strong></small>
          {delta !== 0 && (
            <em className={delta > 0 ? "up" : "down"}> {delta > 0 ? `+${delta}` : delta} since last change</em>
          )}
        </span>
        {analysis.cv_quality && (
          <span className="jms-cv-quality">
            CV content <strong>{analysis.cv_quality.score}%</strong>
          </span>
        )}
        {isAnalyzing && <Loader2 size={14} className="jms-spin" aria-label="Updating score" />}
        <button type="button" className="jms-inspect" onClick={onInspect} disabled={!onInspect}>Inspect Matrix ›</button>
      </div>
      <div className="jms-editor-score-sections jms-metric-grid">
        {metricSections.map(([key, label]) => {
          const sec = analysis.sections[key];
          if (!sec) return null;
          return (
            <span key={key} className={`jms-editor-chip jms-metric tone-${sec.score == null ? "na" : scoreTone(sec.score)}`}>
              <small>{label}</small><b>{sec.score == null ? "N/A" : `${sec.score}%`}</b>
            </span>
          );
        })}
      </div>
      {(analysis.missing_skills || []).length > 0 && (
        <div className="jms-missing">
          <span className="jms-missing-label">Missing high-impact tags:</span>
          {(analysis.missing_skills || []).slice(0, 4).map((skill) => <code key={skill}>+ {skill}</code>)}
        </div>
      )}
      <p className="jms-score-note">
        During generation, job keywords already supported by your résumé are highlighted automatically. Skills without evidence are never added.
      </p>
    </div>
  );
}

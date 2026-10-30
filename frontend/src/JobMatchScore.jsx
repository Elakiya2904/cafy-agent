import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import "./jobMatchScore.css";

// Live job-match scoring for the Resume Editor. Scores come from POST /api/resumes/pre-analysis.

// Mirrors App.jsx: talk to the FastAPI port directly when served from the Vite dev server.
const API_BASE =
  typeof window !== "undefined" &&
  (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") &&
  window.location?.port &&
  window.location?.port !== "8000"
    ? "http://127.0.0.1:8000"
    : "";

const SECTION_ORDER = ["summary", "skills", "experience", "education", "projects", "certifications"];

function scoreTone(score) {
  if (score >= 75) return "strong";
  if (score >= 45) return "partial";
  return "weak";
}

async function fetchJobMatchAnalysis(jobId, profile) {
  const resp = await fetch(`${API_BASE}/api/resumes/pre-analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, resume_data: profile }),
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
export function useJobMatchAnalysis(jobId, profile, debounceMs = 0) {
  const [analysis, setAnalysis] = useState(null);
  const [previousScore, setPreviousScore] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const lastScoreRef = useRef(null);
  const profileKey = JSON.stringify(profile ?? null);

  useEffect(() => {
    if (!jobId || !profile) return undefined;
    let cancelled = false;
    const timer = setTimeout(async () => {
      setIsAnalyzing(true);
      setError("");
      try {
        const data = await fetchJobMatchAnalysis(jobId, profile);
        if (cancelled) return;
        setPreviousScore(lastScoreRef.current);
        lastScoreRef.current = data.job_match_score;
        setAnalysis(data);
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
  }, [jobId, profileKey, debounceMs]);

  return { analysis, previousScore, isAnalyzing, error };
}

export function SectionScoreBadge({ section }) {
  if (!section) return null;
  if (section.score == null) {
    return (
      <span className="jms-score-badge tone-na" title={`${section.name}: not required by this job`}>
        N/A
      </span>
    );
  }
  return (
    <span className={`jms-score-badge tone-${scoreTone(section.score)}`} title={`${section.name}: ${section.score}% match for this job`}>
      {section.score}%
    </span>
  );
}

/** Compact live score bar shown at the top of the Resume Editor. */
export function EditorMatchScore({ analysis, previousScore, isAnalyzing, error }) {
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
  return (
    <div className={`jms-editor-score tone-${scoreTone(analysis.job_match_score)}`} data-testid="editor-match-score">
      <div className="jms-editor-score-main">
        <strong>{analysis.job_match_score}%</strong>
        <span>
          Job Match · {analysis.match_tier}
          {delta !== 0 && (
            <em className={delta > 0 ? "up" : "down"}> {delta > 0 ? `+${delta}` : delta} since last change</em>
          )}
        </span>
        {isAnalyzing && <Loader2 size={14} className="jms-spin" aria-label="Updating score" />}
      </div>
      <div className="jms-editor-score-sections">
        {SECTION_ORDER.map((key) => {
          const sec = analysis.sections[key];
          if (!sec) return null;
          return (
            <span key={key} className={`jms-editor-chip tone-${sec.score == null ? "na" : scoreTone(sec.score)}`}>
              {sec.name} <b>{sec.score == null ? "N/A" : `${sec.score}%`}</b>
            </span>
          );
        })}
      </div>
    </div>
  );
}


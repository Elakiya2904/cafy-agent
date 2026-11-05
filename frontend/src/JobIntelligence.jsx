import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, Flag, Loader2, RefreshCw } from "lucide-react";
import "./jobIntelligence.css";

const API_BASE =
  typeof window !== "undefined" &&
  (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") &&
  window.location?.port &&
  ["5173", "5174", "3000"].includes(window.location?.port)
    ? "http://127.0.0.1:8000"
    : "";

const STATUS_CLASS = { officially_confirmed: "ji-official", publicly_reported: "ji-public", estimated: "ji-estimated", unknown: "ji-unknown" };
const STATUS_LABEL = { officially_confirmed: "Confirmed by employer", publicly_reported: "Reported by candidates", estimated: "Estimated", unknown: "Unconfirmed" };
const FIT_LABEL = { strong_match: "Strong match", match: "Match", needs_preparation: "Partial match", missing_evidence: "Not in your profile", unknown: "Unknown" };
const FIT_CLASS = { strong_match: "ji-official", match: "ji-public", needs_preparation: "ji-estimated", missing_evidence: "ji-missing", unknown: "ji-unknown" };
const SOURCE_TYPE = { job_posting: "This job advert", official_page: "Employer website", candidate_experience: "Candidate reports", public_article: "Article" };
const SCOPE = { role_specific: "For this role", company_wide: "Company-wide", role_family: "Similar roles" };

const fmtDate = (s) => (s ? new Date(s).toLocaleDateString(undefined, { dateStyle: "medium" }) : null);
const hostOf = (url) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
};
const unique = (items) => [...new Set(items)];

function Badge({ status }) {
  return <span className={`ji-badge ${STATUS_CLASS[status] || ""}`}>{STATUS_LABEL[status] || status}</span>;
}

function SourceLink({ url, type }) {
  const host = hostOf(url);
  if (!host) return <span>{SOURCE_TYPE[type] || "This job advert"}</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer">
      {host} <ExternalLink size={10} aria-hidden="true" />
    </a>
  );
}

function Stage({ stage, onReport }) {
  const [open, setOpen] = useState(false);
  const sources = useMemo(() => {
    const seen = new Set();
    return stage.sources.filter((s) => (seen.has(s.url) ? false : seen.add(s.url)));
  }, [stage.sources]);
  return (
    <li className="ji-stage">
      <div className="ji-stage-head">
        <span className="ji-stage-num">{stage.order}</span>
        <strong>{stage.stage}</strong>
        <Badge status={stage.status} />
        {SCOPE[stage.scope] && <span className="ji-muted">{SCOPE[stage.scope]}</span>}
        {stage.conflict && <span className="ji-badge ji-conflict">Sources disagree</span>}
        <button type="button" className="ji-link" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide" : "Details"}</button>
      </div>
      {open && (
        <div className="ji-stage-body">
          {stage.description && <p>{stage.description}</p>}
          {stage.assessment_type && <p><strong>Assessment:</strong> {stage.assessment_type}</p>}
          {stage.interview_format && <p><strong>Format:</strong> {stage.interview_format}</p>}
          <ul className="ji-list">
            {sources.map((s, i) => (
              <li key={i}>
                “{s.evidence}”
                <div className="ji-muted">
                  <SourceLink url={s.url} type={s.type} />
                  {s.published && ` · published ${fmtDate(s.published)}`}
                </div>
              </li>
            ))}
          </ul>
          <button type="button" className="ji-link" onClick={() => onReport(stage)}><Flag size={12} aria-hidden="true" /> Report an error</button>
        </div>
      )}
    </li>
  );
}

function Facts({ rows }) {
  const shown = rows.filter(([, value]) => value);
  if (!shown.length) return null;
  return (
    <dl className="ji-dl">
      {shown.map(([label, value]) => (
        <React.Fragment key={label}>
          <dt>{label}</dt><dd>{value}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

function BulletList({ title, items }) {
  if (!items?.length) return null;
  return (
    <>
      <h5>{title}</h5>
      <ul className="ji-list">{items.map((item, i) => <li key={i}>{typeof item === "string" ? item : item.text || ""}</li>)}</ul>
    </>
  );
}

export default function JobIntelligence({ job }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/job-intelligence/${encodeURIComponent(job.id)}${refresh ? "?refresh=true" : ""}`);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Job insights are unavailable right now.");
      setData(body);
    } catch (e) {
      setError(e.message || "Job insights are unavailable right now.");
    } finally {
      setLoading(false);
    }
  }, [job.id]);
  useEffect(() => { load(); }, [load]);

  const report = async (section, stage) => {
    const message = window.prompt(stage ? `What is wrong about “${stage.stage}”?` : "What is wrong in this section?");
    if (!message || message.trim().length < 3) return;
    const res = await fetch(`${API_BASE}/api/job-intelligence/${encodeURIComponent(job.id)}/report`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section, message, stage_key: stage?.stage_key || null }),
    });
    setNotice(res.ok ? "Thanks, we'll review it." : "Your report couldn't be sent. Please try again.");
  };

  if (loading) {
    return <div className="job-detail-panel ji-root"><p className="ji-muted"><Loader2 size={14} className="doc-spin" aria-hidden="true" /> Gathering insights on this role…</p></div>;
  }
  if (error) {
    return <div className="job-detail-panel ji-root"><p className="ji-error">{error}</p><button type="button" className="ji-btn" onClick={() => load()}>Try again</button></div>;
  }

  const { role_overview: ro, hiring_process: hp, candidate_compatibility: cc, sources } = data;
  const sourceItems = sources.items.filter((s) => hostOf(s.url) || s.type === "job_posting");

  return (
    <div className="job-detail-panel ji-root">
      <div className="ji-toolbar">
        <span className="ji-muted">Updated {fmtDate(data.generated_at)}</span>
        <button type="button" className="ji-btn" onClick={() => load(true)}><RefreshCw size={12} aria-hidden="true" /> Refresh</button>
      </div>
      {notice && <p className="ji-notice" role="status">{notice}</p>}

      <section className="ji-section">
        <h4>About the role</h4>
        <Facts rows={[
          ["Seniority", ro.seniority],
          ["Experience", ro.experience_requirements?.join("; ")],
          ["Salary", ro.salary],
        ]} />
        <BulletList title="Responsibilities" items={ro.responsibilities} />
        <BulletList title="Requirements" items={ro.qualifications} />
        {ro.required_skills?.length > 0 && (
          <>
            <h5>Skills mentioned</h5>
            <div className="ji-chips">{ro.required_skills.map((s) => <span key={s} className="ji-chip">{s}</span>)}</div>
          </>
        )}
        {ro.interpretation?.typical_day && (
          <>
            <p className="ji-tag ji-tag-ai">AI summary · not written by the employer</p>
            <p>{ro.interpretation.typical_day}</p>
            {ro.interpretation.why_role_exists && <p>{ro.interpretation.why_role_exists}</p>}
          </>
        )}
        {!ro.has_description && <p className="ji-muted">The employer's advert has the full details for this role.</p>}
      </section>

      <section className="ji-section">
        <h4>Hiring process</h4>
        {hp.available && hp.stages.length > 0 ? (
          <ol className="ji-stages">{hp.stages.map((s) => <Stage key={s.id} stage={s} onReport={(st) => report("hiring_process", st)} />)}</ol>
        ) : (
          <p className="ji-muted">This employer hasn't published its hiring process for this role yet.</p>
        )}
      </section>

      <section className="ji-section">
        <h4>How you match</h4>
        {!cc.available ? <p className="ji-muted">Add your CV to see how your experience lines up with this role.</p> : (
          <table className="ji-table">
            <thead><tr><th>Requirement</th><th>Match</th><th>From your profile</th></tr></thead>
            <tbody>{cc.rows.map((r, i) => <tr key={i}><td>{r.requirement}</td><td><span className={`ji-badge ${FIT_CLASS[r.status]}`}>{FIT_LABEL[r.status]}</span></td><td>{r.evidence}</td></tr>)}</tbody>
          </table>
        )}
      </section>

      {sourceItems.length > 0 && (
        <details className="ji-section ji-sources">
          <summary>Sources ({sourceItems.length})</summary>
          <ul className="ji-list">{sourceItems.map((s) => (
            <li key={s.url}>
              <SourceLink url={s.url} type={s.type} />{" "}
              <span className="ji-muted">· {SOURCE_TYPE[s.type] || s.type} · {unique(s.stages).join(", ")}</span>
            </li>
          ))}</ul>
          <button type="button" className="ji-link" onClick={() => report("sources")}><Flag size={12} aria-hidden="true" /> Report an error</button>
        </details>
      )}
    </div>
  );
}

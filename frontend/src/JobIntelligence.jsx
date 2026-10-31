import React, { useCallback, useEffect, useState } from "react";
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
const STATUS_LABEL = { officially_confirmed: "Officially confirmed", publicly_reported: "Publicly reported", estimated: "Estimated", unknown: "Unknown" };
const FIT_LABEL = { strong_match: "Strong match", match: "Match", needs_preparation: "Needs preparation", missing_evidence: "Missing evidence", unknown: "Unknown" };
const FIT_CLASS = { strong_match: "ji-official", match: "ji-public", needs_preparation: "ji-estimated", missing_evidence: "ji-missing", unknown: "ji-unknown" };
const SOURCE_TYPE = { job_posting: "Job posting", official_page: "Official company page", candidate_experience: "Candidate experience", public_article: "Public article" };
const SCOPE = { role_specific: "This role", company_wide: "Company-wide (may differ by role)", role_family: "Similar roles", unconfirmed_role: "Role not confirmed", unknown: "" };
const fmtDate = (s) => (s ? new Date(s).toLocaleDateString(undefined, { dateStyle: "medium" }) : null);

function Badge({ status }) {
  return <span className={`ji-badge ${STATUS_CLASS[status] || ""}`}>{STATUS_LABEL[status] || status}</span>;
}

function List({ items, empty }) {
  return items?.length ? <ul className="ji-list">{items.map((i, n) => <li key={n}>{typeof i === "string" ? i : JSON.stringify(i)}</li>)}</ul> : <p className="ji-muted">{empty}</p>;
}

function Stage({ stage, prep, onReport }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="ji-stage">
      <div className="ji-stage-head">
        <span className="ji-stage-num">{stage.order}</span>
        <strong>{stage.stage}</strong>
        <Badge status={stage.status} />
        {stage.scope && SCOPE[stage.scope] && <span className="ji-muted">{SCOPE[stage.scope]}</span>}
        {stage.conflict && <span className="ji-badge ji-conflict">Sources disagree</span>}
        <button type="button" className="ji-link" onClick={() => setOpen(!open)}>{open ? "Hide" : "Details & sources"}</button>
      </div>
      {open && (
        <div className="ji-stage-body">
          {stage.description && <p>{stage.description} <span className="ji-muted">(general description)</span></p>}
          {stage.assessment_type && <p><strong>Assessment type:</strong> {stage.assessment_type}</p>}
          {stage.interview_format && <p><strong>Typical format:</strong> {stage.interview_format} <span className="ji-muted">(general; not confirmed for this company)</span></p>}
          {prep && (
            <>
              <p><strong>Topics:</strong> {prep.topics.join(", ")}</p>
              <p><strong>Skills evaluated:</strong> {prep.skills.join(", ")}</p>
              <p><strong>How to prepare:</strong></p>
              <List items={prep.prep} empty="" />
            </>
          )}
          <p><strong>Evidence</strong></p>
          <ul className="ji-list">
            {stage.sources.map((s, i) => (
              <li key={i}>
                “{s.evidence}”
                <div className="ji-muted">
                  {SOURCE_TYPE[s.type] || s.type} ·{" "}
                  {s.url.startsWith("http") ? <a href={s.url} target="_blank" rel="noreferrer">{new URL(s.url).hostname} <ExternalLink size={10} /></a> : "job posting"}
                  {s.published && ` · published ${fmtDate(s.published)}`} · checked {fmtDate(s.last_verified)}
                  {s.link_status && s.link_status !== "ok" && ` · link ${s.link_status.replace(/_/g, " ")}`}
                </div>
              </li>
            ))}
          </ul>
          <button type="button" className="ji-link" onClick={() => onReport(stage)}><Flag size={12} /> Report incorrect information</button>
        </div>
      )}
    </li>
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
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not load job intelligence.");
      setData(body);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [job.id]);
  useEffect(() => { load(); }, [load]);

  const report = async (section, stage) => {
    const message = window.prompt(stage ? `What is incorrect about “${stage.stage}”?` : "What is incorrect in this section?");
    if (!message || message.trim().length < 3) return;
    const res = await fetch(`${API_BASE}/api/job-intelligence/${encodeURIComponent(job.id)}/report`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section, message, stage_key: stage?.stage_key || null }),
    });
    setNotice(res.ok ? "Thanks – your report was saved." : "Could not save your report.");
  };

  if (loading) return <div className="job-detail-panel ji-root"><p className="ji-muted"><Loader2 size={14} className="doc-spin" /> Researching this company and role… this can take up to a minute the first time.</p></div>;
  if (error) return <div className="job-detail-panel ji-root"><p className="ji-error">{error}</p><button type="button" className="ji-btn" onClick={() => load()}>Try again</button></div>;
  const { company_overview: co, role_overview: ro, hiring_process: hp, interview_preparation: prep, candidate_compatibility: cc, sources } = data;
  const prepByKey = Object.fromEntries(prep.stage_preparation.map((p) => [p.stage_key, p]));

  return (
    <div className="job-detail-panel ji-root">
      <div className="ji-toolbar">
        <span className="ji-muted">Generated {fmtDate(data.generated_at)}{data.reuse.company_reused && " · company research reused"}</span>
        <button type="button" className="ji-btn" onClick={() => load(true)}><RefreshCw size={12} /> Re-research</button>
      </div>
      {notice && <p className="ji-notice" role="status">{notice}</p>}

      <section className="ji-section">
        <h4>A. Company overview</h4>
        <p>{co.overview || <span className="ji-muted">Company description is not available.</span>}{co.overview_source && <span className="ji-muted"> (source: {co.overview_source})</span>}</p>
        <dl className="ji-dl">
          <dt>Company</dt><dd>{co.name}</dd>
          <dt>Industry</dt><dd>{co.industry || <em>Not available</em>}</dd>
          <dt>Headquarters</dt><dd>{co.headquarters || <em>Not available</em>}</dd>
          <dt>Locations hiring</dt><dd>{co.operating_locations.length ? co.operating_locations.join("; ") : <em>Not available</em>}</dd>
          <dt>Products / services</dt><dd>{co.products_and_services || <em>Not available</em>}</dd>
          <dt>Official website</dt><dd>{co.official_website ? <a href={co.official_website} target="_blank" rel="noreferrer">{co.official_website}</a> : <em>Could not be verified</em>}</dd>
          <dt>Careers page</dt><dd>{co.career_page ? <a href={co.career_page} target="_blank" rel="noreferrer">{co.career_page}</a> : <em>Not found</em>}</dd>
        </dl>
        {co.notes.map((n, i) => <p key={i} className="ji-muted">{n}</p>)}
        <button type="button" className="ji-link" onClick={() => report("company")}><Flag size={12} /> Report incorrect information</button>
      </section>

      <section className="ji-section">
        <h4>B. Role overview</h4>
        {!ro.has_description && <p className="ji-muted">This job has no description text, so role details are limited.</p>}
        <p className="ji-tag">Stated in the job description</p>
        <dl className="ji-dl">
          <dt>Title</dt><dd>{ro.title}</dd>
          <dt>Seniority</dt><dd>{ro.seniority || <em>Not stated</em>}</dd>
          <dt>Experience</dt><dd>{ro.experience_requirements.join("; ") || <em>Not stated</em>}</dd>
          <dt>Salary</dt><dd>{ro.salary || <em>Not stated</em>}</dd>
        </dl>
        <h5>Responsibilities</h5><List items={ro.responsibilities} empty="No responsibilities section could be identified." />
        <h5>Qualifications</h5><List items={ro.qualifications} empty="No qualifications section could be identified." />
        <h5>Required skills</h5>
        <div className="ji-chips">{ro.required_skills.length ? ro.required_skills.map((s) => <span key={s} className="ji-chip">{s}</span>) : <span className="ji-muted">None identified</span>}</div>
        {ro.sponsor && <p className="ji-muted">UK sponsor register: employer {ro.sponsor.employer_registered ? "is" : "is not"} listed. {ro.sponsor.note}</p>}
        {ro.interpretation && (
          <>
            <p className="ji-tag ji-tag-ai">AI interpretation – not stated by the employer</p>
            <p><strong>A typical day:</strong> {ro.interpretation.typical_day}</p>
            {ro.interpretation.why_role_exists && <p><strong>Why the role exists:</strong> {ro.interpretation.why_role_exists}</p>}
          </>
        )}
      </section>

      <section className="ji-section">
        <h4>C. Hiring process</h4>
        <p className="ji-muted">{hp.disclaimer}</p>
        {!hp.available ? (
          <p className="ji-unavailable">{hp.message}</p>
        ) : (
          <>
            <p><strong>{hp.known_stage_count}</strong> stage{hp.known_stage_count === 1 ? "" : "s"} with supporting evidence · {hp.assessments.length} assessment{hp.assessments.length === 1 ? "" : "s"} identified</p>
            <ol className="ji-stages">{hp.stages.map((s) => <Stage key={s.id} stage={s} prep={prepByKey[s.stage_key]} onReport={(st) => report("hiring_process", st)} />)}</ol>
            <p className="ji-muted">Stages not listed were not found in any source; that does not mean they don't exist.</p>
          </>
        )}
        {hp.notes.map((n, i) => <p key={i} className="ji-muted">{n}</p>)}
      </section>

      <section className="ji-section">
        <h4>D. Interview preparation</h4>
        <h5>Topics to study</h5><List items={prep.topics_to_study} empty="No specific topics identified." />
        <h5>Your projects and roles worth revising</h5>
        <List items={prep.projects_to_revise.map((p) => `${p.entry} (relevant to ${p.for_skill})`)} empty="Upload your résumé to see which of your projects are relevant." />
        <h5>Practice questions</h5>
        <p className="ji-muted">{prep.practice_questions_note}</p>
        <ul className="ji-list">{prep.practice_questions.map((q, i) => <li key={i}>{q.question} <span className="ji-muted">({q.type}{q.skill !== "behavioural" ? `, ${q.skill}` : ""})</span></li>)}</ul>
        <h5>Study resources</h5>
        <ul className="ji-list">{prep.resources.map((r) => <li key={r.url}><a href={r.url} target="_blank" rel="noreferrer">{r.title}</a></li>)}</ul>
        <p className="ji-muted">{prep.resources_note}</p>
      </section>

      <section className="ji-section">
        <h4>E. Candidate compatibility</h4>
        {!cc.available ? <p className="ji-muted">{cc.message}</p> : (
          <table className="ji-table">
            <thead><tr><th>Requirement</th><th>Your status</th><th>Evidence from your profile</th></tr></thead>
            <tbody>{cc.rows.map((r, i) => <tr key={i}><td>{r.requirement}</td><td><span className={`ji-badge ${FIT_CLASS[r.status]}`}>{FIT_LABEL[r.status]}</span></td><td>{r.evidence}</td></tr>)}</tbody>
          </table>
        )}
      </section>

      <section className="ji-section">
        <h4>F. Sources and reliability</h4>
        <p className="ji-muted">Labels: {Object.values(STATUS_LABEL).join(" · ")}. Estimated means the evidence is weaker or not specific to this role.</p>
        {sources.items.length === 0 ? <p className="ji-muted">No hiring-process sources were found.</p> : (
          <ul className="ji-list">{sources.items.map((s) => (
            <li key={s.url}>
              {s.url.startsWith("http") ? <a href={s.url} target="_blank" rel="noreferrer">{s.url}</a> : "Job posting"}{" "}
              <span className="ji-muted">— {SOURCE_TYPE[s.type] || s.type}{s.official ? " (official)" : ""}; supports {s.stages.join(", ")}; checked {fmtDate(s.last_verified)}{s.published ? `; published ${fmtDate(s.published)}` : ""}</span>
            </li>))}</ul>
        )}
        {sources.checked.filter((c) => c.status && c.status !== "ok").length > 0 && (
          <details><summary className="ji-muted">Sources that could not be used ({sources.checked.filter((c) => c.status !== "ok").length})</summary>
            <ul className="ji-list">{sources.checked.filter((c) => c.status !== "ok").map((c, i) => <li key={i} className="ji-muted">{c.url} — {String(c.status).replace(/_/g, " ")}{c.type === "rejected_wrong_company" ? " (not about this company)" : ""}</li>)}</ul>
          </details>
        )}
      </section>
    </div>
  );
}

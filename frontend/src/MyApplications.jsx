import React, { useCallback, useEffect, useState } from "react";
import { Check, ExternalLink, Loader2, RefreshCw, X } from "lucide-react";
import "./emailAgent.css";

const API_BASE =
  typeof window !== "undefined" &&
  (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") &&
  window.location?.port &&
  ["5173", "5174", "3000"].includes(window.location?.port)
    ? "http://127.0.0.1:8000"
    : "";
const BASE = `${API_BASE}/api/job-applications`;

export async function startApplication(job, allowDuplicate = false) {
  const res = await fetch(`${BASE}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: job.id, allow_duplicate: allowDuplicate }),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data: res.ok ? data : data.detail || {} };
}

async function api(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const err = new Error(typeof d === "string" ? d : d?.message || `Request failed (${res.status})`);
    err.data = typeof d === "object" ? d : {};
    throw err;
  }
  return data;
}

const label = (s) => (s || "—").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
const fmt = (s) => (s ? new Date(s).toLocaleDateString(undefined, { dateStyle: "medium" }) : "—");
const STATUS_CLASS = { submitted: "ea-pill-ok", submission_failed: "ea-pill-bad", confirmation_pending: "ea-pill-bad" };

function FieldRow({ f, appId, onResult, notify, locked }) {
  const [value, setValue] = useState(f.field_value || "");
  const [busy, setBusy] = useState(false);
  useEffect(() => setValue(f.field_value || ""), [f.field_value]);
  const run = async (fn) => {
    setBusy(true);
    try { onResult(await fn()); } catch (e) { notify(e.message, "error"); } finally { setBusy(false); }
  };
  if (f.category.startsWith("document:")) return null;
  const needsApproval = f.field_value && (f.field_source === "ai_suggestion" || f.category === "sensitive") && f.approval_status !== "approved";
  const long = f.field_type === "textarea" || (value || "").length > 80;
  return (
    <div className="ea-field-row">
      <div className="ea-card-head">
        <strong>{f.field_name}{f.required && " *"}</strong>
        <span className="ea-pill">{f.field_source === "ai_suggestion" ? "AI suggestion" : f.field_source === "candidate" ? "You" : f.field_source === "profile" ? "Profile" : "Needs input"}</span>
        {needsApproval && <span className="ea-pill ea-pill-bad">Awaiting review</span>}
      </div>
      {f.options?.length > 0 ? (
        <select value={value} disabled={locked} onChange={(e) => setValue(e.target.value)}>
          <option value="">Select…</option>
          {f.options.map((o) => <option key={o}>{o}</option>)}
        </select>
      ) : long ? (
        <textarea rows={5} value={value} disabled={locked} onChange={(e) => setValue(e.target.value)} />
      ) : (
        <input value={value} disabled={locked} onChange={(e) => setValue(e.target.value)} />
      )}
      {f.note && <p className="ea-muted">{f.note}</p>}
      {!locked && (
        <div className="ea-actions">
          <button className="ea-btn" disabled={busy || value === (f.field_value || "")} onClick={() => run(() => api(`/${appId}/fields/${f.id}`, { method: "PUT", body: JSON.stringify({ value }) }))}>Save my answer</button>
          {needsApproval && <button className="ea-btn" disabled={busy} onClick={() => run(() => api(`/${appId}/fields/${f.id}/approve`, { method: "POST" }))}><Check size={14} /> Accept</button>}
          {f.category === "open_question" && <button className="ea-btn" disabled={busy} onClick={() => run(() => api(`/${appId}/fields/${f.id}/regenerate`, { method: "POST" }))}><RefreshCw size={14} /> Regenerate</button>}
        </div>
      )}
    </div>
  );
}

function Detail({ appId, onClose, onChanged, notify }) {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState("");
  const load = useCallback(async () => {
    try { setD(await api(`/${appId}`)); } catch (e) { notify(e.message, "error"); }
  }, [appId, notify]);
  useEffect(() => { load(); const t = setInterval(load, 6000); return () => clearInterval(t); }, [load]);
  if (!d) return <div className="doc-card"><Loader2 size={16} className="doc-spin" /></div>;
  const app = d.application;
  const locked = ["submitted", "confirmation_pending", "cancelled"].includes(app.status);
  const apply = (r) => { setD((prev) => ({ ...prev, ...r })); onChanged(); };
  const act = async (name, path, msg) => {
    setBusy(name);
    try { const r = await api(`/${appId}${path}`, { method: "POST" }); if (r.fields) apply(r); else { await load(); onChanged(); } if (msg) notify(msg, "ok"); }
    catch (e) { notify(e.data?.blockers?.length ? `${e.message} ${e.data.blockers[0]}` : e.message, "error"); }
    finally { setBusy(""); load(); }
  };
  const resumeDoc = d.documents.find((x) => x.document_type === "resume");
  return (
    <div className="doc-card">
      <div className="ea-card-head">
        <h2 style={{ margin: 0 }}>{app.company} – {app.job_title}</h2>
        <span className={`ea-pill ${STATUS_CLASS[app.status] || ""}`}>{label(app.status)}</span>
        <span className="ea-spacer" />
        <button className="ea-btn" onClick={onClose}><X size={14} /> Close</button>
      </div>
      <p className="ea-muted">
        {app.ats_platform || "Unknown ATS"} · {app.location || "Location n/a"} ·{" "}
        {app.application_url && <a href={app.application_url} target="_blank" rel="noreferrer">Original posting <ExternalLink size={11} /></a>}
        {app.external_reference_id && ` · Ref ${app.external_reference_id}`}
      </p>
      {app.blocked_reason && <div className="ea-alert">Paused: {label(app.blocked_reason)}. Complete it on the application page, then <button className="ea-btn" onClick={() => act("resume", "/resume", "Cleared.")}>Continue</button></div>}
      {app.status === "confirmation_pending" && <div className="ea-alert">Cafy could not confirm the submission. If you received a confirmation email, mark it as submitted; otherwise retry.
        <div className="ea-actions"><button className="ea-btn" onClick={() => act("confirm", "/confirm-submitted", "Marked as submitted.")}>It went through</button><button className="ea-btn" onClick={() => act("retry", "/retry")}>Retry</button></div></div>}
      {app.status === "submission_failed" && <div className="ea-alert">Submission failed: {d.submissions[0]?.error_details || "unknown error"}.
        <div className="ea-actions"><button className="ea-btn" onClick={() => act("retry", "/retry")}>Retry</button></div></div>}

      {d.fields.length === 0 ? (
        <p className="ea-muted">Open the application page with the Cafy extension installed and click “Fill form”. Fields will appear here for review.</p>
      ) : (
        <>
          <h3>Review</h3>
          <table className="ea-table">
            <thead><tr><th>Field</th><th>Status</th></tr></thead>
            <tbody>{d.summary.map((s) => <tr key={s.field_id}><td>{s.field}</td><td>{s.status}</td></tr>)}</tbody>
          </table>
          {resumeDoc && (
            <div className="ea-field-row">
              <strong>Résumé upload</strong> <span className="ea-pill">{label(resumeDoc.upload_status)}</span>
              <p className="ea-muted">{resumeDoc.filename || "Stored résumé"} will only be uploaded with your permission.</p>
              {!locked && <button className="ea-btn" onClick={() => api(`/${appId}/documents/permission`, { method: "POST", body: JSON.stringify({ document_type: "resume", granted: !resumeDoc.permission_granted }) }).then(apply).catch((e) => notify(e.message, "error"))}>
                {resumeDoc.permission_granted ? "Revoke permission" : "Allow résumé upload"}</button>}
            </div>
          )}
          <h3>Edit information</h3>
          {d.fields.map((f) => <FieldRow key={f.id + (f.field_value || "")} f={f} appId={appId} onResult={apply} notify={notify} locked={locked} />)}
          {d.blockers.length > 0 && !locked && <><h3>Before you can submit</h3><ul className="ea-list">{d.blockers.map((b) => <li key={b}>{b}</li>)}</ul></>}
          {!locked && (
            <div className="ea-actions">
              <button className="ea-btn ea-btn-primary" disabled={!d.can_approve || d.approved || !!busy} onClick={() => act("approve", "/approve", "Approved. Click “Submit application” in the extension panel on the application page.")}>
                {busy === "approve" ? <Loader2 size={14} className="doc-spin" /> : <Check size={14} />} {d.approved ? "Approved – waiting for submit" : "Approve and Submit"}
              </button>
              <button className="ea-btn ea-btn-danger" onClick={() => window.confirm("Cancel this application?") && act("cancel", "/cancel", "Application cancelled.")}>Cancel Application</button>
            </div>
          )}
          {!locked && <p className="ea-muted">Cafy never submits on its own: after you approve, you press “Submit application” in the extension on the company's page, and Cafy then verifies the website's confirmation.</p>}
        </>
      )}
      <h3>History</h3>
      <ul className="ea-list">{d.history.slice().reverse().map((h, i) => <li key={i}>{new Date(h.ts).toLocaleString()} – {label(h.event)}</li>)}</ul>
    </div>
  );
}

export default function MyApplications() {
  const [rows, setRows] = useState([]);
  const [company, setCompany] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [open, setOpen] = useState(() => new URLSearchParams(window.location.search).get("application"));
  const [msg, setMsg] = useState(null);
  const notify = useCallback((text, kind = "ok") => setMsg({ text, kind }), []);

  const load = useCallback(async () => {
    const q = new URLSearchParams();
    if (company) q.set("company", company);
    if (from) q.set("date_from", from);
    if (to) q.set("date_to", to);
    try { setRows(await api(`?${q}`)); } catch (e) { notify(e.message, "error"); }
  }, [company, from, to, notify]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="content-container ea-root">
      <h1 className="page-title">My Applications</h1>
      <p className="page-subtitle">Applications started through Cafy. Review and approve each one before it is submitted.</p>
      {msg && <div className={`ea-toast ea-toast-${msg.kind}`} role="status">{msg.text}<button aria-label="Dismiss" onClick={() => setMsg(null)}><X size={14} /></button></div>}
      {open && <Detail appId={open} onClose={() => setOpen(null)} onChanged={load} notify={notify} />}
      <div className="doc-card">
        <div className="ea-actions" style={{ marginTop: 0 }}>
          <input className="ea-input" placeholder="Filter by company" value={company} onChange={(e) => setCompany(e.target.value)} />
          <label className="ea-muted">From <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
          <label className="ea-muted">To <input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        </div>
        {rows.length === 0 ? <div className="ea-empty">No applications yet. Click Apply on a job to start one.</div> : (
          <table className="ea-table">
            <thead><tr><th>Company</th><th>Job title</th><th>Location</th><th>Applied</th><th>Resume</th><th>Status</th><th>Reference</th><th>Source</th><th /></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}>
                <td>{r.company}{r.is_duplicate && <span className="ea-pill ea-pill-bad" title="Another application to the same job exists"> Duplicate</span>}</td>
                <td>{r.job_title}</td><td>{r.location || "—"}</td><td>{fmt(r.applied_at)}</td>
                <td>{(r.resume_version_id || "—").replace("original:", "")}</td>
                <td><span className={`ea-pill ${STATUS_CLASS[r.status] || ""}`}>{label(r.status)}</span></td>
                <td>{r.external_reference_id || "—"}</td><td>{r.ats_platform || "—"}</td>
                <td><button className="ea-btn" onClick={() => setOpen(r.id)}>{["draft", "in_progress", "ready_for_review"].includes(r.status) ? "Review Application" : "Details"}</button>
                  {r.application_url && <a className="ea-muted" href={r.application_url} target="_blank" rel="noreferrer"> Posting</a>}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </div>
    </div>
  );
}

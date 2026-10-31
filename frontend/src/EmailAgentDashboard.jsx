import React, { useCallback, useEffect, useRef, useState } from "react";
import { Check, Loader2, Mail, RefreshCw, Send, X } from "lucide-react";
import "./emailAgent.css";

// Mirrors App.jsx: talk to the FastAPI port directly when served from the Vite dev server.
const API_BASE =
  typeof window !== "undefined" &&
  (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") &&
  window.location?.port &&
  ["5173", "5174", "3000"].includes(window.location?.port)
    ? "http://127.0.0.1:8000"
    : "";
const BASE = `${API_BASE}/api/email-agent`;

async function api(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const err = new Error(typeof detail === "string" ? detail : detail?.message || `Request failed (${res.status})`);
    err.data = typeof detail === "object" ? detail : {};
    throw err;
  }
  return data;
}

const SECTIONS = [
  { id: "inbox", label: "Inbox Intelligence" },
  { id: "interviews", label: "Interview Management" },
  { id: "approvals", label: "Pending Approvals" },
  { id: "updates", label: "Application Updates" },
  { id: "history", label: "Email History" },
];

const label = (s) => (s || "—").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
const fmtDate = (s) => (s ? new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—");

function Empty({ children }) {
  return <div className="ea-empty">{children}</div>;
}

function DraftCard({ draft, onChange, notify }) {
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [toEmail, setToEmail] = useState(draft.to_email || "");
  const [busy, setBusy] = useState("");

  const run = async (kind, fn, okMsg) => {
    setBusy(kind);
    try {
      await fn();
      notify(okMsg, "ok");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy("");
      onChange();
    }
  };
  const payload = () => ({ method: "POST", body: JSON.stringify({ subject, body, to_email: toEmail || null }) });

  return (
    <div className="ea-card">
      <div className="ea-card-head">
        <strong>{draft.company || "Recruiter"}</strong>
        <span className="ea-pill">{label(draft.kind === "follow_up" ? "follow-up" : "reply")}</span>
        {draft.send_status === "failed" && <span className="ea-pill ea-pill-bad">Send failed</span>}
      </div>
      {draft.send_error && <div className="ea-alert">Not sent: {draft.send_error}</div>}
      <label className="ea-field">To
        <input value={toEmail} onChange={(e) => setToEmail(e.target.value)} placeholder="recruiter@company.com" />
      </label>
      <label className="ea-field">Subject
        <input value={subject} onChange={(e) => setSubject(e.target.value)} />
      </label>
      <label className="ea-field">Suggested response
        <textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
      </label>
      <p className="ea-muted">Nothing is sent until you approve it.</p>
      <div className="ea-actions">
        <button className="ea-btn ea-btn-primary" disabled={!!busy} onClick={() => run("send", () => api(`/drafts/${draft.id}/approve`, payload()), "Email sent.")}>
          {busy === "send" ? <Loader2 size={14} className="doc-spin" /> : <Send size={14} />} Approve and Send
        </button>
        <button className="ea-btn" disabled={!!busy} onClick={() => run("save", () => api(`/drafts/${draft.id}`, { method: "PUT", body: JSON.stringify({ subject, body, to_email: toEmail || null }) }), "Draft saved.")}>
          Edit Response (save)
        </button>
        <button className="ea-btn ea-btn-danger" disabled={!!busy} onClick={() => run("reject", () => api(`/drafts/${draft.id}/reject`, { method: "POST" }), "Draft rejected.")}>
          <X size={14} /> Reject Draft
        </button>
      </div>
    </div>
  );
}

function InterviewCard({ iv, onChange, notify }) {
  const [picked, setPicked] = useState(() => new Set());
  const [edit, setEdit] = useState({ interview_date: "", interview_time: "", duration_minutes: "", meeting_link: "" });
  const [busy, setBusy] = useState("");
  const slots = iv.proposed_slots || [];
  const chosen = slots.filter((_, i) => picked.has(i));

  const run = async (kind, fn, okMsg) => {
    setBusy(kind);
    try {
      await fn();
      notify(okMsg, "ok");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy("");
      onChange();
    }
  };
  const reply = (mode, slotList) => () =>
    api(`/interviews/${iv.id}/reply`, { method: "POST", body: JSON.stringify({ mode, slots: slotList }) });
  const confirm = () => {
    const body = Object.fromEntries(Object.entries(edit).filter(([, v]) => v !== "").map(([k, v]) => [k, k === "duration_minutes" ? Number(v) : v]));
    return api(`/interviews/${iv.id}/confirm`, { method: "POST", body: JSON.stringify(body) });
  };
  const hasConflict = (iv.conflicts || []).length > 0;

  return (
    <div className="ea-card">
      <div className="ea-card-head">
        <strong>{iv.company} – {iv.job_title}</strong>
        <span className={`ea-pill ${iv.scheduling_status === "scheduled" ? "ea-pill-ok" : hasConflict || iv.scheduling_status === "calendar_failed" ? "ea-pill-bad" : ""}`}>{label(iv.scheduling_status)}</span>
      </div>
      <dl className="ea-dl">
        <dt>Date</dt><dd>{iv.interview_date || "Not stated"}</dd>
        <dt>Time</dt><dd>{iv.interview_time ? `${iv.interview_time} (${iv.timezone}${iv.timezone_assumed ? ", assumed – please verify" : ""})` : "Not stated"}</dd>
        <dt>Duration</dt><dd>{iv.duration_minutes ? `${iv.duration_minutes} min` : "Not stated"}</dd>
        <dt>Type</dt><dd>{iv.interview_type || "Not stated"}</dd>
        <dt>Link</dt><dd>{iv.meeting_link ? <a href={iv.meeting_link} target="_blank" rel="noreferrer">{iv.platform || "Join"}</a> : "Not stated"}</dd>
        <dt>Recruiter</dt><dd>{[iv.recruiter_name, iv.recruiter_email].filter(Boolean).join(" · ") || "—"}</dd>
      </dl>
      {hasConflict && <div className="ea-alert">Conflicts with your calendar: {iv.conflicts.map((c) => `${fmtDate(c.start)}–${fmtDate(c.end)}`).join("; ")}</div>}
      {iv.calendar_error && <div className="ea-alert">{iv.calendar_error}</div>}
      {iv.missing_fields?.length > 0 && <p className="ea-muted">Missing from the email: {iv.missing_fields.map(label).join(", ")}</p>}

      {slots.length > 0 && iv.scheduling_status !== "scheduled" && (
        <div className="ea-slots">
          <p className="ea-muted">Free slots from your calendar – select the ones to offer:</p>
          {slots.map((s, i) => (
            <label key={s.start} className="ea-check">
              <input type="checkbox" checked={picked.has(i)} onChange={() => setPicked((p) => { const n = new Set(p); n.has(i) ? n.delete(i) : n.add(i); return n; })} />
              {s.label}
            </label>
          ))}
        </div>
      )}

      {iv.scheduling_status !== "scheduled" && (
        <>
          <div className="ea-grid">
            {["interview_date", "interview_time", "duration_minutes", "meeting_link"].map((k) => (
              (!iv[k] || k === "meeting_link") && (
                <label key={k} className="ea-field">{label(k)}
                  <input type={k === "interview_date" ? "date" : k === "interview_time" ? "time" : k === "duration_minutes" ? "number" : "text"}
                    value={edit[k]} onChange={(e) => setEdit({ ...edit, [k]: e.target.value })} />
                </label>
              )
            ))}
          </div>
          <div className="ea-actions">
            {slots.length > 0 && (
              <button className="ea-btn" disabled={!!busy || !chosen.length} onClick={() => run("avail", reply(hasConflict ? "reschedule" : "availability", chosen), "Draft ready for your approval.")}>
                Draft reply with selected slots
              </button>
            )}
            {iv.interview_date && iv.interview_time && !hasConflict && (
              <button className="ea-btn" disabled={!!busy} onClick={() => run("accept", reply("accept"), "Acceptance drafted – review it in Pending Approvals.")}>
                Draft acceptance
              </button>
            )}
            <button className="ea-btn ea-btn-primary" disabled={!!busy} onClick={() => run("confirm", confirm, "Interview added to your calendar with reminders.")}>
              {busy === "confirm" ? <Loader2 size={14} className="doc-spin" /> : <Check size={14} />} Confirm &amp; add to calendar
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default function EmailAgentDashboard({ pipelineJobs = [] }) {
  const [data, setData] = useState(null);
  const [section, setSection] = useState("inbox");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState(null);
  const [syncing, setSyncing] = useState("");

  const notify = useCallback((text, kind = "ok") => setMsg({ text, kind }), []);
  // The parent passes a fresh array each render; key the loader on the job ids instead.
  const jobsRef = useRef(pipelineJobs);
  jobsRef.current = pipelineJobs;
  const jobsKey = pipelineJobs.map((j) => j.id).join(",");

  const load = useCallback(async () => {
    try {
      if (jobsRef.current.length) {
        await api("/applications/sync", {
          method: "POST",
          body: JSON.stringify({ applications: jobsRef.current.map((j) => ({ job_id: j.id, company: j.company, job_title: j.title })) }),
        });
      }
      setData(await api("/dashboard"));
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [jobsKey, notify]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("emailAgent") === "connected") notify("Email account connected.", "ok");
    if (q.get("emailAgent") === "error") notify(`Could not connect: ${q.get("reason") || "unknown error"}`, "error");
  }, [notify]);

  const connect = async (provider) => {
    try {
      const { auth_url } = await api(`/oauth/${provider}/start`);
      window.location.href = auth_url;
    } catch (e) {
      notify(e.message, "error");
    }
  };
  const sync = async (id) => {
    setSyncing(id);
    try {
      const s = await api(`/accounts/${id}/sync`, { method: "POST" });
      notify(`Synced: ${s.job_related} job-related email(s), ${s.duplicates} duplicate(s) skipped.`, "ok");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setSyncing("");
      load();
    }
  };
  const disconnect = async (id) => {
    if (!window.confirm("Disconnect this account and revoke Cafy's access?")) return;
    try {
      const r = await api(`/accounts/${id}`, { method: "DELETE" });
      notify(r.remote_revoked ? "Account disconnected and access revoked." : "Account disconnected. Remote revocation could not be confirmed – also remove Cafy in your provider's security settings.", r.remote_revoked ? "ok" : "error");
    } catch (e) {
      notify(e.message, "error");
    }
    load();
  };
  const scanFollowUps = async () => {
    try {
      const d = await api("/follow-ups/scan", { method: "POST" });
      notify(d.length ? `${d.length} follow-up draft(s) ready for approval.` : "No follow-ups needed right now.", "ok");
      load();
    } catch (e) {
      notify(e.message, "error");
    }
  };
  const addFollowUpToCalendar = async (recordId) => {
    try {
      await api(`/follow-ups/${recordId}/calendar`, { method: "POST" });
      notify("Follow-up reminder added to your calendar.", "ok");
    } catch (e) {
      notify(e.message, "error");
    }
    load();
  };
  const confirmMatch = async (messageId, applicationId) => {
    try {
      await api(`/messages/${messageId}/confirm-match`, { method: "POST", body: JSON.stringify({ application_id: applicationId }) });
    } catch (e) {
      notify(e.message, "error");
    }
    load();
  };

  if (loading) return <div className="content-container"><Empty><Loader2 size={16} className="doc-spin" /> Loading Email Agent…</Empty></div>;
  const d = data || { accounts: [], inbox: [], interviews: [], pending_approvals: [], application_updates: {}, history: { sent: [], failed: [], received: [], follow_ups: [] }, needs_confirmation: [], applications: [], notifications: [], providers: {} };
  const active = d.accounts.filter((a) => a.status !== "disconnected");
  const unread = d.notifications.filter((n) => !n.is_read);
  const counts = { approvals: d.pending_approvals.length, interviews: d.interviews.length, inbox: d.inbox.length };

  return (
    <div className="content-container ea-root">
      <h1 className="page-title">Email Agent</h1>
      <p className="page-subtitle">Tracks recruiter email, prepares replies and schedules interviews. You approve anything that gets sent.</p>

      {msg && <div className={`ea-toast ea-toast-${msg.kind}`} role="status">{msg.text}<button aria-label="Dismiss" onClick={() => setMsg(null)}><X size={14} /></button></div>}

      <div className="doc-card">
        <h2>Connected accounts</h2>
        {active.length === 0 && <p className="ea-muted">Connect Gmail or Outlook (OAuth – Cafy never sees your password). The agent reads job-related mail, drafts replies and checks your calendar.</p>}
        {active.map((a) => (
          <div key={a.id} className="ea-account">
            <Mail size={16} /> <strong>{a.email}</strong> <span className="ea-pill">{label(a.provider)}</span>
            <span className={`ea-pill ${a.status === "connected" ? "ea-pill-ok" : "ea-pill-bad"}`}>{label(a.status)}</span>
            <span className="ea-muted">{a.last_synced_at ? `Last sync ${fmtDate(a.last_synced_at)}` : "Not synced yet"}</span>
            {a.status === "expired" && <span className="ea-alert-inline">Authorization expired – reconnect.</span>}
            <span className="ea-spacer" />
            <button className="ea-btn" disabled={syncing === a.id || a.status !== "connected"} onClick={() => sync(a.id)}>
              {syncing === a.id ? <Loader2 size={14} className="doc-spin" /> : <RefreshCw size={14} />} Sync now
            </button>
            <button className="ea-btn ea-btn-danger" onClick={() => disconnect(a.id)}>Disconnect</button>
          </div>
        ))}
        <div className="ea-actions">
          {["gmail", "outlook"].map((p) => (
            <button key={p} className="ea-btn" onClick={() => connect(p)} title={d.providers[p] ? "" : "OAuth credentials are not configured on the server"}>
              Connect {label(p)}
            </button>
          ))}
          <button className="ea-btn" onClick={scanFollowUps} disabled={!active.length}>Scan for follow-ups</button>
        </div>
      </div>

      {unread.length > 0 && (
        <div className="doc-card">
          <h2>Needs your attention</h2>
          <ul className="ea-list">{unread.slice(0, 5).map((n) => <li key={n.id}>{n.message}</li>)}</ul>
          <button className="ea-btn" onClick={() => api("/notifications/read", { method: "POST" }).then(load)}>Mark as read</button>
        </div>
      )}

      <div className="ea-tabs" role="tablist">
        {SECTIONS.map((s) => (
          <button key={s.id} role="tab" aria-selected={section === s.id} className={section === s.id ? "ea-tab ea-tab-active" : "ea-tab"} onClick={() => setSection(s.id)}>
            {s.label}{counts[s.id] > 0 && <span className="ea-badge">{counts[s.id]}</span>}
          </button>
        ))}
      </div>

      {section === "inbox" && (
        <div className="doc-card">
          {d.needs_confirmation.length > 0 && (
            <div className="ea-confirm">
              <h2>Confirm which application</h2>
              {d.needs_confirmation.map((m) => (
                <div key={m.id} className="ea-confirm-row">
                  <div><strong>{m.subject || "(no subject)"}</strong><div className="ea-muted">{m.sender} · {label(m.category) || "Unclassified"}</div></div>
                  <select defaultValue="" onChange={(e) => e.target.value && confirmMatch(m.id, e.target.value)}>
                    <option value="" disabled>Select application…</option>
                    {d.applications.map((a) => <option key={a.id} value={a.id}>{a.company} – {a.job_title}</option>)}
                  </select>
                  <button className="ea-btn" onClick={() => confirmMatch(m.id, null)}>Not job-related</button>
                </div>
              ))}
            </div>
          )}
          <h2>Job-related emails</h2>
          {d.inbox.length === 0 ? <Empty>No job-related emails yet. Connect an account and sync.</Empty> : (
            <table className="ea-table">
              <thead><tr><th>Company</th><th>Job title</th><th>Category</th><th>Received</th><th>Status</th></tr></thead>
              <tbody>{d.inbox.map((m) => (
                <tr key={m.id}>
                  <td>{m.company || <em>Unmatched</em>}</td><td>{m.job_title || "—"}</td>
                  <td>{label(m.category)}{m.confidence != null && <span className="ea-muted"> {Math.round(m.confidence * 100)}%</span>}</td>
                  <td>{fmtDate(m.received_at)}</td><td>{label(m.application_status || m.processing_status)}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      )}

      {section === "interviews" && (
        d.interviews.length === 0 ? <div className="doc-card"><Empty>No interviews detected yet.</Empty></div>
          : d.interviews.map((iv) => <InterviewCard key={iv.id + iv.updated_at} iv={iv} onChange={load} notify={notify} />)
      )}

      {section === "approvals" && (
        d.pending_approvals.length === 0 ? <div className="doc-card"><Empty>Nothing waiting for approval.</Empty></div>
          : d.pending_approvals.map((dr) => <DraftCard key={dr.id + (dr.body || "").length} draft={dr} onChange={load} notify={notify} />)
      )}

      {section === "updates" && (
        <div className="doc-card">
          {[["under_review", "Under review"], ["assessments", "Assessment invitations"], ["interviews", "Interview invitations"], ["rejections", "Rejections"], ["offers", "Offers received"]].map(([k, title]) => (
            <div key={k} className="ea-group">
              <h3>{title} <span className="ea-badge">{(d.application_updates[k] || []).length}</span></h3>
              {(d.application_updates[k] || []).length === 0 ? <p className="ea-muted">None</p>
                : <ul className="ea-list">{d.application_updates[k].map((a) => <li key={a.id}>{a.company} – {a.job_title} <span className="ea-muted">updated {fmtDate(a.updated_at)}</span></li>)}</ul>}
            </div>
          ))}
        </div>
      )}

      {section === "history" && (
        <div className="doc-card">
          <h2>Sent</h2>
          {d.history.sent.length === 0 ? <p className="ea-muted">No emails sent through Cafy yet.</p>
            : <ul className="ea-list">{d.history.sent.map((s) => <li key={s.id}>{fmtDate(s.sent_at)} → {s.to_email}: {s.subject} <span className="ea-pill">{label(s.kind)}</span></li>)}</ul>}
          {d.history.failed.length > 0 && <>
            <h2>Failed (not sent)</h2>
            <ul className="ea-list">{d.history.failed.map((s) => <li key={s.id}>{s.subject} – {s.send_error}</li>)}</ul>
          </>}
          <h2>Received</h2>
          {d.history.received.length === 0 ? <p className="ea-muted">Nothing yet.</p>
            : <ul className="ea-list">{d.history.received.slice(0, 20).map((m) => <li key={m.id}>{fmtDate(m.received_at)} · {m.sender}: {m.subject}</li>)}</ul>}
          <h2>Follow-up history</h2>
          {d.history.follow_ups.length === 0 ? <p className="ea-muted">No follow-ups yet.</p>
            : <ul className="ea-list">{d.history.follow_ups.map((f) => (
              <li key={f.id}>
                {f.follow_up_date} – {label(f.approval_status)}{f.sent_at ? ` (sent ${fmtDate(f.sent_at)})` : ""}
                {f.calendar_event_id && <span className="ea-pill"> On calendar{f.reminder_at ? ` · ${fmtDate(f.reminder_at)}` : ""}</span>}
                {f.approval_status === "pending" && !f.calendar_event_id && (
                  <button className="ea-btn" onClick={() => addFollowUpToCalendar(f.id)}>Add to calendar</button>
                )}
                {f.calendar_error && !f.calendar_event_id && <span className="ea-muted"> Calendar: {f.calendar_error}</span>}
              </li>))}</ul>}
        </div>
      )}
    </div>
  );
}

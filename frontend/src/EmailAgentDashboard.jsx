/**
 * Dashboard for connected inboxes, recruiter messages, interviews, and drafts.
 * Provides synchronization controls and review/approval actions for email drafts.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bell,
  CalendarCheck,
  CalendarClock,
  Check,
  CheckCheck,
  Clock3,
  History,
  Inbox,
  KanbanSquare,
  Loader2,
  Mail,
  PenLine,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import "./emailAgent.css";
import NangoConnectPanel from "./NangoConnectPanel.jsx";
import "./nangoConnect.css";

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
  { id: "inbox", label: "Inbox Intelligence", hint: "Job-related emails", icon: Inbox },
  { id: "approvals", label: "Pending Approvals", hint: "Drafts to review", icon: PenLine },
  { id: "interviews", label: "Interview Management", hint: "Scheduling & slots", icon: CalendarClock },
  { id: "updates", label: "Application Updates", hint: "Status by stage", icon: KanbanSquare },
  { id: "history", label: "Email History", hint: "Sent, received, follow-ups", icon: History },
];

const UPDATE_STAGES = [
  ["under_review", "Under review", "neutral"],
  ["assessments", "Assessments", "info"],
  ["interviews", "Interviews", "brand"],
  ["offers", "Offers", "ok"],
  ["rejections", "Rejections", "bad"],
];

const label = (s) => (s || "—").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
const fmtDate = (s) => (s ? new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—");
const initial = (s) => (s || "?").trim().charAt(0).toUpperCase() || "?";

function relTime(s) {
  if (!s) return "—";
  const diff = Date.now() - new Date(s).getTime();
  if (!Number.isFinite(diff)) return "—";
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 7) return `${d}d ago`;
  return new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** Maps an email category to a badge tone. */
function categoryTone(category = "") {
  const c = category.toLowerCase();
  if (/offer/.test(c)) return "ok";
  if (/reject|declin|unsuccess/.test(c)) return "bad";
  if (/interview/.test(c)) return "brand";
  if (/assess|test|challenge/.test(c)) return "info";
  if (/recruit|outreach|inquir/.test(c)) return "warn";
  return "neutral";
}

function Empty({ icon: Icon = Inbox, title, children }) {
  return (
    <div className="ea-empty">
      <span className="ea-empty-icon"><Icon size={20} /></span>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

function PanelHead({ title, subtitle, children }) {
  return (
    <div className="ea-panel-head">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {children && <div className="ea-panel-tools">{children}</div>}
    </div>
  );
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
    <article className="ea-card ea-draft">
      <header className="ea-card-head">
        <span className="ea-avatar-sq">{initial(draft.company)}</span>
        <div className="ea-card-title">
          <strong>{draft.company || "Recruiter"}</strong>
          <span>{draft.kind === "follow_up" ? "Follow-up to send" : "Reply to recruiter"}</span>
        </div>
        <span className={`ea-pill ${draft.kind === "follow_up" ? "tone-info" : "tone-brand"}`}>{draft.kind === "follow_up" ? "Follow-up" : "Reply"}</span>
        {draft.send_status === "failed" && <span className="ea-pill tone-bad">Send failed</span>}
      </header>
      {draft.send_error && <div className="ea-alert">Not sent: {draft.send_error}</div>}

      <div className="ea-composer">
        <label className="ea-composer-row">
          <span>To</span>
          <input value={toEmail} onChange={(e) => setToEmail(e.target.value)} placeholder="recruiter@company.com" />
        </label>
        <label className="ea-composer-row">
          <span>Subject</span>
          <input value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <div className="ea-composer-ai"><Sparkles size={13} /> AI draft · edit freely before approving</div>
        <textarea className="ea-composer-body" aria-label="Suggested response" rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
      </div>

      <footer className="ea-card-foot">
        <span className="ea-muted"><ShieldCheck size={13} /> Nothing is sent until you approve it.</span>
        <div className="ea-actions">
          <button className="ea-btn ea-btn-ghost-danger" disabled={!!busy} onClick={() => run("reject", () => api(`/drafts/${draft.id}/reject`, { method: "POST" }), "Draft rejected.")}>
            <X size={14} /> Reject
          </button>
          <button className="ea-btn" disabled={!!busy} onClick={() => run("save", () => api(`/drafts/${draft.id}`, { method: "PUT", body: JSON.stringify({ subject, body, to_email: toEmail || null }) }), "Draft saved.")}>
            {busy === "save" ? <Loader2 size={14} className="doc-spin" /> : <PenLine size={14} />} Save edits
          </button>
          <button className="ea-btn ea-btn-primary" disabled={!!busy} onClick={() => run("send", () => api(`/drafts/${draft.id}/approve`, payload()), "Email sent.")}>
            {busy === "send" ? <Loader2 size={14} className="doc-spin" /> : <Send size={14} />} Approve &amp; Send
          </button>
        </div>
      </footer>
    </article>
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
  const scheduled = iv.scheduling_status === "scheduled";
  const statusTone = scheduled ? "tone-ok" : hasConflict || iv.scheduling_status === "calendar_failed" ? "tone-bad" : "tone-warn";

  const facts = [
    ["Date", iv.interview_date || "Not stated"],
    ["Time", iv.interview_time ? `${iv.interview_time} ${iv.timezone || ""}${iv.timezone_assumed ? " (assumed)" : ""}` : "Not stated"],
    ["Duration", iv.duration_minutes ? `${iv.duration_minutes} min` : "Not stated"],
    ["Format", iv.interview_type || "Not stated"],
    ["Meeting", iv.meeting_link ? <a href={iv.meeting_link} target="_blank" rel="noreferrer">{iv.platform || "Join link"}</a> : "Not stated"],
    ["Recruiter", [iv.recruiter_name, iv.recruiter_email].filter(Boolean).join(" · ") || "—"],
  ];

  return (
    <article className="ea-card">
      <header className="ea-card-head">
        <span className="ea-avatar-sq">{initial(iv.company)}</span>
        <div className="ea-card-title">
          <strong>{iv.company}</strong>
          <span>{iv.job_title}</span>
        </div>
        <span className={`ea-pill ${statusTone}`}>{label(iv.scheduling_status)}</span>
      </header>

      <dl className="ea-facts">
        {facts.map(([k, v]) => (
          <div key={k} className={v === "Not stated" ? "missing" : ""}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {iv.timezone_assumed && iv.interview_time && <p className="ea-muted">Time zone was assumed from your settings. Please verify it with the recruiter.</p>}
      {hasConflict && <div className="ea-alert">Conflicts with your calendar: {iv.conflicts.map((c) => `${fmtDate(c.start)}–${fmtDate(c.end)}`).join("; ")}</div>}
      {iv.calendar_error && <div className="ea-alert">{iv.calendar_error}</div>}
      {iv.missing_fields?.length > 0 && <p className="ea-muted">Missing from the email: {iv.missing_fields.map(label).join(", ")}</p>}

      {slots.length > 0 && !scheduled && (
        <div className="ea-slots">
          <span className="ea-section-label">Free slots from your calendar · select the ones to offer</span>
          <div className="ea-slot-chips">
            {slots.map((s, i) => {
              const on = picked.has(i);
              return (
                <button
                  key={s.start}
                  type="button"
                  className={`ea-slot ${on ? "on" : ""}`}
                  aria-pressed={on}
                  onClick={() => setPicked((p) => { const n = new Set(p); n.has(i) ? n.delete(i) : n.add(i); return n; })}
                >
                  {on ? <Check size={13} /> : <Clock3 size={13} />} {s.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {!scheduled && (
        <>
          {["interview_date", "interview_time", "duration_minutes", "meeting_link"].some((k) => !iv[k] || k === "meeting_link") && (
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
          )}
          <footer className="ea-card-foot">
            <span />
            <div className="ea-actions">
              {slots.length > 0 && (
                <button className="ea-btn" disabled={!!busy || !chosen.length} onClick={() => run("avail", reply(hasConflict ? "reschedule" : "availability", chosen), "Draft ready for your approval.")}>
                  Draft reply with {chosen.length || ""} slot{chosen.length === 1 ? "" : "s"}
                </button>
              )}
              {iv.interview_date && iv.interview_time && !hasConflict && (
                <button className="ea-btn" disabled={!!busy} onClick={() => run("accept", reply("accept"), "Acceptance drafted – review it in Pending Approvals.")}>
                  Draft acceptance
                </button>
              )}
              <button className="ea-btn ea-btn-primary" disabled={!!busy} onClick={() => run("confirm", confirm, "Interview added to your calendar with reminders.")}>
                {busy === "confirm" ? <Loader2 size={14} className="doc-spin" /> : <CalendarCheck size={14} />} Confirm &amp; add to calendar
              </button>
            </div>
          </footer>
        </>
      )}
    </article>
  );
}

function InboxPanel({ d, confirmMatch }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const categories = useMemo(() => {
    const counts = new Map();
    d.inbox.forEach((m) => {
      const c = m.category || "uncategorised";
      counts.set(c, (counts.get(c) || 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [d.inbox]);
  const rows = d.inbox.filter((m) => {
    if (category !== "all" && (m.category || "uncategorised") !== category) return false;
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return [m.company, m.job_title, m.subject, m.sender, m.category].some((v) => (v || "").toLowerCase().includes(q));
  });

  return (
    <>
      {d.needs_confirmation.length > 0 && (
        <div className="ea-confirm">
          <div className="ea-confirm-head">
            <Bell size={15} />
            <div>
              <strong>Confirm which application these belong to</strong>
              <span>{d.needs_confirmation.length} email{d.needs_confirmation.length === 1 ? "" : "s"} couldn't be matched automatically.</span>
            </div>
          </div>
          {d.needs_confirmation.map((m) => (
            <div key={m.id} className="ea-confirm-row">
              <div className="ea-confirm-text">
                <strong>{m.subject || "(no subject)"}</strong>
                <span>{m.sender} · {label(m.category) || "Unclassified"}</span>
              </div>
              <select defaultValue="" onChange={(e) => e.target.value && confirmMatch(m.id, e.target.value)} aria-label="Match to application">
                <option value="" disabled>Select application…</option>
                {d.applications.map((a) => <option key={a.id} value={a.id}>{a.company} – {a.job_title}</option>)}
              </select>
              <button className="ea-btn" onClick={() => confirmMatch(m.id, null)}>Not job-related</button>
            </div>
          ))}
        </div>
      )}

      <PanelHead title="Job-related emails" subtitle={`${d.inbox.length} email${d.inbox.length === 1 ? "" : "s"} classified from your connected inboxes`}>
        <label className="ea-search">
          <Search size={15} />
          <input type="search" placeholder="Search company, role, subject…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search emails" />
        </label>
      </PanelHead>

      {categories.length > 1 && (
        <div className="ea-filter-chips" role="group" aria-label="Filter by category">
          <button type="button" className={category === "all" ? "on" : ""} aria-pressed={category === "all"} onClick={() => setCategory("all")}>
            All <span>{d.inbox.length}</span>
          </button>
          {categories.map(([c, n]) => (
            <button key={c} type="button" className={category === c ? "on" : ""} aria-pressed={category === c} onClick={() => setCategory(c)}>
              {label(c)} <span>{n}</span>
            </button>
          ))}
        </div>
      )}

      {d.inbox.length === 0 ? (
        <Empty icon={Mail} title="No job-related emails yet">Connect an account above and sync to start classifying recruiter emails.</Empty>
      ) : rows.length === 0 ? (
        <Empty icon={Search} title="No emails match">Try a different search or category.</Empty>
      ) : (
        <ul className="ea-mail-list">
          {rows.map((m) => (
            <li key={m.id} className="ea-mail-row">
              <span className="ea-avatar-sq">{initial(m.company || m.sender)}</span>
              <div className="ea-mail-main">
                <div className="ea-mail-line">
                  <strong>{m.company || <em>Unmatched</em>}</strong>
                  {m.job_title && <span className="ea-mail-role">{m.job_title}</span>}
                </div>
                {m.subject && <div className="ea-mail-subject">{m.subject}</div>}
              </div>
              <div className="ea-mail-meta">
                <span className={`ea-pill tone-${categoryTone(m.category)}`}>
                  {label(m.category)}
                  {m.confidence != null && <small>{Math.round(m.confidence * 100)}%</small>}
                </span>
                <span className="ea-mail-status">{label(m.application_status || m.processing_status)}</span>
              </div>
              <time className="ea-mail-time" dateTime={m.received_at} title={fmtDate(m.received_at)}>{relTime(m.received_at)}</time>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function EmailAgentDashboard({ pipelineJobs = [] }) {
  const [data, setData] = useState(null);
  const [section, setSection] = useState("inbox");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState(null);
  const [syncing, setSyncing] = useState("");
  const [showRules, setShowRules] = useState(false);

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

  const handleNangoStatusChange = useCallback((connections) => {
    if (connections.length > 0) load();
  }, [load]);

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
      const result = await api(`/accounts/${id}/sync`, { method: "POST" });
      notify(`Synced: ${result.job_related} job-related email(s), ${result.duplicates} duplicate(s) skipped.`, "ok");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setSyncing("");
      load();
    }
  };
  const syncAll = async () => {
    if (!connectedAccounts.length) return;
    setSyncing("all");
    const results = await Promise.allSettled(connectedAccounts.map((account) => api(`/accounts/${account.id}/sync`, { method: "POST" })));
    const succeeded = results.filter((result) => result.status === "fulfilled");
    const failed = results.filter((result) => result.status === "rejected");
    setSyncing("");
    if (failed.length) {
      notify(`${succeeded.length} account(s) synced; ${failed.length} failed: ${failed[0].reason.message}`, "error");
    } else {
      notify(`Synced ${succeeded.length} email account(s).`, "ok");
    }
    load();
  };
  const disconnect = async (id) => {
    if (!window.confirm("Disconnect this account and revoke Cafy's access?")) return;
    try {
      const result = await api(`/accounts/${id}`, { method: "DELETE" });
      notify(result.remote_revoked ? "Account disconnected and access revoked." : "Account disconnected. Remote revocation could not be confirmed.", result.remote_revoked ? "ok" : "error");
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

  if (loading) {
    return (
      <div className="content-container ea-root ea-dash">
        <div className="ea-loading"><Loader2 size={18} className="doc-spin" /> Loading Email Agent…</div>
      </div>
    );
  }
  const d = data || { accounts: [], inbox: [], interviews: [], pending_approvals: [], application_updates: {}, history: { sent: [], failed: [], received: [], follow_ups: [] }, needs_confirmation: [], applications: [], notifications: [], providers: {} };
  const active = d.accounts.filter((a) => a.status !== "disconnected");
  const connectedAccounts = active.filter((account) => account.status === "connected");
  const outlookAccounts = active.filter((account) => account.provider.toLowerCase().includes("outlook"));
  const unread = d.notifications.filter((n) => !n.is_read);
  const counts = {
    inbox: d.inbox.length,
    approvals: d.pending_approvals.length,
    interviews: d.interviews.length,
    updates: Object.values(d.application_updates || {}).reduce((n, list) => n + (list?.length || 0), 0),
    history: d.history.sent.length,
  };
  const upcoming = d.interviews.filter((iv) => iv.scheduling_status === "scheduled").length;
  const stats = [
    { key: "inbox", label: "Job emails", value: counts.inbox, sub: d.needs_confirmation.length ? `${d.needs_confirmation.length} need matching` : "All matched", icon: Inbox },
    { key: "approvals", label: "Awaiting approval", value: counts.approvals, sub: counts.approvals ? "Review before sending" : "You're all caught up", icon: PenLine, tone: counts.approvals ? "warn" : "" },
    { key: "interviews", label: "Interviews", value: counts.interviews, sub: `${upcoming} scheduled`, icon: CalendarClock },
    { key: "history", label: "Emails sent", value: counts.history, sub: d.history.failed.length ? `${d.history.failed.length} failed` : "Via Cafy Agent", icon: CheckCheck },
  ];
  const current = SECTIONS.find((s) => s.id === section) || SECTIONS[0];

  return (
    <div className="content-container ea-root ea-dash">
      <header className="ea-page-header">
        <div className="ea-header-text">
          <div className="ea-breadcrumb">Follow Up <span>/</span> Email Agent</div>
          <h1 className="ea-title">Email Agent</h1>
          <p className="ea-lede">Tracks recruiter emails, spots interview requests and drafts replies from your calendar and profile. You approve every message before it's sent.</p>
          <div className="ea-status-row">
            <span className={`ea-status ${connectedAccounts.length ? "is-on" : ""}`}>
              <span className="ea-status-dot" />
              {connectedAccounts.length ? `${connectedAccounts.length} inbox${connectedAccounts.length === 1 ? "" : "es"} monitored` : "No inbox connected"}
            </span>
            <span className="ea-status is-guard"><ShieldCheck size={13} /> Human approval on every send</span>
          </div>
        </div>
        <div className="ea-header-actions">
          <button type="button" className="ea-btn" onClick={() => setShowRules(true)}><SlidersHorizontal size={14} /> Follow-up rules</button>
          <button type="button" className="ea-btn ea-btn-primary" onClick={syncAll} disabled={!connectedAccounts.length || !!syncing}>
            {syncing ? <Loader2 size={14} className="doc-spin" /> : <RefreshCw size={14} />} {syncing ? "Syncing…" : "Sync now"}
          </button>
        </div>
      </header>

      {msg && (
        <div className={`ea-toast ea-toast-${msg.kind}`} role="status">
          {msg.kind === "error" ? <X size={15} /> : <Check size={15} />}
          <span>{msg.text}</span>
          <button aria-label="Dismiss" onClick={() => setMsg(null)}><X size={14} /></button>
        </div>
      )}

      <section className="ea-stats" aria-label="Email Agent summary">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <button key={s.key} type="button" className={`ea-stat ${s.tone ? `tone-${s.tone}` : ""}`} onClick={() => setSection(s.key)}>
              <span className="ea-stat-icon"><Icon size={17} /></span>
              <span className="ea-stat-label">{s.label}</span>
              <strong className="ea-stat-value">{s.value}</strong>
              <span className="ea-stat-sub">{s.sub}</span>
            </button>
          );
        })}
      </section>

      <section className="ea-block" aria-labelledby="ea-integrations-title">
        <div className="ea-block-head">
          <div>
            <h2 id="ea-integrations-title">Connected accounts</h2>
            <p>Mail sync finds recruiter emails; calendar access lets the agent propose free interview slots.</p>
          </div>
          <div className="ea-block-tools">
            <span className={`ea-status ${connectedAccounts.length ? "is-on" : ""}`}><span className="ea-status-dot" /> Auto follow-ups {connectedAccounts.length ? "on" : "off"}</span>
            <button type="button" className="ea-btn" onClick={scanFollowUps} disabled={!connectedAccounts.length}><Search size={14} /> Scan for follow-ups</button>
          </div>
        </div>
        <NangoConnectPanel onStatusChange={handleNangoStatusChange}>
          <div className={`nango-card ea-outlook-card ${outlookAccounts.some((account) => account.status === "connected") ? "nango-card-connected" : ""}`}>
            <div className="nango-card-header">
              <div className="nango-card-icon ea-outlook-icon"><Mail size={20} /></div>
              <div className="nango-card-info">
                <strong>Microsoft Outlook</strong>
                <span className="nango-card-desc">Connect a Microsoft 365 or Exchange mailbox.</span>
              </div>
              {outlookAccounts.length > 0
                ? <span className={`ea-pill ${outlookAccounts[0].status === "connected" ? "tone-ok" : "tone-bad"}`}>{label(outlookAccounts[0].status)}</span>
                : <span className="ea-pill tone-neutral">Optional</span>}
            </div>
            {outlookAccounts.length > 0 ? (
              <div className="ea-outlook-account-list">
                {outlookAccounts.map((account) => (
                  <div className="ea-outlook-account" key={account.id}>
                    <span>{account.email}</span>
                    <button type="button" className="ea-btn" disabled={syncing === account.id || !!syncing || account.status !== "connected"} onClick={() => sync(account.id)}>
                      {syncing === account.id ? <Loader2 size={13} className="doc-spin" /> : <RefreshCw size={13} />} Sync
                    </button>
                    {account.status !== "connected" && <button type="button" className="ea-btn" onClick={() => connect("outlook")}>Reconnect</button>}
                    <button type="button" className="ea-btn ea-btn-ghost-danger" onClick={() => disconnect(account.id)}>Disconnect</button>
                  </div>
                ))}
                <span className="nango-muted">Mail sync is active for this account.</span>
              </div>
            ) : (
              <div className="nango-card-actions">
                <button type="button" className="nango-btn nango-btn-primary" onClick={() => connect("outlook")} title={d.providers.outlook ? "" : "Microsoft OAuth credentials are not configured on the server"}>
                  Connect Outlook
                </button>
              </div>
            )}
          </div>
        </NangoConnectPanel>
        {active.some((account) => !account.provider.toLowerCase().includes("outlook")) && (
          <details className="ea-legacy-accounts">
            <summary>Manage existing email connections</summary>
            {active.filter((account) => !account.provider.toLowerCase().includes("outlook")).map((account) => (
              <div key={account.id} className="ea-account">
                <Mail size={16} /> <strong>{account.email}</strong>
                <span className="ea-pill tone-neutral">{label(account.provider)}</span>
                <span className={`ea-pill ${account.status === "connected" ? "tone-ok" : "tone-bad"}`}>{label(account.status)}</span>
                <span className="ea-spacer" />
                <button className="ea-btn" disabled={syncing === account.id || !!syncing || account.status !== "connected"} onClick={() => sync(account.id)}>
                  {syncing === account.id ? <Loader2 size={14} className="doc-spin" /> : <RefreshCw size={14} />} Sync now
                </button>
                <button className="ea-btn ea-btn-ghost-danger" onClick={() => disconnect(account.id)}>Disconnect</button>
              </div>
            ))}
          </details>
        )}
      </section>

      {showRules && (
        <div className="ea-rules-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowRules(false); }}>
          <section className="ea-rules-dialog" role="dialog" aria-modal="true" aria-labelledby="ea-rules-title">
            <div className="ea-rules-heading">
              <div><span className="ea-rules-icon"><Clock3 size={17} /></span><div><h2 id="ea-rules-title">Follow-up rules</h2><p>Current safeguards for recruiter follow-ups</p></div></div>
              <button type="button" className="ea-icon-button" aria-label="Close rules" onClick={() => setShowRules(false)}><X size={18} /></button>
            </div>
            <ul>
              <li><strong>Wait at least 7 days</strong><span>Longer response windows promised by a recruiter are respected.</span></li>
              <li><strong>Space follow-ups 7 days apart</strong><span>Only one pending follow-up is allowed per application.</span></li>
              <li><strong>Limit to 2 follow-ups</strong><span>A qualifying recruiter response stops further follow-ups.</span></li>
              <li><strong>You stay in control</strong><span>Every message is a draft and requires your approval before sending.</span></li>
            </ul>
            <p className="ea-rules-note">These are the current system rules; they are not editable yet.</p>
          </section>
        </div>
      )}

      <div className="ea-workspace">
        <nav className="ea-side" aria-label="Email Agent sections">
          <div className="ea-tabs" role="tablist" aria-orientation="vertical">
            {SECTIONS.map((s) => {
              const Icon = s.icon;
              const on = section === s.id;
              return (
                <button key={s.id} role="tab" aria-selected={on} className={`ea-tab ${on ? "ea-tab-active" : ""}`} onClick={() => setSection(s.id)}>
                  <Icon size={16} />
                  <span className="ea-tab-text">
                    <span>{s.label}</span>
                    <small>{s.hint}</small>
                  </span>
                  {counts[s.id] > 0 && <span className={`ea-badge ${s.id === "approvals" ? "is-hot" : ""}`}>{counts[s.id]}</span>}
                </button>
              );
            })}
          </div>

          {unread.length > 0 && (
            <div className="ea-attention">
              <div className="ea-attention-head"><Bell size={14} /> Needs your attention <span className="ea-badge is-hot">{unread.length}</span></div>
              <ul>{unread.slice(0, 5).map((n) => <li key={n.id}>{n.message}</li>)}</ul>
              <button className="ea-link-btn" onClick={() => api("/notifications/read", { method: "POST" }).then(load)}>Mark all as read</button>
            </div>
          )}
        </nav>

        <section className="ea-panel" aria-label={current.label}>
          {section === "inbox" && <InboxPanel d={d} confirmMatch={confirmMatch} />}

          {section === "approvals" && (
            <>
              <PanelHead title="Pending approvals" subtitle="Review, edit and approve AI drafts. Nothing is sent without you." />
              {d.pending_approvals.length === 0
                ? <Empty icon={CheckCheck} title="Nothing waiting for approval">New reply and follow-up drafts will appear here.</Empty>
                : <div className="ea-stack">{d.pending_approvals.map((dr) => <DraftCard key={dr.id + (dr.body || "").length} draft={dr} onChange={load} notify={notify} />)}</div>}
            </>
          )}

          {section === "interviews" && (
            <>
              <PanelHead title="Interview management" subtitle="Details pulled from recruiter emails, checked against your calendar." />
              {d.interviews.length === 0
                ? <Empty icon={CalendarClock} title="No interviews detected yet">Interview invitations in your inbox will be picked up automatically.</Empty>
                : <div className="ea-stack">{d.interviews.map((iv) => <InterviewCard key={iv.id + iv.updated_at} iv={iv} onChange={load} notify={notify} />)}</div>}
            </>
          )}

          {section === "updates" && (
            <>
              <PanelHead title="Application updates" subtitle="Where each application stands, based on recruiter emails." />
              <div className="ea-board">
                {UPDATE_STAGES.map(([k, title, tone]) => {
                  const items = d.application_updates[k] || [];
                  return (
                    <div key={k} className={`ea-col tone-${tone}`}>
                      <div className="ea-col-head"><span className="ea-col-dot" />{title}<span className="ea-badge">{items.length}</span></div>
                      {items.length === 0 ? <p className="ea-col-empty">None yet</p> : items.map((a) => (
                        <div key={a.id} className="ea-col-card">
                          <strong>{a.company}</strong>
                          <span>{a.job_title}</span>
                          <small>Updated {relTime(a.updated_at)}</small>
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {section === "history" && (
            <>
              <PanelHead title="Email history" subtitle="Everything sent and received through Cafy Agent." />
              <div className="ea-history">
                <div className="ea-history-group">
                  <h3><Send size={14} /> Sent <span className="ea-badge">{d.history.sent.length}</span></h3>
                  {d.history.sent.length === 0 ? <p className="ea-muted">No emails sent through Cafy yet.</p> : (
                    <ul className="ea-timeline">{d.history.sent.map((s) => (
                      <li key={s.id}>
                        <span className="ea-tl-dot tone-ok" />
                        <div><strong>{s.subject}</strong><span>to {s.to_email} · {fmtDate(s.sent_at)}</span></div>
                        <span className="ea-pill tone-neutral">{label(s.kind)}</span>
                      </li>
                    ))}</ul>
                  )}
                </div>

                {d.history.failed.length > 0 && (
                  <div className="ea-history-group">
                    <h3><X size={14} /> Failed (not sent) <span className="ea-badge is-hot">{d.history.failed.length}</span></h3>
                    <ul className="ea-timeline">{d.history.failed.map((s) => (
                      <li key={s.id}>
                        <span className="ea-tl-dot tone-bad" />
                        <div><strong>{s.subject}</strong><span>{s.send_error}</span></div>
                      </li>
                    ))}</ul>
                  </div>
                )}

                <div className="ea-history-group">
                  <h3><Inbox size={14} /> Received <span className="ea-badge">{d.history.received.length}</span></h3>
                  {d.history.received.length === 0 ? <p className="ea-muted">Nothing yet.</p> : (
                    <ul className="ea-timeline">{d.history.received.slice(0, 20).map((m) => (
                      <li key={m.id}>
                        <span className="ea-tl-dot" />
                        <div><strong>{m.subject}</strong><span>from {m.sender} · {fmtDate(m.received_at)}</span></div>
                      </li>
                    ))}</ul>
                  )}
                </div>

                <div className="ea-history-group">
                  <h3><Clock3 size={14} /> Follow-ups <span className="ea-badge">{d.history.follow_ups.length}</span></h3>
                  {d.history.follow_ups.length === 0 ? <p className="ea-muted">No follow-ups yet.</p> : (
                    <ul className="ea-timeline">{d.history.follow_ups.map((f) => (
                      <li key={f.id}>
                        <span className={`ea-tl-dot ${f.sent_at ? "tone-ok" : ""}`} />
                        <div>
                          <strong>{f.follow_up_date} · {label(f.approval_status)}</strong>
                          <span>
                            {f.sent_at ? `Sent ${fmtDate(f.sent_at)}` : "Not sent yet"}
                            {f.calendar_error && !f.calendar_event_id ? ` · Calendar: ${f.calendar_error}` : ""}
                          </span>
                        </div>
                        {f.calendar_event_id && <span className="ea-pill tone-ok">On calendar{f.reminder_at ? ` · ${fmtDate(f.reminder_at)}` : ""}</span>}
                        {f.approval_status === "pending" && !f.calendar_event_id && (
                          <button className="ea-btn" onClick={() => addFollowUpToCalendar(f.id)}><CalendarCheck size={13} /> Add to calendar</button>
                        )}
                      </li>
                    ))}</ul>
                  )}
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

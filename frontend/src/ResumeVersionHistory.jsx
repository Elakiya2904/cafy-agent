/**
 * Browse, compare, preview, restore, and download saved resume versions.
 * Uses authenticated API requests to load version data and document artifacts.
 */
import { withToken } from "./auth.js";
import React, { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Building2,
  CalendarDays,
  Download,
  Eye,
  FileText,
  FileUp,
  GitCompare,
  Layers,
  Loader2,
  Minus,
  Plus,
  Search,
  Sparkles,
  Target,
  Trash2,
  X,
} from "lucide-react";
import "./documents.css";
import "./resumeVersions.css";

// Mirrors App.jsx: talk to the FastAPI port directly when served from the Vite dev server.
const API_BASE =
  typeof window !== "undefined" &&
  (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") &&
  window.location?.port &&
  ["5173", "5174", "3000"].includes(window.location?.port)
    ? "http://127.0.0.1:8000"
    : "";

function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function generatedFor(v) {
  if (!v.job_title && !v.company) return "Unknown role";
  return v.company ? `${v.job_title || "Role"} (${v.company})` : v.job_title;
}

// The uploaded resume is Version 1 when present, so stored version numbers shift by one.
function versionOrigin(v, offset) {
  const base = v.based_on_version_number ? ` of Version ${v.based_on_version_number + offset}` : "";
  if (v.kind === "ai_rewrite") return `AI rewrite${base}`;
  if (v.kind === "edited") return `Edited${base}`;
  return "AI generated";
}

function bestDownload(v) {
  return v.pdf_url || v.docx_url || v.tex_url || null;
}

function entryKey(entry) {
  return `${entry.title || entry.degree || ""}|${entry.organization || entry.company || entry.institution || ""}`;
}

/** Section-by-section differences between two structured tailored resumes. */
export function compareResumes(a, b) {
  const lower = (list) => new Set((list || []).map((s) => String(s).toLowerCase()));
  const aSkills = lower(a.skills);
  const bSkills = lower(b.skills);
  const skillsAdded = (b.skills || []).filter((s) => !aSkills.has(String(s).toLowerCase()));
  const skillsRemoved = (a.skills || []).filter((s) => !bSkills.has(String(s).toLowerCase()));

  const bulletChanges = (section) => {
    const aByKey = new Map((a[section] || []).map((e) => [entryKey(e), e]));
    const changes = [];
    for (const entry of b[section] || []) {
      const before = aByKey.get(entryKey(entry));
      const beforeBullets = new Set(before?.bullets || []);
      const afterBullets = new Set(entry.bullets || []);
      const added = (entry.bullets || []).filter((x) => !beforeBullets.has(x));
      const removed = (before?.bullets || []).filter((x) => !afterBullets.has(x));
      if (!before || added.length || removed.length) {
        changes.push({ name: entry.title || entry.degree || "Entry", isNew: !before, added, removed });
      }
    }
    return changes;
  };

  return {
    summaryChanged: (a.professional_summary || "") !== (b.professional_summary || ""),
    skillsAdded,
    skillsRemoved,
    counts: ["experience", "projects", "education", "certifications"].map((section) => ({
      section,
      a: (a[section] || []).length,
      b: (b[section] || []).length,
    })),
    experience: bulletChanges("experience"),
    projects: bulletChanges("projects"),
  };
}

function ChangesView({ a, b, diff }) {
  return (
    <div className="doc-compare-changes">
      <h5>Professional Summary {diff.summaryChanged ? "" : "(unchanged)"}</h5>
      <div className="doc-compare-cols">
        <div>
          <span className="doc-muted">{a.label}</span>
          <p>{a.resume?.professional_summary || "No summary."}</p>
        </div>
        <div>
          <span className="doc-muted">{b.label}</span>
          <p>{b.resume?.professional_summary || "No summary."}</p>
        </div>
      </div>

      <h5>Skills</h5>
      <div className="doc-chip-row">
        {diff.skillsAdded.map((s) => (
          <span key={`+${s}`} className="doc-chip added"><Plus size={12} aria-hidden="true" /> {s}</span>
        ))}
        {diff.skillsRemoved.map((s) => (
          <span key={`-${s}`} className="doc-chip removed"><Minus size={12} aria-hidden="true" /> {s}</span>
        ))}
        {!diff.skillsAdded.length && !diff.skillsRemoved.length && <span className="doc-muted">No skill changes.</span>}
      </div>

      <h5>Sections</h5>
      <div className="doc-chip-row">
        {diff.counts.map((c) => (
          <span key={c.section} className="doc-chip">
            {c.section}: {c.a} <ArrowRight size={12} aria-label="to" /> {c.b}
          </span>
        ))}
      </div>

      {["experience", "projects"].map((section) =>
        diff[section].length ? (
          <div key={section}>
            <h5>{section === "experience" ? "Work Experience" : "Projects"} bullet changes</h5>
            {diff[section].map((change) => (
              <div key={change.name} className="doc-bullet-change">
                <strong>{change.name}{change.isNew ? " (new)" : ""}</strong>
                <ul>
                  {change.added.map((x) => <li key={`+${x}`} className="added">{x}</li>)}
                  {change.removed.map((x) => <li key={`-${x}`} className="removed">{x}</li>)}
                </ul>
              </div>
            ))}
          </div>
        ) : null
      )}
    </div>
  );
}

/** Full-screen comparison: both resumes rendered as pages side by side, plus a list of changes. */
function ComparisonPanel({ a, b, onClose, PreviewComponent }) {
  const diff = useMemo(() => compareResumes(a.resume || {}, b.resume || {}), [a, b]);
  const [view, setView] = useState(PreviewComponent ? "pages" : "changes");
  return (
    <div className="doc-modal-overlay" onClick={onClose}>
      <div
        className="doc-modal doc-compare-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Compare ${a.label} and ${b.label}`}
        data-testid="version-comparison"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="doc-compare-head">
          <h4>{a.label} vs {b.label}</h4>
          <div className="doc-compare-tabs" role="tablist" aria-label="Comparison view">
            {PreviewComponent && (
              <button type="button" role="tab" aria-selected={view === "pages"} className={view === "pages" ? "active" : ""} onClick={() => setView("pages")}>
                Page view
              </button>
            )}
            <button type="button" role="tab" aria-selected={view === "changes"} className={view === "changes" ? "active" : ""} onClick={() => setView("changes")}>
              Changes
            </button>
          </div>
          <button type="button" className="doc-icon-btn" onClick={onClose} aria-label="Close comparison">
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {view === "pages" && PreviewComponent ? (
          <div className="doc-compare-pages" data-testid="compare-pages">
            {[a, b].map((item) => (
              <div key={item.id} className="doc-compare-page">
                <span className="doc-compare-page-label">{item.label}{item.subtitle ? ` · ${item.subtitle}` : ""}</span>
                <div className="doc-compare-page-body">
                  <PreviewComponent resume={item.resume || {}} job={item.job || {}} resumeReady isGeneratingResume={false} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="doc-modal-body">
            <ChangesView a={a} b={b} diff={diff} />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Lists every generated tailored resume with preview, download and compare.
 * `PreviewComponent` is App's ResumeDocumentPreview, passed in to avoid a circular import.
 */
export default function ResumeVersionHistory({ PreviewComponent }) {
  const [versions, setVersions] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deletingId, setDeletingId] = useState("");
  const [previewing, setPreviewing] = useState(null);
  const [compareA, setCompareA] = useState("");
  const [compareB, setCompareB] = useState("");
  const [comparison, setComparison] = useState(null);
  const [uploaded, setUploaded] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // The original upload is optional; a failure here must not hide the generated versions.
        fetch(`${API_BASE}/api/resume/uploaded`)
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => !cancelled && setUploaded(d?.uploaded || null))
          .catch(() => {});
        const resp = await fetch(`${API_BASE}/api/resumes/versions`);
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || `Could not load versions (${resp.status})`);
        if (cancelled) return;
        const list = data.versions || [];
        setVersions(list);
      } catch (err) {
        if (!cancelled) setError(err.message || "Could not load resume versions.");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const deleteVersion = async (version) => {
    if (!window.confirm(`Delete ${versionLabel(version)} for ${generatedFor(version)}? This cannot be undone.`)) return;
    setDeletingId(version.resume_id);
    setDeleteError("");
    try {
      const resp = await fetch(`${API_BASE}/api/resumes/versions/${encodeURIComponent(version.resume_id)}`, {
        method: "DELETE",
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || `Could not delete this version (${resp.status}).`);
      setVersions((current) => current.filter((item) => item.resume_id !== version.resume_id));
      setCompareA("");
      setCompareB("");
      setComparison(null);
    } catch (err) {
      setDeleteError(err.message || "Could not delete this version.");
    } finally {
      setDeletingId("");
    }
  };

  // Everything that can be compared: the uploaded original (oldest) plus every version.
  const UPLOADED_ID = "uploaded";
  const offset = uploaded ? 1 : 0;
  const versionLabel = (v) => `Version ${v.version_number + offset}`;
  const comparable = [
    ...(uploaded
      ? [{ id: UPLOADED_ID, label: "Version 1 (uploaded)", subtitle: uploaded.filename, order: 0, resume: uploaded.resume || {}, job: {} }]
      : []),
    ...versions.map((v) => ({
      id: v.resume_id,
      label: versionLabel(v),
      subtitle: generatedFor(v),
      order: v.version_number,
      resume: v.resume,
      job: { title: v.job_title, company: v.company },
    })),
  ];
  const byId = (id) => comparable.find((c) => c.id === id);

  useEffect(() => {
    // Default comparison: newest version against the one before it (or the uploaded original).
    if (compareA || compareB) return;
    const newest = versions[0]?.resume_id;
    const previous = versions[1]?.resume_id || (uploaded ? UPLOADED_ID : null);
    if (newest && previous) {
      setCompareA(newest);
      setCompareB(previous);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [comparable.length]);

  const companies = new Set(versions.map((v) => (v.company || "").toLowerCase()).filter(Boolean));
  const latest = versions.reduce((max, v) => {
    const t = new Date(v.updated_at || v.created_at).getTime();
    return Number.isFinite(t) && t > max ? t : max;
  }, 0);
  const shownVersions = versions.filter((v) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return [v.job_title, v.company].some((x) => (x || "").toLowerCase().includes(q));
  });
  const baseSkills = uploaded?.resume?.skills || [];
  const formats = (v) => [["PDF", v.pdf_url], ["DOCX", v.docx_url], ["LaTeX", v.tex_url]].filter(([, url]) => url).map(([name]) => name);

  return (
    <section className="rv" aria-labelledby="doc-version-title">
      <header className="rv-head">
        <div>
          <h2 id="doc-version-title">Document Version History</h2>
          <p>Your uploaded resume and every tailored version generated from it.</p>
        </div>
        <dl className="rv-stats">
          <div><dt><Layers size={14} aria-hidden="true" /> Versions</dt><dd>{versions.length + offset}</dd></div>
          <div><dt><Building2 size={14} aria-hidden="true" /> Companies</dt><dd>{companies.size}</dd></div>
          <div><dt><CalendarDays size={14} aria-hidden="true" /> Last updated</dt><dd>{latest ? new Date(latest).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "—"}</dd></div>
        </dl>
      </header>

      <div className="rv-section-head">
        <h3>Base resume</h3>
        <span>Every tailored version is generated from this original.</span>
      </div>
      {uploaded ? (
        <div className="rv-base" data-testid="uploaded-resume">
          <span className="rv-base-icon"><FileUp size={22} aria-hidden="true" /></span>
          <div className="rv-base-info">
            <strong className="rv-base-title">
              Version 1
              <span className="rv-pill rv-pill-base">Uploaded</span>
            </strong>
            <span className="rv-base-file">{uploaded.filename}</span>
            <span className="rv-meta"><CalendarDays size={13} aria-hidden="true" /> {formatDate(uploaded.uploaded_at)}</span>
            {baseSkills.length > 0 && (
              <div className="rv-skills">
                {baseSkills.slice(0, 6).map((s) => <span key={s} className="rv-skill">{s}</span>)}
                {baseSkills.length > 6 && <span className="rv-skill more">+{baseSkills.length - 6} more</span>}
              </div>
            )}
          </div>
          <div className="rv-actions">
            <button
              type="button"
              className="rv-btn"
              onClick={() => window.open(withToken(`${API_BASE}${uploaded.preview_url}`), "_blank", "noopener")}
            >
              <Eye size={15} aria-hidden="true" /> Preview
            </button>
            <button
              type="button"
              className="rv-btn"
              onClick={() => window.open(withToken(`${API_BASE}${uploaded.download_url}`), "_blank", "noopener")}
            >
              <Download size={15} aria-hidden="true" /> Download
            </button>
          </div>
        </div>
      ) : (
        <div className="rv-base rv-base-empty">
          <span className="rv-base-icon"><FileUp size={22} aria-hidden="true" /></span>
          <p>No uploaded file stored. Upload your resume on the Home page to keep the original here.</p>
        </div>
      )}

      <div className="rv-section-head rv-section-split">
        <div>
          <h3>AI Versions</h3>
          <span>Tailored for specific roles, newest first.</span>
        </div>
        {versions.length > 1 && (
          <label className="rv-search">
            <Search size={15} aria-hidden="true" />
            <input type="search" placeholder="Filter by role or company" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Filter versions" />
          </label>
        )}
      </div>

      {isLoading && (
        <p className="rv-loading"><Loader2 size={16} className="doc-spin" aria-hidden="true" /> Loading versions...</p>
      )}
      {error && <div className="pipeline-error" role="alert">{error}</div>}
      {deleteError && <div className="pipeline-error" role="alert">{deleteError}</div>}
      {!isLoading && !error && versions.length === 0 && (
        <div className="rv-empty">
          <span className="rv-empty-icon"><Sparkles size={20} aria-hidden="true" /></span>
          <strong>Your tailored versions will appear here</strong>
          <p>No tailored resumes yet. Apply to a job and generate a tailored resume to start your version history.</p>
        </div>
      )}
      {versions.length > 0 && shownVersions.length === 0 && (
        <div className="rv-empty"><strong>No versions match “{query}”</strong></div>
      )}

      {shownVersions.length > 0 && (
        <ul className="rv-list">
          {shownVersions.map((v) => {
            const download = bestDownload(v);
            const files = formats(v);
            return (
              <li key={v.resume_id} className={`rv-item ${v.is_current ? "is-current" : ""}`}>
                <span className="rv-badge" aria-hidden="true">V{v.version_number + offset}</span>
                <div className="rv-card">
                  <div className="rv-card-main">
                    <strong className="rv-card-label">
                      {versionLabel(v)}
                      {v.is_current && <span className="rv-pill rv-pill-current">Current</span>}
                    </strong>
                    <h4 className="rv-role">{v.job_title || "Untitled role"}</h4>
                    <div className="rv-card-meta">
                      {v.company && <span className="rv-company"><Building2 size={13} aria-hidden="true" /> {v.company}</span>}
                      <span className="rv-meta"><CalendarDays size={13} aria-hidden="true" /> {formatDate(v.updated_at || v.created_at)}</span>
                      {files.length > 0 && (
                        <span className="rv-formats">
                          {files.map((f) => <span key={f} className="rv-format">{f}</span>)}
                        </span>
                      )}
                    </div>
                    <span className="rv-origin"><Target size={13} aria-hidden="true" /><span>{`${versionOrigin(v, offset)} for: ${generatedFor(v)}`}</span></span>
                  </div>
                  <div className="rv-actions">
                    <button type="button" className="rv-btn" onClick={() => setPreviewing(v)}>
                      <Eye size={15} aria-hidden="true" /> Preview
                    </button>
                    <button
                      type="button"
                      className="rv-btn rv-btn-primary"
                      disabled={!download}
                      title={download ? "Download this version" : "No file available for this version"}
                      onClick={() => window.open(withToken(`${API_BASE}${download}`), "_blank", "noopener")}
                    >
                      <Download size={15} aria-hidden="true" /> Download
                    </button>
                    <button
                      type="button"
                      className="rv-btn rv-btn-icon rv-btn-danger"
                      disabled={deletingId === v.resume_id}
                      aria-label={`Delete ${versionLabel(v)}`}
                      title={`Delete ${versionLabel(v)}`}
                      onClick={() => deleteVersion(v)}
                    >
                      {deletingId === v.resume_id
                        ? <Loader2 size={15} className="doc-spin" aria-hidden="true" />
                        : <Trash2 size={15} aria-hidden="true" />}
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {comparable.length >= 2 && (
        <div className="rv-compare">
          <div className="rv-compare-text">
            <span className="rv-compare-icon"><GitCompare size={18} aria-hidden="true" /></span>
            <div>
              <strong>Compare Versions</strong>
              <span>See what changed between two versions, page by page.</span>
            </div>
          </div>
          <div className="rv-compare-controls">
            <select aria-label="First version" value={compareA} onChange={(e) => setCompareA(e.target.value)}>
              {comparable.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
            <span className="rv-vs">vs</span>
            <select aria-label="Second version" value={compareB} onChange={(e) => setCompareB(e.target.value)}>
              {comparable.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
            <button
              type="button"
              className="rv-btn rv-btn-primary"
              disabled={!compareA || !compareB || compareA === compareB}
              onClick={() => {
                // Show older -> newer regardless of selection order.
                const [x, y] = [byId(compareA), byId(compareB)].sort((p, q) => p.order - q.order);
                setComparison({ a: x, b: y });
              }}
            >
              <GitCompare size={15} aria-hidden="true" /> Compare
            </button>
          </div>
        </div>
      )}

      {comparison && (
        <ComparisonPanel a={comparison.a} b={comparison.b} PreviewComponent={PreviewComponent} onClose={() => setComparison(null)} />
      )}

      {previewing && (
        <div className="doc-modal-overlay" onClick={() => setPreviewing(null)}>
          <div
            className="doc-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`Preview ${versionLabel(previewing)}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="doc-compare-head">
              <h4>{versionLabel(previewing)} · {generatedFor(previewing)}</h4>
              <button type="button" className="doc-icon-btn" onClick={() => setPreviewing(null)} aria-label="Close preview">
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <div className="doc-modal-body">
              {PreviewComponent ? (
                <PreviewComponent
                  resume={previewing.resume}
                  job={{ title: previewing.job_title, company: previewing.company }}
                  resumeReady
                  isGeneratingResume={false}
                />
              ) : (
                <pre>{JSON.stringify(previewing.resume, null, 2)}</pre>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

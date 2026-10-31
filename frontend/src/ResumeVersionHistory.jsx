import { withToken } from "./auth.js";
import React, { useEffect, useMemo, useState } from "react";
import { ArrowRight, Download, Eye, FileText, FileUp, GitCompare, Loader2, Minus, Plus, X } from "lucide-react";
import "./documents.css";

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
  const [previewing, setPreviewing] = useState(null);
  const [compareA, setCompareA] = useState("");
  const [compareB, setCompareB] = useState("");
  const [comparison, setComparison] = useState(null);
  const [uploaded, setUploaded] = useState(null);

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

  return (
    <section className="doc-card" aria-labelledby="doc-version-title">
      <h2 id="doc-version-title">Document Version History</h2>
      <p className="doc-muted">Your uploaded resume and every tailored version generated from it.</p>

      <h3 className="doc-group-title">Uploaded Resume</h3>
      {uploaded ? (
        <ul className="doc-version-list" data-testid="uploaded-resume">
          <li className="doc-version-row">
            <span className="doc-file-icon"><FileUp size={20} aria-hidden="true" /></span>
            <div className="doc-version-info">
              <strong>
                Version 1
                <span className="doc-pill-uploaded">Uploaded</span>
              </strong>
              <span>{uploaded.filename}</span>
              <span className="doc-muted">{formatDate(uploaded.uploaded_at)}</span>
            </div>
            <div className="doc-version-actions">
              <button
                type="button"
                className="doc-btn-secondary"
                onClick={() => window.open(withToken(`${API_BASE}${uploaded.preview_url}`), "_blank", "noopener")}
              >
                <Eye size={14} aria-hidden="true" /> Preview
              </button>
              <button
                type="button"
                className="doc-btn-secondary"
                onClick={() => window.open(withToken(`${API_BASE}${uploaded.download_url}`), "_blank", "noopener")}
              >
                <Download size={14} aria-hidden="true" /> Download
              </button>
            </div>
          </li>
        </ul>
      ) : (
        <p className="doc-muted">No uploaded file stored. Upload your resume on the Home page to keep the original here.</p>
      )}

      <h3 className="doc-group-title">AI Versions</h3>

      {isLoading && (
        <p className="doc-muted"><Loader2 size={14} className="doc-spin" aria-hidden="true" /> Loading versions...</p>
      )}
      {error && <div className="pipeline-error" role="alert">{error}</div>}
      {!isLoading && !error && versions.length === 0 && (
        <div className="doc-empty">
          <FileText size={22} aria-hidden="true" />
          <p>No tailored resumes yet. Apply to a job and generate a tailored resume to start your version history.</p>
        </div>
      )}

      {versions.length > 0 && (
        <ul className="doc-version-list">
          {versions.map((v) => {
            const download = bestDownload(v);
            return (
              <li key={v.resume_id} className="doc-version-row">
                <span className="doc-file-icon"><FileText size={20} aria-hidden="true" /></span>
                <div className="doc-version-info">
                  <strong>
                    {versionLabel(v)}
                    {v.is_current && <span className="doc-pill-current">Current</span>}
                  </strong>
                  <span>{`${versionOrigin(v, offset)} for: ${generatedFor(v)}`}</span>
                  <span className="doc-muted">{formatDate(v.updated_at || v.created_at)}</span>
                </div>
                <div className="doc-version-actions">
                  <button type="button" className="doc-btn-secondary" onClick={() => setPreviewing(v)}>
                    <Eye size={14} aria-hidden="true" /> Preview
                  </button>
                  <button
                    type="button"
                    className="doc-btn-secondary"
                    disabled={!download}
                    title={download ? "Download this version" : "No file available for this version"}
                    onClick={() => window.open(withToken(`${API_BASE}${download}`), "_blank", "noopener")}
                  >
                    <Download size={14} aria-hidden="true" /> Download
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {comparable.length >= 2 && (
        <div className="doc-compare-bar">
          <strong>Compare Versions</strong>
          <select aria-label="First version" value={compareA} onChange={(e) => setCompareA(e.target.value)}>
            {comparable.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
          <span className="doc-muted">vs</span>
          <select aria-label="Second version" value={compareB} onChange={(e) => setCompareB(e.target.value)}>
            {comparable.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
          <button
            type="button"
            className="doc-btn-primary"
            disabled={!compareA || !compareB || compareA === compareB}
            onClick={() => {
              // Show older -> newer regardless of selection order.
              const [x, y] = [byId(compareA), byId(compareB)].sort((p, q) => p.order - q.order);
              setComparison({ a: x, b: y });
            }}
          >
            <GitCompare size={14} aria-hidden="true" /> Compare
          </button>
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

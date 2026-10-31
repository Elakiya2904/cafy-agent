import React, { useState } from "react";
import { Check, Download, Loader2 } from "lucide-react";
import "./documents.css";

// Mirrors App.jsx: talk to the FastAPI port directly when served from the Vite dev server.
const API_BASE =
  typeof window !== "undefined" &&
  (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") &&
  window.location?.port &&
  ["5173", "5174", "3000"].includes(window.location?.port)
    ? "http://127.0.0.1:8000"
    : "";

const EXPORT_OPTIONS = [
  { id: "profile", title: "Profile Data", detail: "Personal information, education, skills, experience, projects, certifications", format: "JSON" },
  { id: "resumes", title: "Resumes", detail: "All generated resume versions", format: "PDF / DOCX / LaTeX" },
  { id: "applications", title: "Application History", detail: "Jobs in your application pipeline and their status", format: "JSON" },
];
const ALL_IDS = EXPORT_OPTIONS.map((o) => o.id);

function filenameFrom(disposition) {
  const match = /filename="?([^";]+)"?/i.exec(disposition || "");
  return match ? match[1] : "cafy-export.zip";
}

/** "Export Your Data" card on the Files tab. Applications live in the browser, so they are sent with the request. */
export default function DataExport({ pipelineJobIds, allJobs }) {
  const [selected, setSelected] = useState(() => new Set(ALL_IDS));
  const [isExporting, setIsExporting] = useState(false);
  const [message, setMessage] = useState(null);

  const allSelected = ALL_IDS.every((id) => selected.has(id));
  const toggle = (id) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const handleExport = async () => {
    setIsExporting(true);
    setMessage(null);
    const ids = pipelineJobIds instanceof Set ? pipelineJobIds : new Set(pipelineJobIds || []);
    const applications = (allJobs || [])
      .filter((job) => ids.has(job.id))
      .map((job) => ({ job_id: job.id, title: job.title, company: job.company, status: "In pipeline", url: job.url }));
    try {
      const resp = await fetch(`${API_BASE}/api/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ include: ALL_IDS.filter((id) => selected.has(id)), applications }),
      });
      if (!resp.ok) {
        let detail = "";
        try {
          detail = (await resp.json()).detail;
        } catch {
          // non-JSON error body
        }
        throw new Error(detail || `Export failed (${resp.status})`);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filenameFrom(resp.headers.get("Content-Disposition"));
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMessage({ kind: "success", text: `Export ready: ${link.download}` });
    } catch (err) {
      setMessage({ kind: "error", text: err.message || "Export failed." });
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <section className="doc-card" aria-labelledby="doc-export-title">
      <h2 id="doc-export-title">Export Your Data</h2>
      <p className="doc-muted">Download a complete copy of your profile, documents and application history.</p>

      <div className="doc-export-grid">
        {EXPORT_OPTIONS.map((option) => (
          <label key={option.id} className={`doc-export-tile ${selected.has(option.id) ? "selected" : ""}`}>
            <input type="checkbox" checked={selected.has(option.id)} onChange={() => toggle(option.id)} />
            <span>
              <strong>{option.title}</strong>
              <small>{option.detail}</small>
              <em className="doc-format">{option.format}</em>
            </span>
          </label>
        ))}
        <label className={`doc-export-tile complete ${allSelected ? "selected" : ""}`}>
          <input
            type="checkbox"
            checked={allSelected}
            onChange={() => setSelected(allSelected ? new Set() : new Set(ALL_IDS))}
          />
          <span>
            <strong>Complete Data</strong>
            <small>Everything (profile + documents + applications)</small>
            <em className="doc-format">ZIP</em>
          </span>
        </label>
      </div>

      <div className="doc-export-footer">
        {message && (
          <span className={message.kind === "error" ? "doc-error" : "doc-success"} role={message.kind === "error" ? "alert" : "status"}>
            {message.kind === "success" && <Check size={14} aria-hidden="true" />} {message.text}
          </span>
        )}
        <button type="button" className="doc-btn-primary" disabled={selected.size === 0 || isExporting} onClick={handleExport}>
          {isExporting ? <Loader2 size={14} className="doc-spin" aria-hidden="true" /> : <Download size={14} aria-hidden="true" />}
          Create Export
        </button>
      </div>
    </section>
  );
}

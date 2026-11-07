/**
 * Structured resume editor with autosave, AI improvements, scores, and preview.
 * Manages editable profile sections and communicates changes to resume services.
 */
import React, { Suspense, lazy, useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  Download,
  ExternalLink,
  FileText,
  GripVertical,
  Lightbulb,
  Redo2,
  SlidersHorizontal,
  Sparkles,
  Undo2,
  X,
} from "lucide-react";
import { EditorMatchScore, SectionScoreBadge } from "./JobMatchScore.jsx";
import { loadPdfSettings, PDF_ACCENTS, PDF_FONTS, PDF_SETTINGS_KEY } from "./pdfSettings.js";
import "./resumeEditor.css";

// The PDF renderer is large, so it loads only when the editor opens.
const PdfPreview = lazy(() => import("./PdfPreview.jsx"));

// [key, short tab label, section heading, helper line]
// Only the sections the UK template prints. Internships are edited on their own tab and print
// under Work Experience. Certifications, publications and achievements are kept in the data
// (never deleted) but are not shown, because the template does not print them.
export const EDITOR_SECTIONS = [
  ["personal", "Personal", "Personal Information", "How recruiters reach you. Keep links short and current."],
  ["summary", "About Me", "About Me", "Two to four sentences aimed at this role: who you are, what you have done, what you bring."],
  ["education", "Education", "Education", "Degree, institution, dates, and anything that strengthens this application."],
  ["experience", "Experience", "Work Experience", "Most recent first. Start each bullet with an action verb and end with a measurable result."],
  ["internships", "Internships", "Internships", "Printed under Work Experience. Roles, organisations and key contributions."],
  ["projects", "Projects", "Projects", "Show what you built, the stack you used, and what changed because of it."],
  ["skills", "Skills", "Skills", "List the tools you have actually used. Match the wording the job description uses."],
];

const FONT_LABELS = { Helvetica: "Helvetica (Sans)", "Times-Roman": "Times (Serif)", Courier: "Courier (Mono)" };
const WORKSPACE_TABS = [
  ["editor", "Resume Editor"],
  ["preview", "Preview & Test"],
  ["ats", "ATS Insights"],
];

const AUTOSAVE_MS = 2000;
const HISTORY_COALESCE_MS = 900;

const ACTION_VERBS = new Set(
  ("led built ran wrote drove grew won cut set made took began brought chose created designed developed " +
    "delivered launched managed improved reduced increased automated implemented optimized migrated " +
    "architected analyzed collaborated mentored owned shipped deployed integrated streamlined established " +
    "resolved secured scaled trained coordinated spearheaded achieved generated accelerated refactored " +
    "maintained produced presented negotiated supported engineered configured monitored tested").split(" ")
);

// Quick, local quality checks for one bullet. These only point things out; they never rewrite.
export function bulletHints(text) {
  const t = String(text || "").trim();
  if (!t) return [];
  const hints = [];
  const first = t.split(/\s+/)[0].toLowerCase().replace(/[^a-z]/g, "");
  if (!ACTION_VERBS.has(first) && !/ed$/.test(first)) hints.push("Start with a strong action verb (Built, Led, Reduced…).");
  if (!/\d/.test(t)) hints.push("Add a measurable result if you have one (%, $, time, scale).");
  if (t.length > 220) hints.push("Long: aim for two lines or fewer.");
  if (t.length < 25) hints.push("Short: add what you did and the outcome.");
  return hints;
}

export function saveBlob(blob, name) {
  if (!blob) return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const cleanBulletLine = (line) => line.replace(/^[\s\-*•·\d.)]+/, "").trim();

function AutoTextarea({ value, className, ...rest }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    if (el.scrollHeight > 0) el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return <textarea ref={ref} rows={1} value={value} className={className} {...rest} />;
}

function SortableList({ count, onMove, children, strategy = verticalListSortingStrategy }) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );
  const ids = useMemo(() => Array.from({ length: count }, (_, i) => String(i)), [count]);
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={({ active, over }) => {
        if (over && active.id !== over.id) onMove(Number(active.id), Number(over.id));
      }}
    >
      <SortableContext items={ids} strategy={strategy}>
        {children}
      </SortableContext>
    </DndContext>
  );
}

function SortableRow({ id, className, children }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: String(id) });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 5 : undefined,
    opacity: isDragging ? 0.85 : 1,
  };
  const handle = (
    <button type="button" className="re-grip" aria-label="Drag to reorder" {...attributes} {...listeners}>
      <GripVertical size={15} aria-hidden="true" />
    </button>
  );
  return (
    <div ref={setNodeRef} style={style} className={className}>
      {children(handle)}
    </div>
  );
}

function BulletList({ section, entryIndex, bullets, isRewriting, focusKey, setFocusKey, edit, onImprove, pendingFocus }) {
  const label = section === "projects" ? "Project" : section === "internships" ? "Internship" : "Experience";
  return (
    <div className="re-bullets">
      <div className="re-field-label">Achievements</div>
      <SortableList count={bullets.length} onMove={(from, to) => edit.moveBullet(section, entryIndex, from, to)}>
        {bullets.map((bullet, bIdx) => {
          const key = `${section}-${entryIndex}-${bIdx}`;
          const hints = focusKey === key ? bulletHints(bullet) : [];
          const clean = bulletHints(bullet).length === 0 && bullet.trim().length > 0;
          return (
            <SortableRow key={key} id={bIdx} className="re-bullet-row">
              {(handle) => (
                <>
                  <div className="re-bullet-main">
                    {handle}
                    <span className={`re-bullet-dot ${clean ? "ok" : ""}`} aria-hidden="true" />
                    <AutoTextarea
                      className="re-bullet-input"
                      data-bullet-key={key}
                      value={bullet}
                      placeholder="What did you do, and what changed because of it?"
                      aria-label={`${label} bullet ${bIdx + 1}`}
                      onFocus={() => setFocusKey(key)}
                      onChange={(e) => edit.updateBullet(section, entryIndex, bIdx, e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                          e.preventDefault();
                          pendingFocus.current = `${section}-${entryIndex}-${bIdx + 1}`;
                          edit.insertBullets(section, entryIndex, bIdx + 1, [""]);
                        } else if (e.key === "Backspace" && !bullet && bullets.length > 0) {
                          e.preventDefault();
                          pendingFocus.current = `${section}-${entryIndex}-${Math.max(0, bIdx - 1)}`;
                          edit.removeBullet(section, entryIndex, bIdx);
                        }
                      }}
                      onPaste={(e) => {
                        const text = e.clipboardData?.getData("text") || "";
                        if (!/\r?\n/.test(text.trim())) return;
                        const lines = text.split(/\r?\n/).map(cleanBulletLine).filter(Boolean);
                        if (lines.length < 2) return;
                        e.preventDefault();
                        edit.replaceBulletWith(section, entryIndex, bIdx, lines);
                      }}
                    />
                    <button
                      type="button"
                      className="btn-icon-action ai-sparkle"
                      title="Improve this bullet with AI"
                      aria-label="Improve this bullet with AI"
                      onClick={() => onImprove(section, entryIndex, bIdx)}
                      disabled={isRewriting || !bullet.trim()}
                    >
                      <Sparkles size={14} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className="btn-icon-action danger"
                      title="Delete bullet"
                      aria-label="Delete bullet"
                      onClick={() => edit.removeBullet(section, entryIndex, bIdx)}
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  </div>
                  {hints.length > 0 && (
                    <ul className="re-hints" aria-label="Writing tips">
                      {hints.map((h) => (
                        <li key={h}><Lightbulb size={12} aria-hidden="true" /> {h}</li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </SortableRow>
          );
        })}
      </SortableList>
      <button
        type="button"
        className="btn-add-bullet"
        onClick={() => {
          pendingFocus.current = `${section}-${entryIndex}-${bullets.length}`;
          edit.insertBullets(section, entryIndex, bullets.length, [""]);
        }}
      >
        + Add Bullet Point
      </button>
    </div>
  );
}

function EntryList({ section, entries, fields, titleOf, addLabel, hasBullets, hasDescription, improveDescription, isRewriting, focusKey, setFocusKey, edit, onImprove, pendingFocus }) {
  return (
    <>
      <SortableList count={entries.length} onMove={(from, to) => edit.moveEntry(section, from, to)}>
        {entries.map((entry, idx) => (
          <SortableRow key={`${section}-${idx}`} id={idx} className="editor-entry-card re-entry">
            {(handle) => (
              <>
                <div className="editor-entry-header">
                  <span className="re-entry-title">
                    {handle}
                    <strong>{titleOf(entry) || "Untitled"}</strong>
                  </span>
                  <span className="editor-entry-actions" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {(hasBullets || improveDescription) && (
                      <button
                        type="button"
                        className="btn-improve-ai-sm"
                        onClick={() => onImprove(section, idx, null)}
                        disabled={isRewriting}
                        title="Improve this entry with AI"
                      >
                        <Sparkles size={13} aria-hidden="true" /> Improve with AI
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn-icon-action danger"
                      title="Remove entry"
                      aria-label={`Remove ${section} entry`}
                      onClick={() => edit.removeEntry(section, idx)}
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  </span>
                </div>
                <div className="re-field-grid">
                  {fields.map(([field, placeholder, ariaLabel]) => (
                    <input
                      key={field}
                      type="text"
                      className="editor-input"
                      placeholder={placeholder}
                      value={entry[field] || ""}
                      onChange={(e) => edit.updateEntryField(section, idx, field, e.target.value)}
                      aria-label={ariaLabel}
                    />
                  ))}
                </div>
                {hasDescription && (
                  <textarea
                    className="editor-input re-entry-description"
                    placeholder={section === "education" ? "Describe the knowledge and focus developed through this degree." : "Description or publication details"}
                    value={entry.description || ""}
                    onChange={(e) => edit.updateEntryField(section, idx, "description", e.target.value)}
                    aria-label={`${section} description ${idx + 1}`}
                  />
                )}
                {hasBullets && (
                  <BulletList
                    section={section}
                    entryIndex={idx}
                    bullets={entry.bullets || []}
                    isRewriting={isRewriting}
                    focusKey={focusKey}
                    setFocusKey={setFocusKey}
                    edit={edit}
                    onImprove={onImprove}
                    pendingFocus={pendingFocus}
                  />
                )}
              </>
            )}
          </SortableRow>
        ))}
      </SortableList>
      <button type="button" className="btn-add-entry" onClick={() => edit.addEntry(section)}>
        {addLabel}
      </button>
    </>
  );
}

function SkillsEditor({ skills, recommended, edit }) {
  const [draft, setDraft] = useState("");
  const commit = (raw) => {
    const parts = String(raw).split(/[,\n;]/).map((s) => s.trim()).filter(Boolean);
    if (parts.length) edit.addSkills(parts);
    setDraft("");
  };
  return (
    <>
      <SortableList count={skills.length} onMove={edit.moveSkill} strategy={rectSortingStrategy}>
        <div className="re-skill-wrap">
          {skills.map((skill, i) => (
            <SortableRow key={skill} id={i} className="re-skill-chip">
              {(handle) => (
                <>
                  {handle}
                  <span>{skill}</span>
                  <button type="button" className="editor-skill-remove" onClick={() => edit.removeSkill(skill)} aria-label={`Remove skill ${skill}`}>
                    ×
                  </button>
                </>
              )}
            </SortableRow>
          ))}
        </div>
      </SortableList>
      <div className="editor-skill-add-bar">
        <input
          type="text"
          className="editor-input"
          placeholder="Type a skill and press Enter (paste a comma-separated list to add many)"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              commit(draft);
            }
          }}
          onPaste={(e) => {
            const text = e.clipboardData?.getData("text") || "";
            if (/[,\n;]/.test(text)) {
              e.preventDefault();
              commit(text);
            }
          }}
          aria-label="Add new skill"
        />
        <button type="button" className="pipeline-btn-secondary" onClick={() => commit(draft)}>Add</button>
      </div>
      <div className="re-muted">{skills.length} skills{skills.length < 8 ? " · aim for 8–15 relevant ones" : skills.length > 18 ? " · consider trimming to the most relevant" : ""}</div>
      {recommended.length > 0 && (
        <div className="re-suggest">
          <div className="re-suggest-head">
            <span><Lightbulb size={14} aria-hidden="true" /> Skills this job asks for</span>
            <button type="button" onClick={() => edit.addSkills(recommended)}>+ Add all ({recommended.length})</button>
          </div>
          <p>Add only the ones that are true for you.</p>
          <div className="re-suggest-chips">
            {recommended.map((s) => (
              <button key={s} type="button" onClick={() => edit.addSkills([s])} title={`Add ${s} to resume`}>+ {s}</button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export default function ResumeEditor({
  resume,
  setResume,
  job,
  apiBase = "",
  generatedOutput,
  savedSnapshot,
  isSaving,
  onSave,
  isRewriting,
  onImprove,
  scoring,
  recommendedSkills = [],
  fallbackPreview = null,
  onPdfReady,
  workspaceTab = "editor",
  onWorkspaceTab,
  onApply,
}) {
  const [section, setSection] = useState("summary");
  const [localWorkspaceTab, setLocalWorkspaceTab] = useState(workspaceTab);
  const [dismissedTip, setDismissedTip] = useState(null);
  const [focusKey, setFocusKey] = useState(null);
  const [settings, setSettings] = useState(loadPdfSettings);
  const [render, setRender] = useState({ pages: null, blob: null, size: null, density: null });
  const [, force] = useReducer((n) => n + 1, 0);
  const rootRef = useRef(null);
  const pendingFocus = useRef(null);
  const history = useRef({ past: [], future: [], last: resume, at: 0, skip: false });
  const attempted = useRef(null);
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const activeWorkspaceTab = onWorkspaceTab ? workspaceTab : localWorkspaceTab;
  const changeWorkspaceTab = (tab) => {
    setLocalWorkspaceTab(tab);
    onWorkspaceTab?.(tab);
  };

  useEffect(() => {
    try {
      localStorage.setItem(PDF_SETTINGS_KEY, JSON.stringify(settings));
    } catch {
      /* private mode: settings just won't persist */
    }
  }, [settings]);

  // --- Undo / redo: edits made within a short window collapse into one step. ---
  useEffect(() => {
    const h = history.current;
    if (resume === h.last) return;
    if (h.skip) {
      h.skip = false;
      h.last = resume;
      return;
    }
    const now = Date.now();
    // Re-render only when the Undo/Redo buttons change state, not on every keystroke.
    const buttonsChange = h.past.length === 0 || h.future.length > 0;
    if (now - h.at > HISTORY_COALESCE_MS) {
      h.past.push(h.last);
      if (h.past.length > 100) h.past.shift();
    }
    h.at = now;
    h.future = [];
    h.last = resume;
    if (buttonsChange) force();
  }, [resume]);

  const undo = useCallback(() => {
    const h = history.current;
    if (!h.past.length) return;
    const prev = h.past.pop();
    h.future.push(h.last);
    h.skip = true;
    setResume(prev);
    force();
  }, [setResume]);

  const redo = useCallback(() => {
    const h = history.current;
    if (!h.future.length) return;
    const next = h.future.pop();
    h.past.push(h.last);
    h.skip = true;
    setResume(next);
    force();
  }, [setResume]);

  // --- Autosave: persists a couple of seconds after the last change. ---
  const dirty = !!savedSnapshot && resume !== savedSnapshot;
  useEffect(() => {
    if (!dirty || isSaving || attempted.current === resume) return undefined;
    const timer = setTimeout(() => {
      attempted.current = resume;
      onSaveRef.current();
    }, AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [dirty, isSaving, resume]);

  const saveNow = useCallback(() => {
    if (isSaving) return;
    attempted.current = resume;
    onSaveRef.current();
  }, [isSaving, resume]);

  const onKeyDown = (e) => {
    if (!(e.metaKey || e.ctrlKey)) return;
    const k = e.key.toLowerCase();
    if (k === "s") {
      e.preventDefault();
      saveNow();
    } else if (k === "z") {
      e.preventDefault();
      if (e.shiftKey) redo(); else undo();
    } else if (k === "y") {
      e.preventDefault();
      redo();
    }
  };

  // Move the caret into a bullet that was just created or deleted into.
  useEffect(() => {
    if (!pendingFocus.current) return;
    const el = rootRef.current?.querySelector(`[data-bullet-key="${pendingFocus.current}"]`);
    pendingFocus.current = null;
    if (el) {
      el.focus();
      const end = el.value.length;
      el.setSelectionRange?.(end, end);
    }
  });

  // --- Resume mutations. Each makes a fresh object so history and autosave can compare by reference. ---
  const edit = useMemo(() => {
    const upd = (fn) => setResume((prev) => fn(prev));
    const setList = (section, fn) => upd((prev) => ({ ...prev, [section]: fn([...(prev[section] || [])]) }));
    const setEntry = (section, i, fn) => setList(section, (list) => {
      if (!list[i]) return list;
      list[i] = fn(list[i]);
      return list;
    });
    return {
      personal: (field, val) => upd((p) => ({ ...p, personal_info: { ...p.personal_info, [field]: val } })),
      summary: (val) => upd((p) => ({ ...p, professional_summary: val })),
      updateEntryField: (section, i, field, val) =>
        setEntry(section, i, (e) => {
          const next = { ...e, [field]: val };
          if (field === "organization") next.company = val;
          if (field === "institution") next.organization = val;
          if (field === "degree") next.title = val;
          if (field === "title" && section === "education") next.degree = val;
          return next;
        }),
      addEntry: (section) =>
        setList(section, (list) => {
          list.push(
            section === "education"
              ? { degree: "", institution: "", dates: "", location: "", description: "", bullets: [] }
              : section === "certifications"
              ? { name: "", issuer: "", dates: "" }
              : section === "publications"
              ? { title: "", organization: "", dates: "", description: "", bullets: [] }
              : section === "achievements"
              ? { title: "", dates: "", description: "" }
              : { title: "", organization: "", dates: "", location: "", bullets: [] }
          );
          return list;
        }),
      removeEntry: (section, i) => setList(section, (list) => list.filter((_, k) => k !== i)),
      moveEntry: (section, from, to) => setList(section, (list) => arrayMove(list, from, to)),
      updateBullet: (section, ei, bi, val) =>
        setEntry(section, ei, (e) => {
          const bullets = [...(e.bullets || [])];
          bullets[bi] = val;
          return { ...e, bullets };
        }),
      insertBullets: (section, ei, at, lines) =>
        setEntry(section, ei, (e) => {
          const bullets = [...(e.bullets || [])];
          bullets.splice(at, 0, ...lines);
          return { ...e, bullets };
        }),
      replaceBulletWith: (section, ei, bi, lines) =>
        setEntry(section, ei, (e) => {
          const bullets = [...(e.bullets || [])];
          bullets.splice(bi, 1, ...lines);
          return { ...e, bullets };
        }),
      removeBullet: (section, ei, bi) =>
        setEntry(section, ei, (e) => ({ ...e, bullets: (e.bullets || []).filter((_, k) => k !== bi) })),
      moveBullet: (section, ei, from, to) =>
        setEntry(section, ei, (e) => ({ ...e, bullets: arrayMove(e.bullets || [], from, to) })),
      addSkills: (skills) =>
        upd((p) => {
          const have = new Set((p.skills || []).map((s) => s.toLowerCase()));
          const fresh = [];
          for (const s of skills) {
            const t = String(s).trim();
            if (t && !have.has(t.toLowerCase())) {
              have.add(t.toLowerCase());
              fresh.push(t);
            }
          }
          return fresh.length ? { ...p, skills: [...(p.skills || []), ...fresh] } : p;
        }),
      removeSkill: (skill) => upd((p) => ({ ...p, skills: (p.skills || []).filter((s) => s !== skill) })),
      moveSkill: (from, to) => upd((p) => ({ ...p, skills: arrayMove(p.skills || [], from, to) })),
    };
  }, [setResume]);

  const sections = scoring?.analysis?.sections || {};
  const have = new Set((resume.skills || []).map((s) => s.toLowerCase()));
  const suggestions = recommendedSkills.filter((s) => !have.has(String(s).toLowerCase()));
  const idx = EDITOR_SECTIONS.findIndex(([k]) => k === section);
  const prevSection = EDITOR_SECTIONS[idx - 1];
  const nextSection = EDITOR_SECTIONS[idx + 1];
  const current = EDITOR_SECTIONS[idx] || EDITOR_SECTIONS[1];
  const info = resume.personal_info || {};
  const summaryText = resume.professional_summary || "";
  const summaryWords = summaryText.trim() ? summaryText.trim().split(/\s+/).length : 0;
  const tip = scoring?.analysis?.suggestions?.[0];
  const tipText = tip ? (typeof tip === "string" ? tip : tip.text) : "";
  const h = history.current;

  const candidateName = (info.name || "").trim().replace(/\s+/g, "_");
  const targetRole = (resume.target_role || job?.title || "").trim().replace(/\s+/g, "_");
  const companyName = (job?.company || "").trim().replace(/\s+/g, "_");
  const fileBase = [candidateName, targetRole, companyName, "Resume"]
    .filter(Boolean)
    .join("_")
    .replace(/[^\w\-]+/g, "")
    .replace(/_+/g, "_")
    .trim() || "Resume";
  const downloadPdf = () => saveBlob(render.blob, `${fileBase}.pdf`);
  // The DOCX is built on the server from the last save, so unsaved edits are saved first.
  // Fetched (not linked) so the app's auth headers are sent; guest sessions have no URL token.
  const [docxBusy, setDocxBusy] = useState(false);
  const [docxError, setDocxError] = useState("");
  const downloadDocx = async () => {
    if (!generatedOutput?.docx_url || docxBusy) return;
    setDocxBusy(true);
    setDocxError("");
    try {
      if (dirty) {
        attempted.current = resume;
        await onSaveRef.current();
      }
      const response = await fetch(`${apiBase}${generatedOutput.docx_url}`);
      if (!response.ok) throw new Error(`DOCX download failed (${response.status}).`);
      saveBlob(await response.blob(), `${fileBase}.docx`);
    } catch (e) {
      setDocxError(e.message || "DOCX download failed.");
    } finally {
      setDocxBusy(false);
    }
  };
  // Lets the page's own Download Resume button hand out this same PDF.
  useEffect(() => {
    onPdfReady?.(render.blob ? { blob: render.blob, name: `${fileBase}.pdf` } : null);
  }, [render.blob, fileBase, onPdfReady]);

  const common = { isRewriting, focusKey, setFocusKey, edit, onImprove, pendingFocus };

  return (
    <div className="re-shell" ref={rootRef} onKeyDown={onKeyDown}>
      <header className="re-contextbar">
        <span className={`re-autosaved ${dirty || isSaving ? "pending" : ""}`} role="status" aria-live="polite">
          <span className="re-autosaved-dot" aria-hidden="true" />
          {isSaving ? "Saving…" : dirty ? "Unsaved changes" : "All changes saved"}
        </span>
        <div className="re-view-tabs" role="tablist" aria-label="Resume workspace view">
          {WORKSPACE_TABS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={activeWorkspaceTab === key}
              className={activeWorkspaceTab === key ? "active" : ""}
              onClick={() => changeWorkspaceTab(key)}
            >
              {label}
              {key === "ats" && <span className="re-tab-dot" aria-hidden="true" />}
            </button>
          ))}
        </div>
        <span className="re-target" title={job?.title || "Not set"}>
          <small>Target Role:</small>
          <strong>{job?.title || "Not set"}</strong>
        </span>
        <div className="re-context-actions">
          {generatedOutput?.docx_url && (
            <button type="button" className="re-context-action" onClick={downloadDocx} disabled={docxBusy} title={docxError || "Download as Word (DOCX)"}>
              <FileText size={13} aria-hidden="true" /> {docxBusy ? "Preparing…" : docxError ? "Retry DOCX" : "DOCX"}
            </button>
          )}
          <button type="button" className="re-context-action primary" onClick={downloadPdf} disabled={!render.blob}>
            <Download size={13} aria-hidden="true" /> Export PDF
          </button>
        </div>
      </header>

      {activeWorkspaceTab === "editor" && <>
      <div className="re-form">
        <nav className="re-nav" aria-label="Structured editor sections">
          {EDITOR_SECTIONS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={section === key ? "active" : ""}
              aria-current={section === key ? "true" : undefined}
              onClick={() => setSection(key)}
            >
              {key !== "personal" && sections[key] ? (
                <SectionScoreBadge section={sections[key]} variant="dot" />
              ) : (
                <span className="re-nav-dot" aria-hidden="true" />
              )}
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <EditorMatchScore
          {...scoring}
          targetRole={job?.title}
          onInspect={() => changeWorkspaceTab("ats")}
        />

        <div className="re-section">
          <div className="re-section-heading">
            <h2>{current[2]}</h2>
            <span>Step {Math.max(1, idx + 1)} of {EDITOR_SECTIONS.length}</span>
          </div>
          <p className="re-section-hint">{current[3]}</p>
          {section === "personal" && (
            <div className="re-field-grid">
              <input type="text" className="editor-input re-span" placeholder="Full Name" value={info.name || ""} onChange={(e) => edit.personal("name", e.target.value)} aria-label="Full name" />
              <input type="email" className="editor-input" placeholder="Email Address" value={info.email || ""} onChange={(e) => edit.personal("email", e.target.value)} aria-label="Candidate email" />
              <input type="tel" className="editor-input" placeholder="Phone" value={info.phone || ""} onChange={(e) => edit.personal("phone", e.target.value)} aria-label="Candidate phone" />
              <input type="text" className="editor-input" placeholder="Location" value={info.location || ""} onChange={(e) => edit.personal("location", e.target.value)} aria-label="Location" />
              <input type="text" className="editor-input" placeholder="LinkedIn (username or URL)" value={info.linkedin || ""} onChange={(e) => edit.personal("linkedin", e.target.value)} aria-label="LinkedIn profile" />
              <input type="text" className="editor-input" placeholder="GitHub (username or URL)" value={info.github || ""} onChange={(e) => edit.personal("github", e.target.value)} aria-label="GitHub profile" />
              <input type="text" className="editor-input" placeholder="Portfolio / website" value={info.portfolio || ""} onChange={(e) => edit.personal("portfolio", e.target.value)} aria-label="Portfolio website" />
            </div>
          )}

          {section === "summary" && (
            <>
              <div className="re-composer">
                <div className="re-composer-bar">
                  <span className="re-composer-meta">
                    {summaryWords} words{job?.title ? <> · Tone: <b>Targeted to {job.title}</b></> : null}
                  </span>
                  <span className={`re-composer-count ${summaryText.length > 500 ? "over" : ""}`}>
                    {summaryText.length} / 500 chars
                  </span>
                </div>
                <AutoTextarea
                  className="re-summary"
                  value={summaryText}
                  onChange={(e) => edit.summary(e.target.value)}
                  aria-label="Professional summary"
                  placeholder="Two or three sentences: who you are, what you do best, what you want next."
                />
                <div className="re-composer-foot">
                  <button type="button" className="btn-improve-ai re-ai-primary" onClick={() => onImprove("professional_summary")} disabled={isRewriting}>
                    <Sparkles size={14} aria-hidden="true" /> {isRewriting ? "Improving with AI…" : "AI Enhance & Optimize"}
                  </button>
                  <span className="re-composer-history">
                    <button type="button" className="re-icon-btn" onClick={undo} disabled={!h.past.length} title="Undo (Ctrl+Z)" aria-label="Undo">
                      <Undo2 size={15} aria-hidden="true" />
                    </button>
                    <button type="button" className="re-icon-btn" onClick={redo} disabled={!h.future.length} title="Redo (Ctrl+Y)" aria-label="Redo">
                      <Redo2 size={15} aria-hidden="true" />
                    </button>
                  </span>
                </div>
              </div>
              {tipText && dismissedTip !== tipText && (
                <div className="re-recommendation">
                  <div className="re-recommendation-head">
                    <strong><span className="re-rec-dot" aria-hidden="true" /> AI Executive Review Recommendation</strong>
                    {tip.confidence && <code>Confidence: {tip.confidence}</code>}
                  </div>
                  <p>{tipText}</p>
                  <div className="re-recommendation-actions">
                    <button type="button" className="btn-improve-ai re-ai-primary" onClick={() => onImprove("professional_summary")} disabled={isRewriting}>Apply Recommendation</button>
                    <button type="button" className="re-dismiss" onClick={() => setDismissedTip(tipText)}>Dismiss</button>
                  </div>
                </div>
              )}
            </>
          )}

          {section === "skills" && <SkillsEditor skills={resume.skills || []} recommended={suggestions.slice(0, 15)} edit={edit} />}

          {section === "experience" && (
            <EntryList
              {...common}
              section="experience"
              entries={resume.experience || []}
              hasBullets
              titleOf={(e) => [e.title, e.organization].filter(Boolean).join(" — ")}
              addLabel="+ Add Work Experience Entry"
              fields={[
                ["title", "Job Title", "Experience job title"],
                ["organization", "Company / Organization", "Experience company"],
                ["dates", "Dates (e.g. Aug 2024 - Present)", "Experience dates"],
                ["location", "Location", "Experience location"],
              ]}
            />
          )}

          {section === "internships" && (
            <EntryList
              {...common}
              section="internships"
              entries={resume.internships || []}
              hasBullets
              hasDescription
              titleOf={(e) => [e.title, e.organization].filter(Boolean).join(" — ")}
              addLabel="+ Add Internship Entry"
              fields={[
                ["title", "Internship Role", "Internship title"],
                ["organization", "Company / Organization", "Internship company"],
                ["dates", "Dates", "Internship dates"],
                ["location", "Location", "Internship location"],
              ]}
            />
          )}

          {section === "projects" && (
            <EntryList
              {...common}
              section="projects"
              entries={resume.projects || []}
              hasBullets
              hasDescription
              titleOf={(e) => e.title}
              addLabel="+ Add Project Entry"
              fields={[
                ["title", "Project Name / Title", "Project title"],
                ["organization", "Organization / Tech Stack", "Project organization"],
                ["dates", "Dates", "Project dates"],
              ]}
            />
          )}

          {section === "publications" && (
            <EntryList
              {...common}
              section="publications"
              entries={resume.publications || []}
              hasDescription
              titleOf={(e) => e.title}
              addLabel="+ Add Publication"
              fields={[
                ["title", "Publication / Paper Title", "Publication title"],
                ["organization", "Journal / Conference", "Publication venue"],
                ["dates", "Year", "Publication year"],
              ]}
            />
          )}

          {section === "education" && (
            <EntryList
              {...common}
              section="education"
              entries={resume.education || []}
              hasDescription
              improveDescription
              titleOf={(e) => [e.degree || e.title, e.institution || e.organization].filter(Boolean).join(" — ")}
              addLabel="+ Add Education Entry"
              fields={[
                ["degree", "Degree", "Education degree"],
                ["institution", "Institution / School", "Education institution"],
                ["dates", "Dates", "Education dates"],
                ["location", "Location", "Education location"],
              ]}
            />
          )}

          {section === "certifications" && (
            <EntryList
              {...common}
              section="certifications"
              entries={resume.certifications || []}
              titleOf={(e) => e.name}
              addLabel="+ Add Certification"
              fields={[
                ["name", "Certification name", "Certification name"],
                ["issuer", "Issuer", "Certification issuer"],
                ["dates", "Date", "Certification date"],
              ]}
            />
          )}

          {section === "achievements" && (
            <EntryList
              {...common}
              section="achievements"
              entries={resume.achievements || []}
              hasDescription
              titleOf={(e) => e.title}
              addLabel="+ Add Achievement"
              fields={[
                ["title", "Achievement / Award", "Achievement title"],
                ["dates", "Date", "Achievement date"],
              ]}
            />
          )}
        </div>

        <div className="re-pager">
          <button type="button" className="pipeline-btn-secondary" disabled={!prevSection} onClick={() => prevSection && setSection(prevSection[0])}>
            <ArrowLeft size={14} aria-hidden="true" /> {prevSection ? prevSection[1] : "Back"}
          </button>
          <button type="button" className="pipeline-btn-secondary" disabled={!nextSection} onClick={() => nextSection && setSection(nextSection[0])}>
            {nextSection ? nextSection[1] : "Next"} <ArrowRight size={14} aria-hidden="true" />
          </button>
        </div>
        {onApply && (
          <button type="button" className="re-apply-button" onClick={onApply}>
            Apply now <ExternalLink size={15} aria-hidden="true" />
          </button>
        )}
      </div>

      <aside className="re-preview" aria-label="Resume preview">
        <div className="re-toolbar">
          <label>
            Font
            <select value={settings.font} onChange={(e) => setSettings((s) => ({ ...s, font: e.target.value }))}>
              {PDF_FONTS.map((f) => <option key={f} value={f}>{FONT_LABELS[f] || f}</option>)}
            </select>
          </label>
          <label>
            Size
            <select value={settings.fontSize} onChange={(e) => setSettings((s) => ({ ...s, fontSize: Number(e.target.value) }))}>
              {[8.5, 9, 9.5, 10, 10.5, 11, 11.5].map((n) => <option key={n} value={n}>{n} pt</option>)}
            </select>
          </label>
          <label>
            Spacing
            <select value={settings.density} onChange={(e) => setSettings((s) => ({ ...s, density: e.target.value }))}>
              <option value="compact">Compact</option>
              <option value="normal">Standard</option>
              <option value="relaxed">Relaxed</option>
            </select>
          </label>
          <span className="re-swatches" role="group" aria-label="Accent colour">
            <span className="re-swatch-label">Theme</span>
            {PDF_ACCENTS.map((c) => (
              <button
                key={c}
                type="button"
                className={settings.accent === c ? "active" : ""}
                style={{ background: c }}
                aria-label={`Accent ${c}`}
                aria-pressed={settings.accent === c}
                onClick={() => setSettings((s) => ({ ...s, accent: c }))}
              />
            ))}
          </span>
          <span className="re-toolbar-end">
            <span className={`re-pages ${render.pages > 1 ? "over" : render.pages === 1 ? "ok" : ""}`}>
              {render.pages == null ? "Rendering…" : render.pages === 1 ? "1 page · A4" : `${render.pages} pages · over one page`}
              {render.pages === 1 && settings.autoFit && render.size && render.size < settings.fontSize ? ` · ${render.size} pt` : ""}
            </span>
            <label className="re-check">
              <input type="checkbox" checked={settings.autoFit} onChange={(e) => setSettings((s) => ({ ...s, autoFit: e.target.checked }))} />
              Auto-fit to 1 page
            </label>
          </span>
        </div>

        <div className="re-frame">
          <PreviewBoundary fallback={fallbackPreview}>
            <Suspense fallback={<div className="re-loading">Loading preview…</div>}>
              <PdfPreview resume={resume} settings={settings} onRendered={setRender} />
            </Suspense>
          </PreviewBoundary>
        </div>
      </aside>
      </>}
      {activeWorkspaceTab === "preview" && (
        <section className="re-full-view" aria-label="Preview and test resume">
          <div className="re-toolbar re-full-toolbar">
            <label>
              Font
              <select value={settings.font} onChange={(e) => setSettings((s) => ({ ...s, font: e.target.value }))}>
                {PDF_FONTS.map((font) => <option key={font} value={font}>{FONT_LABELS[font] || font}</option>)}
              </select>
            </label>
            <label>
              Size
              <select value={settings.fontSize} onChange={(e) => setSettings((s) => ({ ...s, fontSize: Number(e.target.value) }))}>
                {[8.5, 9, 9.5, 10, 10.5, 11, 11.5].map((size) => <option key={size} value={size}>{size} pt</option>)}
              </select>
            </label>
            <label>
              Spacing
              <select value={settings.density} onChange={(e) => setSettings((s) => ({ ...s, density: e.target.value }))}>
                <option value="compact">Compact</option>
                <option value="normal">Standard</option>
                <option value="relaxed">Relaxed</option>
              </select>
            </label>
            <span className={`re-pages ${render.pages > 1 ? "over" : render.pages === 1 ? "ok" : ""}`}>
              {render.pages == null ? "Rendering…" : render.pages === 1 ? "1 page · A4" : `${render.pages} pages`}
            </span>
          </div>
          <div className="re-full-preview-frame">
            <PreviewBoundary>
              <Suspense fallback={<div className="re-loading">Loading PDF preview…</div>}>
                <PdfPreview resume={resume} settings={settings} onRendered={setRender} />
              </Suspense>
            </PreviewBoundary>
          </div>
        </section>
      )}
      {activeWorkspaceTab === "ats" && (
        <AtsInsights
          resume={resume}
          job={job}
          scoring={scoring}
          isRewriting={isRewriting}
          onImprove={onImprove}
          onNavigateToSection={(nextSection) => {
            setSection(nextSection);
            changeWorkspaceTab("editor");
          }}
        />
      )}
    </div>
  );
}

function AtsInsights({ resume, job, scoring, isRewriting, onImprove, onNavigateToSection }) {
  const [priorityOnly, setPriorityOnly] = useState(false);
  const [showMetricExamples, setShowMetricExamples] = useState(false);
  const analysis = scoring?.analysis;
  const missingSkills = Array.from(new Set(analysis?.missing_skills || []))
    .filter((skill) => String(skill).trim())
    .slice(0, 5);
  const suggestions = (analysis?.suggestions || [])
    .map((item) => typeof item === "string" ? item : item?.text)
    .filter(Boolean);
  const summary = String(resume.professional_summary || "").trim();
  const bullets = [
    ...(resume.experience || []),
    ...(resume.internships || []),
    ...(resume.projects || []),
  ].flatMap((entry) => entry.bullets || []);
  const quantifiedBullets = bullets.filter((bullet) => /\d/.test(bullet)).length;
  const languagePatterns = /\b(c\+\+|c#|java|python|javascript|typescript|go|rust|sql|kotlin|swift|ruby|php)\b/i;
  const verifiedLanguages = Array.from(new Set((resume.skills || []).filter((skill) => languagePatterns.test(skill)))).slice(0, 6);
  const roleTitle = job?.title || "your target role";
  const matchScore = Number.isFinite(analysis?.job_match_score) ? analysis.job_match_score : null;
  const recommendationCount = 4 + (suggestions.length > 0 ? 1 : 0);

  return (
    <section className="re-full-view re-ats-view" aria-label="ATS insights and recommendations">
      <header className="re-ats-header">
        <div>
          <div className="re-ats-title-row">
            <h2>ATS Insights</h2>
            <span className="re-ats-live"><span /> Live evaluation</span>
          </div>
          <p>Practical, role-specific ways to strengthen this résumé for <strong>{roleTitle}</strong>. Scores are Cafy estimates, not an employer ATS result.</p>
        </div>
        <div className="re-ats-score-group">
          <div className="re-ats-score-box" aria-label={matchScore == null ? "Job match score updating" : `${matchScore}% Cafy job match estimate`}>
            <div><span>Job match · Cafy estimate</span><strong>{matchScore == null ? "—" : `${matchScore}%`}</strong></div>
            <span className="re-ats-score-ring" style={{ "--match-progress": `${matchScore ?? 0}%` }}>{matchScore == null ? "…" : `${matchScore}%`}</span>
          </div>
          {analysis?.cv_quality && (
            <div className="re-ats-score-box re-cv-quality-box" aria-label={`${analysis.cv_quality.score}% CV content score`}>
              <div>
                <span>CV content score</span>
                <strong>{analysis.cv_quality.score}%</strong>
                <small>{analysis.cv_quality.passed_checks}/{analysis.cv_quality.total_checks} checks passed</small>
              </div>
            </div>
          )}
        </div>
      </header>
      {scoring?.isAnalyzing && <p className="re-ats-status" role="status">Updating your match analysis…</p>}
      {scoring?.error && <p className="re-ats-status" role="alert">{scoring.error}</p>}

      <section className="re-ats-actions" aria-label="Actionable recommendations">
        <header className="re-ats-actions-header">
          <div>
            <div className="re-ats-actions-title">
              <h3>Actionable Recommendations</h3>
              <span>{priorityOnly ? "2 prioritized fixes" : `${recommendationCount} recommendations`}</span>
            </div>
            <p>High-impact changes to strengthen your résumé for this role.</p>
          </div>
          <button
            type="button"
            className={`re-ats-filter ${priorityOnly ? "active" : ""}`}
            aria-pressed={priorityOnly}
            onClick={() => setPriorityOnly((value) => !value)}
          >
            <SlidersHorizontal size={15} aria-hidden="true" /> {priorityOnly ? "Show all" : "Filter"}
          </button>
        </header>

        <div className="re-ats-recommendation-grid">
          <article className="re-ats-recommendation re-ats-summary-recommendation">
            <span className="re-ats-dot priority" aria-hidden="true" />
            <div className="re-ats-recommendation-main">
              <div className="re-ats-recommendation-title">
                <h4>Strengthen your opening summary</h4>
                <span>High leverage</span>
                <button type="button" onClick={() => onImprove?.("professional_summary")} disabled={isRewriting || !onImprove}>
                  <Sparkles size={14} aria-hidden="true" /> {isRewriting ? "Improving…" : "Improve with AI"}
                </button>
              </div>
              <p>{summary ? `${summary.split(/\s+/).length} words. Focus on strengths and impact relevant to ${roleTitle}.` : "Add a concise summary focused on your relevant strengths and target role."}</p>
            </div>
          </article>

          <article className="re-ats-recommendation">
            <span className="re-ats-dot" aria-hidden="true" />
            <div className="re-ats-recommendation-main">
              <h4>Use measurable evidence</h4>
              <p>{quantifiedBullets} of {bullets.length} experience and project bullets include a number. Add truthful scope or outcomes where possible.</p>
              <footer><span>Target: quantify key outcomes</span><button type="button" onClick={() => setShowMetricExamples((value) => !value)}>{showMetricExamples ? "Hide examples" : "View examples"}</button></footer>
              {showMetricExamples && <p className="re-ats-example">Examples: “reduced processing time by 20%”, “supported 12 clients”, or “automated 4 weekly reports” — use only figures you can verify.</p>}
            </div>
          </article>

          {!priorityOnly && (
            <article className="re-ats-recommendation">
              <span className="re-ats-dot" aria-hidden="true" />
              <div className="re-ats-recommendation-main">
                <h4>Role keyword coverage</h4>
                <p>{missingSkills.length ? <>The role lists <strong>{missingSkills.join(", ")}</strong>. Add a term only if you genuinely have the experience.</> : "Your résumé currently covers the identified role skills."}</p>
                <footer><span>{missingSkills.length} missing target keywords</span><button type="button" onClick={() => onNavigateToSection?.("skills")}>Review skills <ArrowRight size={13} aria-hidden="true" /></button></footer>
              </div>
            </article>
          )}

          {!priorityOnly && (
            <article className="re-ats-recommendation">
              <span className="re-ats-dot" aria-hidden="true" />
              <div className="re-ats-recommendation-main">
                <h4>Evidence technical languages</h4>
                <p>{verifiedLanguages.length
                  ? <>Back up <strong>{verifiedLanguages.join(", ")}</strong> with a project or experience bullet showing where you used them.</>
                  : "If you list programming languages, add a project or experience bullet showing how you used each one."}</p>
                <footer><span>Core language verification</span><button type="button" onClick={() => onNavigateToSection?.("projects")}>Map to project <ArrowRight size={13} aria-hidden="true" /></button></footer>
              </div>
            </article>
          )}

          {!priorityOnly && suggestions.slice(0, 1).map((suggestion) => (
            <article className="re-ats-recommendation" key={suggestion}>
              <span className="re-ats-dot" aria-hidden="true" />
              <div className="re-ats-recommendation-main"><h4>Match insight</h4><p>{suggestion}</p></div>
            </article>
          ))}
        </div>

        {!priorityOnly && missingSkills.length > 0 && (
          <div className="re-ats-learning-links">
            <strong><BookOpen size={15} aria-hidden="true" /> Learning resources</strong>
            <div>{missingSkills.map((skill) => {
              const resource = learningResource(skill);
              return <a key={skill} href={resource.href} target="_blank" rel="noopener noreferrer">{skill}: {resource.label}<ExternalLink size={12} aria-hidden="true" /></a>;
            })}</div>
          </div>
        )}
        <p className="re-ats-note">Use recommendations as guidance; only include claims you can support with real experience or study.</p>
      </section>
    </section>
  );
}

const LEARNING_RESOURCES = [
  { pattern: /customer service/i, label: "Customer service skills", href: "https://www.skillsyouneed.com/ips/customer-service.html", description: "Communication, active listening, and handling customer needs." },
  { pattern: /customs|import|export/i, label: "UK import and export guidance", href: "https://www.gov.uk/topic/business-tax/import-export", description: "Official guidance on customs processes and trade requirements." },
  { pattern: /databricks/i, label: "Databricks Academy", href: "https://www.databricks.com/learn/training/home", description: "Training paths and learning materials from Databricks." },
  { pattern: /looker/i, label: "Looker learning resources", href: "https://cloud.google.com/looker/docs/learning-resources", description: "Documentation and training resources from Google Cloud." },
  { pattern: /machin(?:e|ing)|cnc/i, label: "Machining courses", href: "https://www.coursera.org/search?query=machining", description: "Browse structured courses related to machining and manufacturing." },
  { pattern: /mentor/i, label: "CIPD mentoring guidance", href: "https://www.cipd.org/en/knowledge/factsheets/coaching-mentoring-factsheet/", description: "Guidance on coaching and mentoring at work." },
  { pattern: /onboarding/i, label: "CIPD induction guidance", href: "https://www.cipd.org/en/knowledge/factsheets/induction-factsheet/", description: "Practical guidance for welcoming and supporting new starters." },
  { pattern: /recruit|hiring/i, label: "CIPD recruitment guidance", href: "https://www.cipd.org/en/knowledge/factsheets/recruitment-factsheet/", description: "Guidance on fair and effective recruitment practices." },
  { pattern: /react/i, label: "React Learn", href: "https://react.dev/learn", description: "Official interactive introduction to React." },
  { pattern: /javascript|js\b/i, label: "MDN JavaScript Guide", href: "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide", description: "A comprehensive guide to the JavaScript language." },
  { pattern: /typescript/i, label: "TypeScript Handbook", href: "https://www.typescriptlang.org/docs/handbook/intro.html", description: "Official guide to TypeScript concepts and usage." },
  { pattern: /python/i, label: "Python Tutorial", href: "https://docs.python.org/3/tutorial/", description: "Official Python language tutorial." },
  { pattern: /aws|amazon web services/i, label: "AWS Skill Builder", href: "https://skillbuilder.aws/", description: "Digital courses and learning plans from AWS." },
  { pattern: /docker|container/i, label: "Docker Get Started", href: "https://docs.docker.com/get-started/", description: "Official hands-on introduction to Docker." },
  { pattern: /kubernetes|k8s/i, label: "Kubernetes Tutorials", href: "https://kubernetes.io/docs/tutorials/", description: "Official tutorials for learning Kubernetes." },
  { pattern: /sql|postgres|database/i, label: "SQLBolt Lessons", href: "https://sqlbolt.com/", description: "Interactive lessons for learning SQL." },
  { pattern: /git|github/i, label: "GitHub Skills", href: "https://skills.github.com/", description: "Interactive courses for GitHub workflows." },
];

function learningResource(skill) {
  return LEARNING_RESOURCES.find(({ pattern }) => pattern.test(skill))
    || {
      label: `Explore ${skill} courses`,
      href: `https://www.coursera.org/search?query=${encodeURIComponent(skill)}`,
      description: `Browse courses related to ${skill} and compare their level and prerequisites.`,
    };
}

class PreviewBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed) return this.props.fallback || <div className="re-loading">Preview unavailable.</div>;
    return this.props.children;
  }
}

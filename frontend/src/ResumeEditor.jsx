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
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  Download,
  FileText,
  GripVertical,
  Lightbulb,
  Redo2,
  Sparkles,
  Undo2,
  X,
} from "lucide-react";
import { EditorMatchScore, SectionScoreBadge } from "./JobMatchScore.jsx";
import { DEFAULT_PDF_SETTINGS, PDF_ACCENTS, PDF_FONTS } from "./pdfSettings.js";
import "./resumeEditor.css";

// The PDF renderer is large, so it loads only when the editor opens.
const PdfPreview = lazy(() => import("./PdfPreview.jsx"));

export const EDITOR_SECTIONS = [
  ["personal", "Personal Information"],
  ["summary", "Professional Summary"],
  ["skills", "Skills"],
  ["experience", "Work Experience"],
  ["projects", "Projects"],
  ["education", "Education"],
  ["certifications", "Certifications"],
];

const SETTINGS_KEY = "cafy.resumePdfSettings";
const AUTOSAVE_MS = 2000;
const HISTORY_COALESCE_MS = 900;

const ACTION_VERBS = new Set(
  ("led built ran wrote drove grew won cut set made took began brought chose created designed developed " +
    "delivered launched managed improved reduced increased automated implemented optimized migrated " +
    "architected analyzed collaborated mentored owned shipped deployed integrated streamlined established " +
    "resolved secured scaled trained coordinated spearheaded achieved generated accelerated refactored " +
    "maintained produced presented negotiated supported engineered configured monitored tested").split(" ")
);

function loadSettings() {
  try {
    return { ...DEFAULT_PDF_SETTINGS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") };
  } catch {
    return DEFAULT_PDF_SETTINGS;
  }
}

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
  const label = section === "projects" ? "Project" : "Experience";
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

function EntryList({ section, entries, fields, titleOf, addLabel, hasBullets, isRewriting, focusKey, setFocusKey, edit, onImprove, pendingFocus }) {
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
                    {hasBullets && (
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
}) {
  const [section, setSection] = useState("summary");
  const [focusKey, setFocusKey] = useState(null);
  const [settings, setSettings] = useState(loadSettings);
  const [render, setRender] = useState({ pages: null, blob: null, size: null, density: null });
  const [, force] = useReducer((n) => n + 1, 0);
  const rootRef = useRef(null);
  const pendingFocus = useRef(null);
  const history = useRef({ past: [], future: [], last: resume, at: 0, skip: false });
  const attempted = useRef(null);
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;

  useEffect(() => {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
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
    if (now - h.at > HISTORY_COALESCE_MS) {
      h.past.push(h.last);
      if (h.past.length > 100) h.past.shift();
    }
    h.at = now;
    h.future = [];
    h.last = resume;
    force();
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
              ? { degree: "", institution: "", dates: "", location: "", bullets: [] }
              : section === "certifications"
              ? { name: "", issuer: "", dates: "" }
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
  const info = resume.personal_info || {};

  const status = isSaving ? "Saving…" : dirty ? "Unsaved changes" : "All changes saved";
  const past = history.current.past.length;
  const future = history.current.future.length;

  const fileBase = [info.name, job?.company].filter(Boolean).join(" - ").replace(/[^\w\- ]+/g, "").trim() || "resume";
  const downloadPdf = () => saveBlob(render.blob, `${fileBase}.pdf`);
  // Lets the page's own Download Resume button hand out this same PDF.
  useEffect(() => {
    onPdfReady?.(render.blob ? { blob: render.blob, name: `${fileBase}.pdf` } : null);
  }, [render.blob, fileBase, onPdfReady]);

  const common = { isRewriting, focusKey, setFocusKey, edit, onImprove, pendingFocus };

  return (
    <div className="re-shell" ref={rootRef} onKeyDown={onKeyDown}>
      <div className="re-form">
        <div className="re-topbar">
          <span className={`re-status ${dirty || isSaving ? "pending" : "saved"}`} role="status" aria-live="polite">
            {dirty || isSaving ? <AlertCircle size={13} aria-hidden="true" /> : <Check size={13} aria-hidden="true" />} {status}
          </span>
          <span className="re-topbar-actions">
            <button type="button" className="btn-icon-action" onClick={undo} disabled={!past} title="Undo (Ctrl/Cmd+Z)" aria-label="Undo">
              <Undo2 size={15} aria-hidden="true" />
            </button>
            <button type="button" className="btn-icon-action" onClick={redo} disabled={!future} title="Redo (Ctrl/Cmd+Shift+Z)" aria-label="Redo">
              <Redo2 size={15} aria-hidden="true" />
            </button>
            <button type="button" className="pipeline-btn-primary re-save" onClick={saveNow} disabled={isSaving || !dirty} title="Save now (Ctrl/Cmd+S)">
              {isSaving ? "Saving…" : "Save"}
            </button>
          </span>
        </div>

        <nav className="re-nav" aria-label="Structured editor sections">
          {EDITOR_SECTIONS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={section === key ? "active" : ""}
              aria-current={section === key ? "true" : undefined}
              onClick={() => setSection(key)}
            >
              <span>{label}</span>
              {key !== "personal" && <SectionScoreBadge section={sections[key]} />}
            </button>
          ))}
        </nav>

        <EditorMatchScore {...scoring} />

        <div className="re-section">
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
              <AutoTextarea
                className="re-summary"
                value={resume.professional_summary || ""}
                onChange={(e) => edit.summary(e.target.value)}
                aria-label="Professional summary"
                placeholder="Two or three sentences: who you are, what you do best, what you want next."
              />
              <div className="re-row-between">
                <button type="button" className="btn-improve-ai" onClick={() => onImprove("professional_summary")} disabled={isRewriting}>
                  <Sparkles size={14} aria-hidden="true" /> {isRewriting ? "Improving with AI…" : "Improve with AI"}
                </button>
                <span className={`re-muted ${(resume.professional_summary || "").length > 500 ? "over" : ""}`}>
                  {(resume.professional_summary || "").length}/500
                </span>
              </div>
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

          {section === "projects" && (
            <EntryList
              {...common}
              section="projects"
              entries={resume.projects || []}
              hasBullets
              titleOf={(e) => e.title}
              addLabel="+ Add Project Entry"
              fields={[
                ["title", "Project Name / Title", "Project title"],
                ["organization", "Organization / Tech Stack", "Project organization"],
                ["dates", "Dates", "Project dates"],
              ]}
            />
          )}

          {section === "education" && (
            <EntryList
              {...common}
              section="education"
              entries={resume.education || []}
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
        </div>

        <div className="re-pager">
          <button type="button" className="pipeline-btn-secondary" disabled={!prevSection} onClick={() => prevSection && setSection(prevSection[0])}>
            <ArrowLeft size={14} aria-hidden="true" /> {prevSection ? prevSection[1] : "Back"}
          </button>
          <button type="button" className="pipeline-btn-secondary" disabled={!nextSection} onClick={() => nextSection && setSection(nextSection[0])}>
            {nextSection ? nextSection[1] : "Next"} <ArrowRight size={14} aria-hidden="true" />
          </button>
        </div>
      </div>

      <aside className="re-preview" aria-label="Resume preview">
        <div className="re-toolbar">
          <label>
            Font
            <select value={settings.font} onChange={(e) => setSettings((s) => ({ ...s, font: e.target.value }))}>
              {PDF_FONTS.map((f) => <option key={f} value={f}>{f.replace("-Roman", "")}</option>)}
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
              <option value="normal">Normal</option>
              <option value="relaxed">Relaxed</option>
            </select>
          </label>
          <span className="re-swatches" role="group" aria-label="Accent colour">
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
          <label className="re-check">
            <input type="checkbox" checked={settings.autoFit} onChange={(e) => setSettings((s) => ({ ...s, autoFit: e.target.checked }))} />
            Auto-fit to 1 page
          </label>
        </div>

        <div className="re-preview-head">
          <span className={`re-pages ${render.pages > 1 ? "over" : render.pages === 1 ? "ok" : ""}`}>
            {render.pages == null ? "Rendering…" : render.pages === 1 ? "1 page · A4" : `${render.pages} pages · over one page`}
            {render.pages === 1 && settings.autoFit && render.size && render.size < settings.fontSize ? ` · shrunk to ${render.size} pt` : ""}
          </span>
          <span className="re-preview-actions">
            <button type="button" className="pipeline-btn-primary" onClick={downloadPdf} disabled={!render.blob}>
              <Download size={14} aria-hidden="true" /> Save PDF
            </button>
            {generatedOutput?.docx_url && (
              <a className="pipeline-btn-secondary re-link" href={`${apiBase}${generatedOutput.docx_url}`} download>
                <FileText size={14} aria-hidden="true" /> DOCX
              </a>
            )}
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
    </div>
  );
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

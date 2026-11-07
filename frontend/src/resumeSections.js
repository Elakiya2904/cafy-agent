// Canonical resume sections for every on-screen and PDF rendering.
// Mirrors backend/resume_structure.py (section titles, order, entry lines, date style) so the
// in-app preview, the React-PDF export and the server's DOCX/LaTeX exports all show the same
// sections in the same order with the same content.

export const SECTION_TITLES = {
  summary: "About Me",
  experience: "Work Experience",
  internships: "Internship Experience",
  education: "Education",
  projects: "Projects",
  skills: "Skills",
  certifications: "Certifications",
  publications: "Publications",
  achievements: "Achievements",
};

// The UK template prints exactly these five sections, in this order. Full-time roles and
// internships share "Work Experience" (full-time first). Certifications, publications and
// achievements stay in the data and the editor but are not printed.
export const PRINTED_SECTIONS = ["summary", "education", "experience", "projects", "skills"];

export const ENTRY_SECTIONS = ["experience", "internships", "education", "projects", "certifications", "publications", "achievements"];

const text = (value) => String(value ?? "").replace(/\s+/g, " ").trim();

const MONTHS = {
  jan: "Jan", january: "Jan", feb: "Feb", february: "Feb", mar: "Mar", march: "Mar", apr: "Apr", april: "Apr",
  may: "May", jun: "Jun", june: "Jun", jul: "Jul", july: "Jul", aug: "Aug", august: "Aug", sep: "Sep", sept: "Sep",
  september: "Sep", oct: "Oct", october: "Oct", nov: "Nov", november: "Nov", dec: "Dec", december: "Dec",
};
const MONTH_NUMBERS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_WORD = new RegExp(`\\b(${Object.keys(MONTHS).sort((a, b) => b.length - a.length).join("|")})\\.?(?=\\s*'?\\d)`, "gi");

/** "September 2023 - present" -> "Sep 2023 – Present". Reformats only; never invents a date. */
export function standardizeDates(value) {
  let t = text(value).replace(/^[([\s]+|[)\]\s]+$/g, "");
  if (!t) return "";
  t = t.replace(/\b(0?[1-9]|1[0-2])\s*\/\s*((?:19|20)\d{2})\b/g, (_, m, y) => `${MONTH_NUMBERS[Number(m) - 1]} ${y}`);
  t = t.replace(MONTH_WORD, (m) => MONTHS[m.replace(".", "").toLowerCase()] || m);
  t = t.replace(/\b(?:present|currently|current|now|ongoing|date)\b/gi, "Present");
  const parts = t.split(/\s*(?:-{1,2}|–|—|\bto\b|\buntil\b)\s*/i);
  if (parts.length === 2 && parts.every((p) => /(?:19|20)\d{2}|Present/.test(p))) t = `${parts[0].trim()} – ${parts[1].trim()}`;
  return t.replace(/\s{2,}/g, " ").trim();
}

const key = (value) => String(value ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "");
const titleOf = (e) => text(e?.title || e?.role || e?.name || e?.degree);
const orgOf = (e) => text(e?.organization || e?.company || e?.institution || e?.school || e?.issuer || e?.venue || e?.publisher);
const sameDates = (a, b) => !text(a) || !text(b) || key(standardizeDates(a)) === key(standardizeDates(b));

const STOPWORDS = new Set(["the", "and", "for", "with", "using", "via", "into", "from", "that", "this", "was", "were", "are",
  "its", "our", "their", "as", "of", "in", "on", "to", "at", "by", "an", "a", "well"]);

function contentWords(value) {
  const words = new Set();
  for (const raw of String(value ?? "").toLowerCase().match(/[a-z0-9][a-z0-9.+#/-]*/g) || []) {
    let w = raw.replace(/^[.\-/]+|[.\-/]+$/g, "");
    // Numbers always count ("thing 1" and "thing 2" differ); other 1-letter tokens do not.
    if (!w || STOPWORDS.has(w) || (w.length < 2 && !/^\d+$/.test(w))) continue;
    for (const suffix of ["ing", "ed", "es", "s"]) {
      if (w.length - suffix.length >= 4 && w.endsWith(suffix)) { w = w.slice(0, -suffix.length); break; }
    }
    words.add(w);
  }
  return words;
}

// True when (almost) every content word of `value` already appears in `other`.
function repeats(value, other, threshold) {
  const words = contentWords(value);
  if (!words.size) return false;
  // Short lines only count as repeats when every word matches.
  if (words.size < 4) threshold = 1;
  const otherWords = contentWords(other);
  let shared = 0;
  for (const w of words) if (otherWords.has(w)) shared += 1;
  return shared / words.size >= threshold;
}

// Two lines make the same point: they share most words in BOTH directions (mirrors backend _same_point).
function samePoint(a, b, threshold = 0.85) {
  const wa = contentWords(a);
  const wb = contentWords(b);
  if (!wa.size || !wb.size) return false;
  let shared = 0;
  for (const w of wa) if (wb.has(w)) shared += 1;
  return shared / Math.max(wa.size, wb.size) >= (Math.min(wa.size, wb.size) < 4 ? 1 : threshold);
}

/**
 * Drop text that only repeats what the entry already says (mirrors backend without_repeats):
 * a description restating the heading line or summarising the bullets, and repeated bullets.
 */
export function withoutRepeats(entry) {
  if (!entry || typeof entry !== "object") return entry;
  const heading = ["title", "name", "degree", "organization", "company", "institution", "issuer", "location", "dates"]
    .map((k) => text(entry[k])).join(" ");
  const bullets = (entry.bullets || []).filter((b) => text(b));
  let description = text(entry.description);
  if (description && (repeats(description, heading, 0.8) || (bullets.length && repeats(description, `${heading} ${bullets.join(" ")}`, 0.75)))) {
    description = "";
  }
  const kept = [];
  for (const b of bullets) {
    if (kept.some((k) => samePoint(b, k)) || (description && samePoint(b, description)) || repeats(b, heading, 0.9)) continue;
    kept.push(b);
  }
  return { ...entry, description, bullets: kept };
}

/** True when two entries are the same role / degree / item (dates must not conflict). */
export function sameRecord(a, b, section = "experience") {
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  if (!sameDates(a.dates, b.dates)) return false;
  const [ta, tb, oa, ob] = [key(titleOf(a)), key(titleOf(b)), key(orgOf(a)), key(orgOf(b))];
  if (ta && ta === tb && oa === ob) return true;
  if (section === "education") {
    if (oa && oa === ob && (!ta || !tb)) return true;
    if (ta && ta === tb && (!oa || !ob)) return true;
  }
  return false;
}

/** Merge repeated records; missing fields and extra bullets from a copy are kept, never lost. */
export function dedupeEntries(entries, section = "experience") {
  return mergeRecords(entries, section).map(withoutRepeats);
}

function mergeRecords(entries, section) {
  const out = [];
  for (const entry of entries || []) {
    if (!entry || typeof entry !== "object") continue;
    const kept = out.find((e) => sameRecord(e, entry, section));
    if (!kept) {
      out.push({ ...entry, bullets: [...(entry.bullets || [])] });
      continue;
    }
    for (const [field, value] of Object.entries(entry)) {
      if (field !== "bullets" && !text(kept[field]) && text(value)) kept[field] = value;
    }
    if (text(entry.description).length > text(kept.description).length) kept.description = entry.description;
    const seen = new Set(kept.bullets.map(key));
    for (const b of entry.bullets || []) {
      if (key(b) && !seen.has(key(b))) { kept.bullets.push(b); seen.add(key(b)); }
    }
  }
  return out;
}

export function sectionOrder() {
  return PRINTED_SECTIONS;
}

/** The template's first entry line: "Organisation, Location | dates". */
export function entryMeta(subheading, location, dates) {
  const place = [subheading, location].filter(Boolean).join(", ");
  return [place, dates].filter(Boolean).join(" | ");
}

/**
 * The lines every renderer prints for one entry (UK template):
 * meta ("Organisation, Location | dates"), then the bold heading (role / degree / project),
 * then description and bullets.
 */
export function renderEntry(entry, section) {
  const e = withoutRepeats(entry || {});
  let heading;
  let subheading;
  if (section === "education") {
    heading = text(e.degree || e.title);
    subheading = text(e.institution || e.organization || e.school);
  } else if (section === "certifications") {
    heading = text(e.name || e.title);
    subheading = text(e.issuer || e.organization);
  } else if (section === "publications") {
    heading = text(e.title || e.name);
    subheading = text(e.organization || e.venue || e.publisher);
  } else if (section === "achievements") {
    heading = text(e.title || e.name);
    subheading = text(e.organization || e.issuer);
  } else if (section === "projects") {
    heading = text(e.title || e.name);
    subheading = text(e.organization || e.company || e.role);
  } else {
    heading = text(e.title || e.role);
    subheading = text(e.organization || e.company);
  }
  if (!heading && subheading) [heading, subheading] = [subheading, ""];
  const dates = standardizeDates(e.dates || e.date || e.year);
  const location = text(e.location);
  return {
    heading,
    subheading,
    dates,
    location,
    meta: entryMeta(subheading, location, dates),
    description: text(e.description),
    bullets: (e.bullets || []).map(text).filter(Boolean),
  };
}

/** The five printed sections, in template order, skipping empty ones. */
export function renderSections(resume) {
  const r = resume || {};
  const sections = [];
  for (const sectionKey of sectionOrder()) {
    if (sectionKey === "summary") {
      const summary = text(r.professional_summary || r.summary);
      if (summary) sections.push({ key: sectionKey, title: SECTION_TITLES.summary, kind: "text", text: summary });
    } else if (sectionKey === "skills") {
      const skills = (r.skills || []).map(text).filter(Boolean);
      if (skills.length) sections.push({ key: sectionKey, title: SECTION_TITLES.skills, kind: "skills", skills, text: skills.join(", ") });
    } else {
      const raw = sectionKey === "experience" ? [...(r.experience || []), ...(r.internships || [])] : (r[sectionKey] || []);
      const entries = raw
        .map((e) => renderEntry(e, sectionKey))
        .filter((e) => e.heading || e.description || e.bullets.length);
      if (entries.length) sections.push({ key: sectionKey, title: SECTION_TITLES[sectionKey], kind: "entries", entries });
    }
  }
  return sections;
}

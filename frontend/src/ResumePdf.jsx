/**
 * Build the printable PDF document layout for a candidate resume.
 * Defines typography, sections, and formatting shared by in-app PDF previews.
 */
import React from "react";
import { Document, Page, Text, View, Link, StyleSheet } from "@react-pdf/renderer";
import { DEFAULT_PDF_SETTINGS } from "./pdfSettings.js";
import { renderSections } from "./resumeSections.js";

// One-column, ATS-friendly template. Only built-in PDF fonts are used, so rendering is instant,
// works offline and the text stays selectable for applicant tracking systems.
// `headingKeep`: points of following content a heading needs on its page, or it moves to the next.
const SPACING = {
  compact: { page: 30, section: 8, entry: 5, headingKeep: 28 },
  normal: { page: 40, section: 11, entry: 7, headingKeep: 34 },
  relaxed: { page: 48, section: 14, entry: 9, headingKeep: 40 },
};

const bold = (font) => (font === "Times-Roman" ? "Times-Bold" : `${font}-Bold`);

const stripScheme = (v) => String(v || "").trim().replace(/^https?:\/\/(www\.)?/i, "").replace(/\/$/, "");
export const normalizePdfText = (value) => String(value ?? "").replace(/\s+/g, " ").trim();

function contactItems(info = {}) {
  const items = [];
  const phone = normalizePdfText(info.phone);
  const email = normalizePdfText(info.email);
  const location = normalizePdfText(info.location);
  if (phone) items.push({ text: phone, href: `tel:${phone.replace(/[^\d+]/g, "")}` });
  if (email) items.push({ text: email, href: `mailto:${email}` });
  if (location) items.push({ text: location });
  const linkedin = stripScheme(info.linkedin).replace(/^linkedin\.com\/in\//i, "");
  if (linkedin) items.push({ text: `linkedin.com/in/${linkedin}`, href: `https://linkedin.com/in/${linkedin}` });
  const github = stripScheme(info.github).replace(/^github\.com\//i, "");
  if (github) items.push({ text: `github.com/${github}`, href: `https://github.com/${github}` });
  const site = stripScheme(info.portfolio || info.website);
  if (site) items.push({ text: site, href: `https://${site}` });
  return items;
}

export default function ResumePdf({ resume, settings = DEFAULT_PDF_SETTINGS }) {
  const s = { ...DEFAULT_PDF_SETTINGS, ...settings };
  const sp = SPACING[s.density] || SPACING.normal;
  const fs = s.fontSize;
  // UK template: centred bold name, role, "phone | email | location"; a full-width rule
  // before every section; entries are "Organisation | dates" then the bold role; 3-column skills.
  const styles = StyleSheet.create({
    page: { paddingHorizontal: sp.page, paddingTop: sp.page - 4, paddingBottom: sp.page - 4, fontFamily: s.font, fontSize: fs, color: "#111111", lineHeight: 1.35 },
    // Explicit line heights: the page's 1.35 line height made the large name overlap the role line.
    name: { fontFamily: bold(s.font), fontSize: fs * 2.6, lineHeight: 1.2, textAlign: "center", color: s.accent, letterSpacing: 0.5, marginBottom: fs * 0.5 },
    role: { textAlign: "center", fontSize: fs * 1.45, lineHeight: 1.25, marginTop: 0 },
    contact: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", marginTop: 7, fontSize: fs * 1.0 },
    sep: { marginHorizontal: 9 },
    link: { color: "#111111", textDecoration: "none" },
    section: { width: "100%", marginTop: sp.section, paddingTop: sp.section, borderTopWidth: 1, borderTopColor: s.accent },
    sectionTitle: { width: "100%", fontFamily: bold(s.font), fontSize: fs * 1.5, color: s.accent, textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 4 },
    entry: { width: "100%", marginBottom: sp.entry },
    meta: { width: "100%" },
    strong: { width: "100%", fontFamily: bold(s.font) },
    bullet: { width: "100%", flexDirection: "row", marginTop: 2, paddingLeft: 6 },
    dot: { width: 10 },
    bulletText: { width: "100%", flex: 1, textAlign: "left" },
    para: { width: "100%", textAlign: "left", marginTop: 1 },
    skillGrid: { width: "100%", flexDirection: "row" },
    skillCol: { flex: 1 },
  });

  const r = resume || {};
  const contacts = contactItems(r.personal_info);
  const role = r.target_role;

  const Bullets = ({ items }) =>
    (items || []).map(normalizePdfText).filter(Boolean).map((b, i) => (
      <View style={styles.bullet} key={i} wrap={false}>
        <Text style={styles.dot}>•</Text>
        <Text style={styles.bulletText}>{b}</Text>
      </View>
    ));

  // Lines come from renderSections (shared with the preview and the DOCX/LaTeX exports):
  // "Organisation, Location | dates", then the bold role/degree, then description and bullets.
  // An entry may break across pages between bullets, but its title lines stay together and
  // stay with the first line that follows them.
  const EntryView = ({ heading, meta, description, bullets }) => (
    <View style={styles.entry}>
      <View wrap={false} minPresenceAhead={sp.headingKeep}>
        {meta ? <Text style={styles.meta}>{meta}</Text> : null}
        {heading ? <Text style={styles.strong}>{heading}</Text> : null}
      </View>
      {description ? <Text style={styles.para}>{description}</Text> : null}
      <Bullets items={bullets} />
    </View>
  );

  // Three columns filled top-to-bottom, like the template.
  const SkillGrid = ({ skills }) => {
    const rows = Math.ceil(skills.length / 3);
    const cols = [0, 1, 2].map((c) => skills.slice(c * rows, (c + 1) * rows));
    return (
      <View style={styles.skillGrid}>
        {cols.map((col, c) => (
          <View style={styles.skillCol} key={c}>
            <Bullets items={col} />
          </View>
        ))}
      </View>
    );
  };

  return (
    <Document title={`${r.personal_info?.name || "Resume"}${role ? ` - ${role}` : ""}`} author={r.personal_info?.name || undefined}>
      <Page size="A4" style={styles.page}>
        {normalizePdfText(r.personal_info?.name) ? <Text style={styles.name}>{normalizePdfText(r.personal_info.name).toUpperCase()}</Text> : null}
        {normalizePdfText(role) ? <Text style={styles.role}>{normalizePdfText(role)}</Text> : null}
        {contacts.length > 0 && (
          <View style={styles.contact}>
            {contacts.map((c, i) => (
              <View key={i} style={{ flexDirection: "row" }}>
                {i > 0 && <Text style={styles.sep}>|</Text>}
                {c.href ? <Link src={c.href} style={styles.link}>{c.text}</Link> : <Text>{c.text}</Text>}
              </View>
            ))}
          </View>
        )}

        {renderSections(r).map((section) => (
          <View style={styles.section} key={section.key}>
            {/* Keep the heading on the same page as at least the first lines under it. */}
            <Text style={styles.sectionTitle} minPresenceAhead={sp.headingKeep}>{section.title}</Text>
            {section.kind === "entries"
              ? section.entries.map((e, i) => <EntryView key={i} {...e} />)
              : section.kind === "skills"
                ? <SkillGrid skills={section.skills} />
                : <Text style={styles.para}>{section.text}</Text>}
          </View>
        ))}
      </Page>
    </Document>
  );
}

/**
 * Build the printable PDF document layout for a candidate resume.
 * Defines typography, sections, and formatting shared by in-app PDF previews.
 */
import React from "react";
import { Document, Page, Text, View, Link, StyleSheet } from "@react-pdf/renderer";
import { DEFAULT_PDF_SETTINGS } from "./pdfSettings.js";

// One-column, ATS-friendly template. Only built-in PDF fonts are used, so rendering is instant,
// works offline and the text stays selectable for applicant tracking systems.
const SPACING = {
  compact: { page: 28, section: 7, entry: 4 },
  normal: { page: 36, section: 10, entry: 6 },
  relaxed: { page: 44, section: 14, entry: 9 },
};

const bold = (font) => (font === "Times-Roman" ? "Times-Bold" : `${font}-Bold`);
const italic = (font) => (font === "Times-Roman" ? "Times-Italic" : font === "Courier" ? "Courier-Oblique" : "Helvetica-Oblique");

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
  const styles = StyleSheet.create({
    page: { padding: sp.page, paddingBottom: sp.page - 4, fontFamily: s.font, fontSize: fs, color: "#111827", lineHeight: 1.3 },
    name: { fontFamily: bold(s.font), fontSize: fs * 2, textAlign: "center", color: s.accent, letterSpacing: 1 },
    role: { textAlign: "center", fontSize: fs * 1.1, color: "#475569", marginTop: 10 },
    contact: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", marginTop: 7, fontSize: fs * 0.9, color: "#334155" },
    sep: { marginHorizontal: 4, color: "#94a3b8" },
    link: { color: "#334155", textDecoration: "none" },
    section: { width: "100%", marginTop: sp.section },
    sectionTitle: { width: "100%", fontFamily: bold(s.font), fontSize: fs * 1.05, color: s.accent, textTransform: "uppercase", letterSpacing: 0.8, borderBottomWidth: 0.8, borderBottomColor: s.accent, paddingBottom: 1.5, marginBottom: 4 },
    entry: { width: "100%", marginBottom: sp.entry },
    row: { width: "100%", flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
    strong: { flex: 1, fontFamily: bold(s.font) },
    em: { width: "100%", fontFamily: italic(s.font), color: "#334155" },
    dates: { flexShrink: 0, fontSize: fs * 0.92, color: "#475569", marginLeft: 8 },
    bullet: { width: "100%", flexDirection: "row", marginTop: 1.5, paddingLeft: 6 },
    dot: { width: 9 },
    bulletText: { width: "100%", flex: 1, textAlign: "left" },
    para: { width: "100%", textAlign: "left" },
    skillsGrid: { width: "100%", flexDirection: "row", flexWrap: "wrap" },
    skillItem: { width: "33.333%", paddingRight: 8, marginBottom: 2 },
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

  const tidy = (v) => normalizePdfText(v).replace(/[,\s|;–-]+$/, "");
  const Entry = (props) => {
    // With no company/institution, the role takes the bold line instead of leaving it blank.
    let left = tidy(props.left);
    let sub = tidy(props.sub);
    if (!left && sub) [left, sub] = [sub, ""];
    return <EntryView {...props} left={left} sub={sub} />;
  };
  const EntryView = ({ left, sub, dates, bullets, description }) => {
    const entryLength = normalizePdfText(
      [left, sub, dates, description, ...(Array.isArray(bullets) ? bullets : [])].join(" ")
    ).length;
    return (
      <View style={styles.entry} wrap={entryLength > 2400}>
        <View style={styles.row} wrap={false}>
          <Text style={styles.strong}>{normalizePdfText(left)}</Text>
          {dates ? <Text style={styles.dates}>{normalizePdfText(dates)}</Text> : null}
        </View>
        {sub ? <Text style={styles.em}>{normalizePdfText(sub)}</Text> : null}
        {normalizePdfText(description) ? <Text style={styles.para}>{normalizePdfText(description)}</Text> : null}
        <Bullets items={bullets} />
      </View>
    );
  };

  const join = (...parts) => parts.map(normalizePdfText).filter(Boolean).join(" | ");

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

        {normalizePdfText(r.professional_summary) ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>About Me</Text>
            <Text style={styles.para}>{normalizePdfText(r.professional_summary)}</Text>
          </View>
        ) : null}

        {(r.education || []).length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Education</Text>
            {r.education.map((e, i) => (
              <Entry key={i} left={join(e.institution || e.organization, e.location)} sub={e.degree || e.title} dates={e.dates} bullets={e.bullets} description={e.description} />
            ))}
          </View>
        )}

        {(r.experience || []).length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Work Experience</Text>
            {r.experience.map((e, i) => (
              <Entry key={i} left={join(e.organization || e.company, e.location)} sub={e.title} dates={e.dates} bullets={e.bullets} description={e.description} />
            ))}
          </View>
        )}

        {(r.projects || []).length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Projects</Text>
            {r.projects.map((p, i) => (
              <Entry key={i} left={join(p.title, p.organization)} dates={p.dates} bullets={p.bullets} description={p.description} />
            ))}
          </View>
        )}

        {(r.skills || []).length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Skills</Text>
            <View style={styles.skillsGrid}>
              {r.skills.map((skill, i) => (
                <Text key={i} style={styles.skillItem}>• {normalizePdfText(skill)}</Text>
              ))}
            </View>
          </View>
        )}

      </Page>
    </Document>
  );
}

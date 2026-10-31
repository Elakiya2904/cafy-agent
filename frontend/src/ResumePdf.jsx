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

function contactItems(info = {}) {
  const items = [];
  if (info.phone) items.push({ text: info.phone, href: `tel:${String(info.phone).replace(/[^\d+]/g, "")}` });
  if (info.email) items.push({ text: info.email, href: `mailto:${info.email}` });
  if (info.location) items.push({ text: info.location });
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
    role: { textAlign: "center", fontSize: fs * 1.1, color: "#475569", marginTop: 2 },
    contact: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", marginTop: 4, fontSize: fs * 0.9, color: "#334155" },
    sep: { marginHorizontal: 4, color: "#94a3b8" },
    link: { color: "#334155", textDecoration: "none" },
    section: { marginTop: sp.section },
    sectionTitle: { fontFamily: bold(s.font), fontSize: fs * 1.05, color: s.accent, textTransform: "uppercase", letterSpacing: 0.8, borderBottomWidth: 0.8, borderBottomColor: s.accent, paddingBottom: 1.5, marginBottom: 4 },
    entry: { marginBottom: sp.entry },
    row: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
    strong: { fontFamily: bold(s.font) },
    em: { fontFamily: italic(s.font), color: "#334155" },
    dates: { fontSize: fs * 0.92, color: "#475569", marginLeft: 8 },
    bullet: { flexDirection: "row", marginTop: 1.5, paddingLeft: 6 },
    dot: { width: 9 },
    bulletText: { flex: 1, textAlign: "left" },
    para: { textAlign: "left" },
  });

  const r = resume || {};
  const contacts = contactItems(r.personal_info);
  const role = r.target_role;

  const Bullets = ({ items }) =>
    (items || []).filter((b) => String(b || "").trim()).map((b, i) => (
      <View style={styles.bullet} key={i} wrap={false}>
        <Text style={styles.dot}>•</Text>
        <Text style={styles.bulletText}>{b}</Text>
      </View>
    ));

  const Entry = ({ left, sub, dates, bullets, description }) => (
    <View style={styles.entry}>
      <View style={styles.row} wrap={false}>
        <Text style={styles.strong}>{left}</Text>
        {dates ? <Text style={styles.dates}>{dates}</Text> : null}
      </View>
      {sub ? <Text style={styles.em}>{sub}</Text> : null}
      {description ? <Text style={styles.para}>{description}</Text> : null}
      <Bullets items={bullets} />
    </View>
  );

  const join = (...parts) => parts.filter((p) => p && String(p).trim()).join(" | ");

  return (
    <Document title={`${r.personal_info?.name || "Resume"}${role ? ` - ${role}` : ""}`} author={r.personal_info?.name || undefined}>
      <Page size="A4" style={styles.page}>
        {r.personal_info?.name ? <Text style={styles.name}>{r.personal_info.name.toUpperCase()}</Text> : null}
        {role ? <Text style={styles.role}>{role}</Text> : null}
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

        {r.professional_summary ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Professional Summary</Text>
            <Text style={styles.para}>{r.professional_summary}</Text>
          </View>
        ) : null}

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

        {(r.education || []).length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Education</Text>
            {r.education.map((e, i) => (
              <Entry key={i} left={join(e.institution || e.organization, e.location)} sub={e.degree || e.title} dates={e.dates} bullets={e.bullets} description={e.description} />
            ))}
          </View>
        )}

        {(r.skills || []).length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Skills</Text>
            <Text style={styles.para}>{r.skills.join("  •  ")}</Text>
          </View>
        )}

        {(r.certifications || []).length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Certifications</Text>
            {r.certifications.map((c, i) => (
              <View style={[styles.row, { marginBottom: 2 }]} key={i} wrap={false}>
                <Text>
                  <Text style={styles.strong}>{c.name || c.title}</Text>
                  {c.issuer ? <Text style={styles.em}>{`  ${c.issuer}`}</Text> : null}
                </Text>
                {c.dates ? <Text style={styles.dates}>{c.dates}</Text> : null}
              </View>
            ))}
          </View>
        )}
      </Page>
    </Document>
  );
}

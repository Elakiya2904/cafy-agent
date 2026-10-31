// @vitest-environment node
import React from "react";
import { describe, expect, it } from "vitest";
import { pdf } from "@react-pdf/renderer";
import ResumePdf from "./ResumePdf.jsx";
import { countPdfPagesFromBytes } from "./pdfUtils.js";

const resume = (bulletCount) => ({
  personal_info: { name: "Ada Lovelace", email: "ada@example.com", phone: "+353 1 234 5678", location: "Dublin", linkedin: "ada", github: "ada", portfolio: "" },
  target_role: "Software Engineer",
  professional_summary: "Engineer with a record of shipping reliable systems.",
  experience: [{ title: "Engineer", organization: "Analytical Engines", dates: "2020 - Present", location: "London", bullets: Array.from({ length: bulletCount }, (_, i) => `Delivered feature ${i} that cut latency by ${i + 10}% across the platform for all customers.`) }],
  projects: [], education: [{ degree: "BSc Maths", institution: "UCD", dates: "2016 - 2020", bullets: [] }],
  certifications: [{ name: "AWS SAA", issuer: "Amazon", dates: "2022" }],
  skills: ["Python", "React", "SQL"],
});

async function pages(data, settings) {
  const buf = await pdf(<ResumePdf resume={data} settings={settings} />).toBuffer();
  const chunks = [];
  for await (const c of buf) chunks.push(c);
  const bytes = new Uint8Array(Buffer.concat(chunks));
  return { bytes, pages: countPdfPagesFromBytes(bytes) };
}

describe("ResumePdf", () => {
  it("renders a real one-page PDF for a short resume", async () => {
    const out = await pages(resume(3));
    expect(String.fromCharCode(...out.bytes.subarray(0, 5))).toBe("%PDF-");
    expect(out.pages).toBe(1);
  }, 30000);

  it("reports more than one page for an overlong resume", async () => {
    expect((await pages(resume(60))).pages).toBeGreaterThan(1);
  }, 30000);
});

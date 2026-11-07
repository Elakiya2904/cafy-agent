/**
 * Explains a job's match score (backend/requirement_matching.py): the three top-band checks,
 * every requirement the listing states (essential / desirable) with how the resume evidences
 * it and the exact resume line, and eligibility items to confirm. Visa sponsorship is shown
 * elsewhere and is not part of the score.
 */
import React from "react";

const EVIDENCE_LABEL = {
  direct: "Shown in your work",
  weak: "Listed only",
  transferable: "Related skill",
  missing: "Missing",
};

function Check({ label, passed, detail }) {
  return (
    <li className={`mb-check ${passed ? "is-pass" : "is-fail"}`}>
      <span aria-hidden="true">{passed ? "✓" : "✗"}</span> <strong>{label}</strong>
      {detail ? <span className="mb-muted"> — {detail}</span> : null}
    </li>
  );
}

export default function MatchBreakdown({ breakdown }) {
  if (!breakdown || !Array.isArray(breakdown.requirements)) return null;
  const { checks = {}, essential = {}, desirable = {}, requirements, eligibility = [] } = breakdown;
  const skills = checks.skills || {};
  const exp = checks.experience || {};
  const quals = checks.qualifications || { items: [] };

  return (
    <details className="match-breakdown">
      <summary>Why this score?</summary>

      <p className="mb-muted">
        {essential.count || 0} essential and {desirable.count || 0} desirable requirements read from this listing.
        Essential requirements count {breakdown.weights?.importance?.essential ?? 2}× a desirable one.
        {breakdown.capped ? " Score capped below 85% because a top-band check failed." : ""}
      </p>

      <ul className="mb-checks">
        <Check label={`Skills matched: ${skills.matched ?? 0} (need ${skills.required ?? 4}+)`} passed={skills.passed} />
        <Check label="Experience level" passed={exp.passed} detail={exp.detail} />
        <Check
          label="Essential qualifications"
          passed={quals.passed}
          detail={(quals.items || []).length
            ? quals.items.map((q) => `${q.name}${q.importance === "desirable" ? " (desirable)" : ""}: ${q.met ? "met" : "not met"}`).join("; ")
            : "None stated"}
        />
      </ul>

      <table className="mb-table">
        <thead>
          <tr><th>Requirement</th><th>Importance</th><th>Your resume</th><th>Evidence</th></tr>
        </thead>
        <tbody>
          {requirements.map((r) => (
            <tr key={r.name} className={`mb-${r.evidence_type}`}>
              <td>{r.name}</td>
              <td>{r.importance}</td>
              <td>{EVIDENCE_LABEL[r.evidence_type] || r.evidence_type}</td>
              <td className="mb-muted">
                {r.evidence_type === "transferable" && r.transferable_from
                  ? `${r.transferable_from.candidate_skill} (${r.transferable_from.cluster})`
                  : (r.resume_evidence || [])[0]
                    ? `“${r.resume_evidence[0].text}” — ${r.resume_evidence[0].source}`
                    : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {eligibility.length > 0 && (
        <>
          <strong>Check before applying (not scored)</strong>
          <ul className="mb-checks">
            {eligibility.map((e) => <li key={e.check}>{e.check}: <span className="mb-muted">“{e.job_text}”</span></li>)}
          </ul>
        </>
      )}
    </details>
  );
}

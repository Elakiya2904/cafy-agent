import React, { useState, useEffect } from "react";
import { Sparkles, FileText, CheckCircle2, Loader2, ChevronRight, Zap, Target, Shield } from "lucide-react";

const STEPS = [
  { id: "parse",    label: "Parsing your resume",          detail: "Extracting skills, experience & education" },
  { id: "match",    label: "Analysing job requirements",   detail: "Identifying key skills and keywords" },
  { id: "tailor",   label: "Tailoring content with AI",    detail: "Rewriting bullets to match the role" },
  { id: "validate", label: "Validating factual accuracy",  detail: "Zero-hallucination guardrail check" },
  { id: "compile",  label: "Compiling ATS-ready document", detail: "Generating PDF & DOCX files" },
];

function StepRow({ step, status }) {
  return (
    <div className="trs-step-row" data-status={status}>
      <div className="trs-step-icon">
        {status === "done"    && <CheckCircle2 size={18} className="trs-icon-done" />}
        {status === "active"  && <Loader2     size={18} className="trs-icon-spin" />}
        {status === "pending" && <div className="trs-icon-dot" />}
      </div>
      <div className="trs-step-text">
        <span className="trs-step-label">{step.label}</span>
        {status === "active" && <span className="trs-step-detail">{step.detail}</span>}
      </div>
    </div>
  );
}

export default function TailorResumeScreen({
  job,
  resume,
  tailorJobDescription,
  setTailorJobDescription,
  additionalInstructions,
  setAdditionalInstructions,
  isGenerating,
  onGenerate,
  error,
}) {
  const [activeStep, setActiveStep] = useState(-1);

  useEffect(() => {
    if (!isGenerating) { setActiveStep(-1); return; }
    setActiveStep(0);
    const timings = [0, 1400, 3200, 5800, 8200];
    const timers = timings.map((ms, i) => setTimeout(() => setActiveStep(i), ms));
    return () => timers.forEach(clearTimeout);
  }, [isGenerating]);

  const getStepStatus = (i) => {
    if (!isGenerating && activeStep === -1) return "pending";
    if (i < activeStep) return "done";
    if (i === activeStep) return "active";
    return "pending";
  };

  return (
    <div className="trs-root">
      {/* Left panel — setup form */}
      <div className="trs-left">
        <div className="trs-left-inner">
          <div className="trs-header">
            <div className="trs-header-icon"><Sparkles size={20} /></div>
            <div>
              <h2 className="trs-title">Tailor Resume</h2>
              <p className="trs-subtitle">AI-powered, zero-hallucination tailoring</p>
            </div>
          </div>

          {/* Job target card */}
          <div className="trs-target-card">
            <div className="trs-target-avatar">{(job?.company || "?").charAt(0).toUpperCase()}</div>
            <div className="trs-target-info">
              <span className="trs-target-title">{job?.title || "Unknown role"}</span>
              <span className="trs-target-company">{job?.company || "Unknown company"}</span>
            </div>
            {job?.match_score > 0 && (
              <span className="trs-match-pill">{job.match_score}% match</span>
            )}
          </div>

          {/* Base resume */}
          <div className="trs-field">
            <label className="trs-label">
              <FileText size={14} /> Base resume
            </label>
            <div className="trs-readonly-input">
              {resume?.filename || resume?.candidate_name || "Uploaded resume"}
            </div>
          </div>

          {/* Job description */}
          <div className="trs-field">
            <label className="trs-label">
              <Target size={14} /> Job description
              <span className="trs-label-hint">
                {job?.description ? "Retrieved from job — edit if needed" : "Paste the job description"}
              </span>
            </label>
            <textarea
              className="trs-textarea"
              rows={6}
              value={tailorJobDescription}
              onChange={(e) => setTailorJobDescription(e.target.value)}
              placeholder="Paste the job description here…"
              disabled={isGenerating}
            />
          </div>

          {/* Additional instructions */}
          <div className="trs-field">
            <label className="trs-label">
              <Zap size={14} /> Additional instructions
              <span className="trs-label-hint">optional</span>
            </label>
            <textarea
              className="trs-textarea trs-textarea-sm"
              rows={2}
              maxLength={500}
              placeholder="e.g. Emphasise my Python and RAG experience"
              value={additionalInstructions}
              onChange={(e) => setAdditionalInstructions(e.target.value)}
              disabled={isGenerating}
            />
          </div>

          {error && <div className="trs-error">{error}</div>}

          <button
            type="button"
            className="trs-generate-btn"
            onClick={onGenerate}
            disabled={isGenerating}
          >
            {isGenerating ? (
              <><Loader2 size={16} className="trs-icon-spin" /> Generating…</>
            ) : (
              <><Sparkles size={16} /> Generate Tailored Resume</>
            )}
          </button>

          <p className="trs-disclaimer">
            <Shield size={12} /> Resume facts are preserved during tailoring.
          </p>
        </div>
      </div>

      {/* Right panel — live progress */}
      <div className="trs-right">
        <div className="trs-right-inner">
          {!isGenerating && activeStep === -1 ? (
            <div className="trs-idle-state">
              <div className="trs-idle-icon">
                <Sparkles size={36} />
              </div>
              <h3>Your tailored resume will appear here</h3>
              <p>Fill in the details on the left and click <strong>Generate Tailored Resume</strong> to begin.</p>

              <div className="trs-feature-list">
                <div className="trs-feature-item">
                  <CheckCircle2 size={15} className="trs-icon-done" />
                  <span>ATS-optimised single-page PDF</span>
                </div>
                <div className="trs-feature-item">
                  <CheckCircle2 size={15} className="trs-icon-done" />
                  <span>Editable DOCX export</span>
                </div>
                <div className="trs-feature-item">
                  <CheckCircle2 size={15} className="trs-icon-done" />
                  <span>Zero-hallucination guardrail</span>
                </div>
                <div className="trs-feature-item">
                  <CheckCircle2 size={15} className="trs-icon-done" />
                  <span>Live editor with AI bullet improvements</span>
                </div>
                <div className="trs-feature-item">
                  <CheckCircle2 size={15} className="trs-icon-done" />
                  <span>Version history & rollback</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="trs-progress-state">
              <div className="trs-progress-header">
                <div className="trs-progress-pulse" />
                <span>Generating your tailored resume…</span>
              </div>

              <div className="trs-steps">
                {STEPS.map((step, i) => (
                  <StepRow key={step.id} step={step} status={getStepStatus(i)} />
                ))}
              </div>

              <div className="trs-progress-bar-wrap">
                <div
                  className="trs-progress-bar-fill"
                  style={{ width: `${Math.min(100, ((activeStep + 1) / STEPS.length) * 100)}%` }}
                />
              </div>
              <p className="trs-progress-note">
                This usually takes 10–20 seconds. Your resume is being tailored with AI and validated for accuracy.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ==========================================================================
// CAFY AGENT • REACT APPLICATION
// ==========================================================================

import { withToken } from "./auth.js";
import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  tailoredResumeToProfile,
  useJobMatchAnalysis,
} from "./JobMatchScore.jsx";
import ApplicationAnalysis from "./ApplicationAnalysis.jsx";
import ResumeEditor, { saveBlob } from "./ResumeEditor.jsx";
import ResumeVersionHistory from "./ResumeVersionHistory.jsx";
import DataExport from "./DataExport.jsx";
import EmailAgentDashboard from "./EmailAgentDashboard.jsx";
import MyApplications, { startApplication } from "./MyApplications.jsx";
import JobIntelligence from "./JobIntelligence.jsx";
import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  BarChart3,
  Bookmark,
  Building2,
  CalendarDays,
  ChevronRight,
  Briefcase,
  Check,
  Plus,
  CheckCircle2,
  ChevronDown,
  Circle,
  Clock,
  Download,
  ExternalLink,
  Eye,
  FileText,
  Github,
  Globe,
  GraduationCap,
  Hourglass,
  Info,
  Lightbulb,
  Loader2,
  LayoutGrid,
  Linkedin,
  List,
  Mail,
  MapPin,
  PenLine,
  Pencil,
  Phone,
  RefreshCw,
  Rocket,
  Save,
  Search,
  ScrollText,
  Sparkles,
  Star,
  Target,
  User,
  Wrench,
  X,
} from "lucide-react";

const API_BASE =
  typeof window !== "undefined" &&
    (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") &&
    window.location?.port &&
    ["5173", "5174", "3000"].includes(window.location?.port)
    ? "http://127.0.0.1:8000"
    : "";

function App() {
  // Navigation & View State
  const [activeTab, setActiveTab] = useState("home");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [platforms, setPlatforms] = useState([]);
  const [allJobs, setAllJobs] = useState([]);
  const [totalJobsCount, setTotalJobsCount] = useState(0);

  // Resume & Matching State
  const [currentResume, setCurrentResume] = useState(null);
  const [matchedJobs, setMatchedJobs] = useState([]);
  const [currentStep, setCurrentStep] = useState(1);
  const [isProcessing, setIsProcessing] = useState(false);

  // Modal State
  const [selectedJob, setSelectedJob] = useState(null);
  const [showAddCompanyModal, setShowAddCompanyModal] = useState(false);

  // Toasts & Pipeline State
  const [toasts, setToasts] = useState([]);
  const [pipelineJobIds, setPipelineJobIds] = useState(new Set());
  const fileInputRef = useRef(null);

  const showToast = useCallback((message, duration = 3500) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, duration);
  }, []);

  const togglePipeline = useCallback((jobId) => {
    setPipelineJobIds((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) {
        next.delete(jobId);
        showToast("Removed job from pipeline");
      } else {
        next.add(jobId);
        showToast("Added job to pipeline!");
      }
      return next;
    });
  }, [showToast]);

  const handleAddAllToPipeline = useCallback((jobsToAdd) => {
    if (!jobsToAdd || jobsToAdd.length === 0) return;
    setPipelineJobIds((prev) => {
      const next = new Set(prev);
      jobsToAdd.forEach((j) => next.add(j.id));
      return next;
    });
    showToast(`Added all ${jobsToAdd.length} jobs to your pipeline!`);
  }, [showToast]);

  // Fetch initial data
  const loadPlatformsAndJobs = useCallback(async () => {
    try {
      const [platRes, jobsRes] = await Promise.all([
        fetch(`${API_BASE}/api/platforms`),
        fetch(`${API_BASE}/api/jobs?limit=10000`)
      ]);
      const platData = await platRes.json();
      const jobsData = await jobsRes.json();

      setPlatforms(platData.platforms || []);
      setTotalJobsCount(platData.total_jobs || jobsData.count || 0);
      setAllJobs(jobsData.jobs || []);
    } catch (e) {
      console.error("Failed to load initial data", e);
    }
  }, []);

  useEffect(() => {
    loadPlatformsAndJobs();
    fetch(`${API_BASE}/api/resume/current`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.resume) {
          setCurrentResume(data.resume);
          if (data.matched_jobs) setMatchedJobs(data.matched_jobs);
        }
      })
      .catch(() => {});
  }, [loadPlatformsAndJobs]);

  // Handle File Upload
  const handleFileUpload = async (file) => {
    if (!file) return;
    setIsProcessing(true);
    setCurrentStep(2);
    showToast(`Analyzing ${file.name}... Extracting skills...`);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_BASE}/api/resume/upload`, {
        method: "POST",
        body: formData
      });

      if (!res.ok) {
        throw new Error(`Upload failed (${res.status})`);
      }

      const data = await res.json();
      setCurrentResume(data.resume);
      setMatchedJobs(data.matched_jobs || []);
      setCurrentStep(3);
      showToast(`Analyzed résumé. Found ${data.matched_jobs?.length || 0} matching roles.`);

      // Auto-redirect to Find Jobs tab
      setTimeout(() => {
        setActiveTab("find-jobs");
      }, 700);
    } catch (err) {
      console.error(err);
      showToast(`Error processing résumé: ${err.message}`);
      setCurrentStep(1);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className={`app-layout ${assistantOpen ? "assistant-open" : ""}`}>
      {/* SIDEBAR COMPONENT */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={(tab) => {
          setActiveTab(tab);
          setSelectedJob(null);
        }}
        totalJobsCount={totalJobsCount}
        hasResume={!!currentResume}
        highMatchCount={matchedJobs.length}
        pipelineCount={pipelineJobIds.size}
        platformCount={platforms.length}
      />

      {/* MAIN CONTENT AREA */}
      <main className="main-content">
        <header className="main-top-bar">
          <div className="top-bar-left" />
          <div className="top-bar-right">
            {currentResume && (
              <div className="user-profile-badge">
                <span className="user-avatar-circle">
                  {(currentResume.candidate_name || currentResume.filename || "?").charAt(0).toUpperCase()}
                </span>
                <span className="user-name">
                  {currentResume.candidate_name || currentResume.filename || "Your profile"}
                </span>
              </div>
            )}
          </div>
        </header>
        {activeTab === "home" && (
          <div className="content-container">
            {/* HERO SECTION */}
            <HeroSection />

            {/* UPLOAD CARD CONTAINER */}
            <div className="upload-container-card">
              <UploadDropzone
                onFileSelected={handleFileUpload}
                isProcessing={isProcessing}
                fileInputRef={fileInputRef}
              />

              <Stepper currentStep={currentStep} />
            </div>

            {/* WHAT HAPPENS NEXT SECTION */}
            <NextStepsSection
              resume={currentResume}
              matchedCount={matchedJobs.length}
              onViewJobs={() => setActiveTab("find-jobs")}
              onChangeResume={() => fileInputRef.current && fileInputRef.current.click()}
              onViewProfile={() => setActiveTab("resume")}
            />
          </div>
        )}

        {/* TAB: FIND JOBS (Browse all stored jobs & skill-matched jobs) */}
        {activeTab === "find-jobs" && (
          <DirectoryView
            jobs={allJobs}
            matchedJobs={matchedJobs}
            resume={currentResume}
            platforms={platforms}
            pipelineJobIds={pipelineJobIds}
            onTogglePipeline={togglePipeline}
            onAddAllToPipeline={handleAddAllToPipeline}
            onSelectJob={setSelectedJob}
            onRefresh={loadPlatformsAndJobs}
          />
        )}

        {/* TAB: COMPANIES (ATS Connectors) */}
        {activeTab === "companies" && (
          <CompaniesView
            platforms={platforms}
            onOpenAdd={() => setShowAddCompanyModal(true)}
            onScrapePlatform={async (pId) => {
              try {
                const res = await fetch(`${API_BASE}/api/scrape?platform=${encodeURIComponent(pId)}`, { method: "POST" });
                if (!res.ok) throw new Error(`Scrape request failed (${res.status})`);
                showToast(`Scrape of ${pId} started. Refresh the job list once it finishes.`);
              } catch (err) {
                showToast(err.message || "Could not start the scrape.");
              }
            }}
          />
        )}

        {/* TAB: RESUME DETAILS */}
        {activeTab === "resume" && (
          <div className="content-container">
            <ResumeVersionHistory PreviewComponent={ResumeDocumentPreview} />
          </div>
        )}

        {/* TAB: INSIGHTS */}
        {activeTab === "insights" && <InsightsView platforms={platforms} />}

        {/* TAB: MY APPLICATIONS */}
        {activeTab === "my-applications" && <MyApplications />}
        {activeTab === "my-applications" && (
          <ApplicationTrackingView
            pipelineJobIds={pipelineJobIds}
            allJobs={allJobs}
            onSelectJob={setSelectedJob}
          />
        )}

        {/* TAB: JOB ALERTS */}
        {activeTab === "job-alerts" && (
          <div className="content-container">
            <h1 className="page-title">Job Alerts</h1>
            <p className="page-subtitle">Get automatic notifications when new roles matching your skills are scraped.</p>
            <div className="empty-state-card">
              <p>Job alerts are not available yet.</p>
            </div>
          </div>
        )}

        {/* TAB: EMAIL AGENT (Pipeline 3) */}
        {activeTab === "follow-ups" && (
          <EmailAgentDashboard pipelineJobs={allJobs.filter((j) => pipelineJobIds.has(j.id))} />
        )}

        {/* TAB: FILES */}
        {activeTab === "files" && (
          <div className="content-container">
            <h1 className="page-title">Files & Documents</h1>
            <p className="page-subtitle">Uploaded résumés, cover letters, and parsed skill profiles.</p>
            <div className="empty-state-card">
              {currentResume ? (
                <div>
                  <h4 style={{ marginBottom: 8, color: "var(--slate-900)" }}>Current File: {currentResume.filename}</h4>
                  <p>
                    {[
                      `Extracted ${currentResume.total_skills ?? (currentResume.skills || []).length} skills`,
                      currentResume.seniority_level && currentResume.seniority_level !== "Unknown" ? currentResume.seniority_level : null,
                      currentResume.candidate_name || null,
                    ].filter(Boolean).join(" • ")}
                  </p>
                </div>
              ) : (
                <p>No files uploaded yet. Upload a résumé on the Home tab to see your document breakdown here.</p>
              )}
            </div>
            <DataExport pipelineJobIds={pipelineJobIds} allJobs={allJobs} />
          </div>
        )}

        {/* TAB: SETTINGS */}
        {activeTab === "settings" && <SettingsView />}
      </main>

      <CareerAnalystPanel
        isOpen={assistantOpen}
        onOpen={() => setAssistantOpen(true)}
        onClose={() => setAssistantOpen(false)}
        resume={currentResume}
        matchedJobs={matchedJobs}
        pipelineJobIds={pipelineJobIds}
        focusJob={selectedJob}
      />

      {/* JOB DETAIL MODAL */}
      {selectedJob && (
        <JobDetailModal
          job={selectedJob}
          resume={currentResume}
          onUpdateResume={setCurrentResume}
          inPipeline={pipelineJobIds.has(selectedJob.id)}
          onTogglePipeline={() => togglePipeline(selectedJob.id)}
          onClose={() => setSelectedJob(null)}
          fullPage
          resumeOnly
        />
      )}

      {/* ADD COMPANY MODAL */}
      {showAddCompanyModal && (
        <AddCompanyModal
          onClose={() => setShowAddCompanyModal(false)}
          onSuccess={() => {
            setShowAddCompanyModal(false);
            loadPlatformsAndJobs();
            showToast("Added company and started indexing!");
          }}
        />
      )}

      {/* TOAST ALERTS */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className="toast">
            {t.message}
          </div>
        ))}
      </div>
    </div>
  );
}

function BirdLogo({ size = 26 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <path d="M4 14.5L28 4L18 28L13 19L4 14.5Z" fill="#0066FF" stroke="#0052CC" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M28 4L13 19" stroke="#93C5FD" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function CompanyBrandLogo({ company }) {
  const c = (company || "").toLowerCase();
  if (c.includes("google")) {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
        <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z" />
        <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24z" />
        <path fill="#FBBC05" d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.98 0 12s.45 3.82 1.25 5.42l4.03-3.15z" />
        <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.93 6.72-4.93z" />
      </svg>
    );
  }
  if (c.includes("microsoft")) {
    return (
      <svg width="20" height="20" viewBox="0 0 23 23" style={{ flexShrink: 0 }}>
        <path fill="#f35325" d="M1 1h10v10H1z" />
        <path fill="#81bc06" d="M12 1h10v10H12z" />
        <path fill="#05a6f0" d="M1 12h10v10H1z" />
        <path fill="#ffba08" d="M12 12h10v10H12z" />
      </svg>
    );
  }
  if (c.includes("amazon")) {
    return (
      <div style={{ width: "24px", height: "24px", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <text x="3" y="16" fontFamily="Inter, system-ui, sans-serif" fontWeight="900" fontSize="17" fill="#0F172A">a</text>
          <path d="M4 18.5c4 2.2 10.5 2.2 14.5 0" stroke="#FF9900" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      </div>
    );
  }
  if (c.includes("databricks")) {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }} aria-hidden="true">
        <path d="M12 2L2 7l10 5 10-5-10-5z" fill="#FF3621" />
        <path d="M2 12l10 5 10-5-10-5-10 5z" fill="#FF3621" opacity="0.85" />
        <path d="M2 17l10 5 10-5-10-5-10 5z" fill="#FF3621" opacity="0.7" />
      </svg>
    );
  }
  if (c.includes("stripe")) {
    return (
      <div style={{ width: "22px", height: "22px", borderRadius: "5px", background: "#635BFF", display: "grid", placeItems: "center", flexShrink: 0 }} aria-hidden="true">
        <svg width="12" height="14" viewBox="0 0 12 14" fill="#FFFFFF">
          <path d="M4.8 5.4c0-.6.5-.9 1.4-.9 1.2 0 2.8.4 4 .9V1.7C8.9 1.3 7.5 1.1 6.2 1.1 2.8 1.1.9 2.9.9 5.6c0 4.2 5.8 3.5 5.8 5.3 0 .7-.6 1-1.6 1-1.5 0-3.4-.6-4.9-1.4v3.8c1.6.7 3.3 1 4.9 1 3.6 0 5.8-1.7 5.8-4.6-.1-4.4-6.1-3.7-6.1-5.3z" />
        </svg>
      </div>
    );
  }
  if (c.includes("linear")) {
    return (
      <div style={{ width: "22px", height: "22px", borderRadius: "5px", background: "#5E6AD2", display: "grid", placeItems: "center", flexShrink: 0 }} aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.5">
          <line x1="4" y1="20" x2="20" y2="4" strokeLinecap="round" />
        </svg>
      </div>
    );
  }
  if (c.includes("figma")) {
    return (
      <svg width="16" height="22" viewBox="0 0 38 57" style={{ flexShrink: 0 }} aria-hidden="true">
        <path fill="#1abcfe" d="M19 28.5a9.5 9.5 0 1 1 19 0 9.5 9.5 0 0 1-19 0z" />
        <path fill="#0acf83" d="M0 47.5A9.5 9.5 0 0 1 9.5 38H19v9.5a9.5 9.5 0 1 1-19 0z" />
        <path fill="#ff7262" d="M19 0v19h9.5a9.5 9.5 0 1 0 0-19H19z" />
        <path fill="#f24e1e" d="M0 9.5A9.5 9.5 0 0 0 9.5 19H19V0H9.5A9.5 9.5 0 0 0 0 9.5z" />
        <path fill="#a259ff" d="M0 28.5A9.5 9.5 0 0 0 9.5 38H19V19H9.5A9.5 9.5 0 0 0 0 28.5z" />
      </svg>
    );
  }
  const initial = (company || "C").charAt(0).toUpperCase();
  return (
    <div
      aria-hidden="true"
      style={{
        width: "22px",
        height: "22px",
        borderRadius: "6px",
        background: "linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%)",
        color: "#2563EB",
        fontWeight: "800",
        fontSize: "0.75rem",
        display: "grid",
        placeItems: "center",
        flexShrink: 0,
        boxShadow: "inset 0 0 0 1px rgba(37,99,235,0.15)",
      }}
    >
      {initial}
    </div>
  );
}

const QUICK_ACTIONS = [
  {
    id: "opportunities",
    label: "Analyse my opportunities",
    prompt: "Analyse my opportunities",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="#0066FF" stroke="#0066FF" strokeWidth="1">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
    )
  },
  {
    id: "explain",
    label: "Explain a job match",
    prompt: "Explain why I match this job",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0066FF" strokeWidth="2.2">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><circle cx="12" cy="11" r="3" />
      </svg>
    )
  },
  {
    id: "search",
    label: "Find new jobs",
    prompt: "Find new jobs",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0066FF" strokeWidth="2.4" strokeLinecap="round">
        <circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.5" y2="16.5" />
      </svg>
    )
  },
  {
    id: "skills",
    label: "Skill gap analysis",
    prompt: "Skill gap analysis",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="#0066FF">
        <rect x="3" y="12" width="4" height="9" rx="1" /><rect x="10" y="7" width="4" height="14" rx="1" /><rect x="17" y="3" width="4" height="18" rx="1" />
      </svg>
    )
  },
  {
    id: "strategy",
    label: "Application strategy",
    prompt: "Which jobs should I prioritise this week?",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="#0066FF">
        <rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" fill="none" stroke="#0066FF" strokeWidth="2" />
      </svg>
    )
  },
  {
    id: "progress",
    label: "Show my progress",
    prompt: "Show my progress",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0066FF" strokeWidth="2.2" strokeLinecap="round">
        <circle cx="12" cy="12" r="9" /><polyline points="12 7 12 12 15 14" />
      </svg>
    )
  },
];

function sanitizeDisplayText(value) {
  if (value == null) return "";
  const source = String(value);
  const withBreaks = source.replace(
    /<\s*\/?(?:br|p|div|li|h[1-6]|tr|section|article|ul|ol)[^>]*>/gi,
    (tag) => /^<\s*\/|<\s*br/i.test(tag) ? "\n" : ""
  );
  const decoded = typeof DOMParser !== "undefined"
    ? new DOMParser().parseFromString(withBreaks, "text/html").body.textContent || ""
    : withBreaks;
  let text = decoded
    .replace(/\u00a0/g, " ")
    .replace(/\u200b/g, "")
    .replace(/\|{2,}/g, " ")
    .replace(/\r/g, "")
    .replace(/(^|\n)\s*#{1,6}\s*/g, "$1")
    .replace(/(^|\n)\s*>\s*/g, "$1")
    .replace(/[<>]/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/\s{2,}/g, " ")
    .trim();

  return text;
}

function renderCareerAnswer(content) {
  const lines = sanitizeDisplayText(content)
    .split(/\n/);

  const blocks = [];
  let index = 0;
  let key = 0;

  const renderInline = (text, prefix) => {
    const safeText = String(text || "").replace(/\s+/g, " ").trim();
    if (!safeText) return null;

    const parts = safeText.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
    return parts.map((part, partIndex) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={`${prefix}-${partIndex}`}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith("`") && part.endsWith("`")) {
        return <code key={`${prefix}-${partIndex}`}>{part.slice(1, -1)}</code>;
      }
      return part;
    });
  };

  const parseTableRow = (line) => line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
  const isTableRow = (line) => {
    if (!line || !line.includes("|")) return false;
    const cells = parseTableRow(line);
    return cells.length >= 2 && cells.some(Boolean);
  };
  const isTableDivider = (line) => {
    if (!isTableRow(line)) return false;
    return parseTableRow(line).every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, "")));
  };
  const isListItem = (line) => /^[\s\u00a0]*(?:[-*+]|\d+[.)])\s+/.test(line);
  const isHeading = (line) => /^[\s\u00a0]*#{1,6}\s+.+$/.test(line);

  while (index < lines.length) {
    if (!lines[index].trim()) {
      index += 1;
      continue;
    }

    if (isTableRow(lines[index]) && isTableDivider(lines[index + 1] || "")) {
      const headers = parseTableRow(lines[index]);
      index += 2;
      const rows = [];
      while (index < lines.length && isTableRow(lines[index])) {
        rows.push(parseTableRow(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="career-chat-table-wrap" key={`table-${key++}`}>
          <table className="career-chat-table">
            <thead>
              <tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{renderInline(cell, `th-${key}-${cellIndex}`)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {headers.map((_, cellIndex) => (
                    <td key={cellIndex}>{renderInline(row[cellIndex] || "", `td-${key}-${rowIndex}-${cellIndex}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    const heading = lines[index].match(/^[\s\u00a0]*(#{1,3})\s+(.+)$/);
    if (heading) {
      const HeadingTag = `h${Math.min(heading[1].length, 3)}`;
      blocks.push(
        <HeadingTag key={`heading-${key++}`}>
          {renderInline(heading[2], `heading-${key}`)}
        </HeadingTag>
      );
      index += 1;
      continue;
    }

    if (isListItem(lines[index])) {
      const ordered = /^[\s\u00a0]*\d+[.)]\s+/.test(lines[index]);
      const ListTag = ordered ? "ol" : "ul";
      const items = [];
      while (index < lines.length && isListItem(lines[index])) {
        items.push(lines[index].replace(/^[\s\u00a0]*(?:[-*+]|\d+[.)])\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ListTag key={`list-${key++}`}>
          {items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item, `list-${key}-${itemIndex}`)}</li>)}
        </ListTag>
      );
      continue;
    }

    const paragraph = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !isListItem(lines[index]) &&
      !isHeading(lines[index]) &&
      !(isTableRow(lines[index]) && isTableDivider(lines[index + 1] || ""))
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    const text = paragraph.join(" ").trim();
    if (text) {
      blocks.push(<p key={`paragraph-${key++}`}>{renderInline(text, `paragraph-${key}`)}</p>);
    } else {
      index += 1;
    }
  }

  if (blocks.length === 0 && content) {
    return <p>{renderInline(String(content), "fallback")}</p>;
  }

  return blocks;
}

function getCareerChatErrorMessage(detail) {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (!item || typeof item !== "object") return "";
        const message = typeof item.msg === "string" ? item.msg : "";
        const location = Array.isArray(item.loc)
          ? item.loc.filter((part) => typeof part === "string" || typeof part === "number").join(".")
          : "";
        return message ? (location ? `${location}: ${message}` : message) : "";
      })
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  return "The analyst could not answer right now. Please try again.";
}

function CareerAnalystPanel({ isOpen, onOpen, onClose, resume, matchedJobs, pipelineJobIds, focusJob }) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const createInitialMessages = () => [
    {
      role: "assistant",
      content: "Hi!\nI can help you explore current job listings and application strategies. Upload your resume to get evidence-based match scores, skill comparisons, and personalized recommendations.\n\nWhat would you like to do?",
      showQuickActions: true,
      job_cards: [],
    },
  ];

  const [messages, setMessages] = useState(createInitialMessages);
  const threadRef = useRef(null);

  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) return undefined;

    const scrollToLatestMessage = () => {
      thread.scrollTo({
        top: thread.scrollHeight,
        behavior: "smooth",
      });
    };

    const frame = requestAnimationFrame(scrollToLatestMessage);
    return () => cancelAnimationFrame(frame);
  }, [messages, busy]);

  const resetChat = () => {
    setMessages(createInitialMessages());
    setDraft("");
  };

  const sendMessage = async (queryText = draft) => {
    const query = queryText.trim();
    if (!query || busy) return;

    const history = messages
      .filter((message) =>
        (message.role === "user" || message.role === "assistant") &&
        !message.isError &&
        typeof message.content === "string"
      )
      .slice(-6)
      .map(({ role, content }) => ({ role, content: content.slice(0, 1000) }));

    setMessages((prev) => [...prev, { role: "user", content: query, job_cards: [] }]);
    setDraft("");
    setBusy(true);

    try {
      const response = await fetch(`${API_BASE}/api/career-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          mode: "opportunities",
          history,
          resume_data: resume,
          pipeline_job_ids: [...pipelineJobIds],
          focus_job_id: focusJob?.id || null,
        }),
      });
      const responseText = await response.text();
      let data;
      try {
        data = responseText ? JSON.parse(responseText) : {};
      } catch {
        throw new Error(
          response.ok
            ? "Career Analyst returned an unreadable response. Please try again."
            : `Career Analyst service error (${response.status}). Please try again shortly.`
        );
      }
      if (!response.ok) throw new Error(getCareerChatErrorMessage(data.detail));
      if (typeof data.answer !== "string" || !data.answer.trim()) {
        throw new Error("Career Analyst returned an empty response. Please try again.");
      }

      const cards = data.job_cards || [];
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          job_cards: cards,
          evidence: data.evidence || null,
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: error instanceof Error
            ? error.message
            : "The analyst could not answer right now. Please try again.",
          job_cards: [],
          isError: true,
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {!isOpen && (
        <button className="career-chat-launcher" onClick={onOpen} aria-label="Open Career Analyst" title="Open Cafy Agent">
          <BirdLogo size={28} />
        </button>
      )}

      {isOpen && (
        <aside className={`career-chat-dock ${isExpanded ? "expanded" : ""}`} aria-label="Cafy Agent">
          {/* Header */}
          <header className="career-chat-header">
            <div className="career-chat-brand-mark" aria-hidden="true">
              <BirdLogo size={28} />
            </div>
            <div className="career-chat-brand-copy">
              <strong>Cafy Agent</strong>
              <span>Your career assistant</span>
            </div>
            <div className="career-chat-header-actions">
              <button
                className="career-chat-header-btn"
                onClick={() => setIsExpanded(!isExpanded)}
                aria-label={isExpanded ? "Collapse panel" : "Expand panel"}
                title={isExpanded ? "Collapse" : "Expand"}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="15 3 21 3 21 9" />
                  <polyline points="9 21 3 21 3 15" />
                  <line x1="21" y1="3" x2="14" y2="10" />
                  <line x1="3" y1="21" x2="10" y2="14" />
                </svg>
              </button>
              <button
                className="career-chat-header-btn"
                onClick={resetChat}
                aria-label="New chat / History"
                title="Reset conversation"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                  <path d="M3 3v5h5" />
                  <path d="M12 7v5l3 3" />
                </svg>
              </button>
              <button
                className="career-chat-header-btn"
                onClick={onClose}
                aria-label="Close Cafy Agent"
                title="Close"
              >
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </header>

          {/* Conversation Thread */}
          <div className="career-chat-thread" ref={threadRef} aria-live="polite">
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`career-chat-row ${message.role} ${message.isError ? "error" : ""}`}>
                {message.role === "assistant" && (
                  <div className="career-chat-avatar-slot" aria-hidden="true">
                    <BirdLogo size={24} />
                  </div>
                )}

                <div className="career-chat-bubble-container">
                  <div className={`career-chat-bubble ${message.role}`}>
                    {message.role === "assistant"
                      ? <div className="career-chat-answer">{renderCareerAnswer(message.content)}</div>
                      : <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{message.content}</p>}
                    {message.evidence && !message.isError && (
                      <div className="career-chat-evidence">
                        <span>{message.evidence.analyzed_job_count} listings analyzed</span>
                        {message.evidence.profile_loaded && (
                          <span>{message.evidence.profile_match_count} profile matches</span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* 2x3 Quick Action Grid on greeting */}
                  {message.showQuickActions && messages.length === 1 && (
                    <div className="career-chat-actions-grid">
                      {QUICK_ACTIONS.map((action) => (
                        <button
                          key={action.id}
                          className="career-chat-action-card"
                          onClick={() => sendMessage(action.prompt)}
                          disabled={busy}
                        >
                          <span className="career-chat-action-icon">{action.icon}</span>
                          <span className="career-chat-action-label">{action.label}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Job Cards if assistant returns recommendations */}
                  {message.job_cards && message.job_cards.length > 0 && (
                    <div className="career-chat-cards-column">
                      {message.job_cards.map((job) => {
                        const bullets = job.bullets || [];

                        return (
                          <article className="career-chat-exact-card" key={job.id}>
                            <div className="career-chat-card-top">
                              <div className="career-chat-card-identity">
                                <CompanyBrandLogo company={job.company} />
                                <div className="career-chat-card-titles">
                                  <h4 className="career-chat-card-title">{job.title}</h4>
                                  <span className="career-chat-card-company">{job.company || "Unknown employer"}</span>
                                </div>
                              </div>
                              {Number.isFinite(job.match_score) && (
                                <span className="career-chat-card-match">
                                  {job.match_score}% match
                                </span>
                              )}
                            </div>

                            {bullets.length > 0 && (
                              <ul className="career-chat-card-bullets">
                                {bullets.map((b, i) => (
                                  <li key={i}>
                                    <span className="bullet-dot">•</span>
                                    <span>{b.replace(/^[•\s]+/, "")}</span>
                                  </li>
                                ))}
                              </ul>
                            )}

                            {job.url && /^https?:\/\//i.test(job.url) && (
                              <div className="career-chat-card-bottom">
                                <a
                                  href={job.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="career-chat-card-btn"
                                >
                                  View job <ArrowRight size={14} aria-hidden="true" />
                                </a>
                              </div>
                            )}
                          </article>
                        );
                      })}
                    </div>
                  )}

                </div>
              </div>
            ))}

            {busy && (
              <div className="career-chat-row assistant">
                <div className="career-chat-avatar-slot">
                  <BirdLogo size={24} />
                </div>
                <div className="career-chat-thinking-bubble">
                  <span /><span /><span />
                </div>
              </div>
            )}
          </div>

          {/* Footer Pill Composer */}
          <footer className="career-chat-footer">
            <form
              className="career-chat-pill-bar"
              onSubmit={(e) => {
                e.preventDefault();
                sendMessage();
              }}
            >
              <div className="career-chat-sparkle-icon" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" strokeWidth="1.8">
                  <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3Z" />
                </svg>
              </div>
              <input
                type="text"
                className="career-chat-pill-input"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
                placeholder="Ask about jobs, your profile, skills, or applications..."
                disabled={busy}
                aria-label="Ask Cafy Agent"
              />
              <button
                type="submit"
                className="career-chat-pill-send"
                disabled={busy || !draft.trim()}
                aria-label="Send message"
                title="Send"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="#FFFFFF">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                </svg>
              </button>
            </form>
          </footer>
        </aside>
      )}
    </>
  );
}

// ==========================================================================
// SUBCOMPONENTS
// ==========================================================================

function Sidebar({ activeTab, setActiveTab, totalJobsCount, hasResume, highMatchCount = 0, pipelineCount = 0, platformCount = 0 }) {
  const navItems = [
    {
      section: "Overview", id: "home", label: "Home", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
          <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
          <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
          <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
        </svg>
      )
    },
    {
      section: "1. Discover", id: "find-jobs", label: "Find Jobs", badge: hasResume ? highMatchCount : totalJobsCount, icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
      )
    },
    {
      id: "companies", label: "Companies", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="4" y="2" width="16" height="20" rx="2" ry="2"></rect>
          <line x1="9" y1="22" x2="9" y2="22.01"></line>
          <line x1="15" y1="22" x2="15" y2="22.01"></line>
          <line x1="9" y1="18" x2="9" y2="18.01"></line>
          <line x1="15" y1="18" x2="15" y2="18.01"></line>
          <line x1="9" y1="14" x2="9" y2="14.01"></line>
          <line x1="15" y1="14" x2="15" y2="14.01"></line>
        </svg>
      )
    },
    {
      id: "job-alerts", label: "Job Alerts", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
        </svg>
      )
    },
    {
      section: "2. Apply", label: "Application", id: "my-applications", badge: pipelineCount > 0 ? pipelineCount : undefined, icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M9 11l3 3L22 4"></path>
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
        </svg>
      )
    },
    {
      id: "resume", label: "Resume", hasDot: hasResume, icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
        </svg>
      )
    },
    {
      id: "files", label: "Files", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
        </svg>
      )
    },
    {
      section: "3 · Follow up", id: "follow-ups", label: "Email Agent", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
      )
    },
    {
      section: "Account", id: "insights", label: "Analytics", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="18" y1="20" x2="18" y2="10"></line>
          <line x1="12" y1="20" x2="12" y2="4"></line>
          <line x1="6" y1="20" x2="6" y2="14"></line>
        </svg>
      )
    },
    {
      id: "settings", label: "Settings", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
        </svg>
      )
    }
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-logo-icon">
          <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
            <path d="M4 14.5L28 4L18 28L13 19L4 14.5Z" fill="#2563EB" stroke="#1D4ED8" strokeWidth="2" strokeLinejoin="round" />
            <path d="M28 4L13 19" stroke="#93C5FD" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </div>
        <span className="brand-title">Cafy Agent</span>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <React.Fragment key={item.id}>
            {item.section && <div className="nav-section-label">{item.section}</div>}
            <a
              href={`#${item.id}`}
              className={`nav-item ${activeTab === item.id ? "active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                setActiveTab(item.id);
              }}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
              {item.badge !== undefined && <span className="badge-counter">{item.badge}</span>}
              {item.tag && <span className="badge-pill">{item.tag}</span>}
              {item.hasDot && <span className="status-dot active"></span>}
            </a>
          </React.Fragment>
        ))}
      </nav>

    </aside>
  );
}

function HeroSection() {
  return (
    <div className="hero-section">
      <div className="hero-text-col">
        <span className="hero-tag">WELCOME TO CAFY AGENT</span>
        <h1 className="hero-title">
          Find jobs that fit <span className="text-blue-accent">your skills</span>
        </h1>
        <p className="hero-subtitle">
          Upload your résumé. We'll extract your skills and experience, then match you with relevant opportunities.
        </p>
      </div>

      <div className="hero-illustration-col">
        <div className="floating-scene">
          <svg className="scene-trails" viewBox="0 0 320 200" fill="none">
            <path d="M 40 100 C 90 20, 160 30, 240 60" stroke="#CBD5E1" strokeWidth="1.8" strokeDasharray="4 4" />
            <path d="M 120 180 C 180 180, 220 140, 260 90" stroke="#CBD5E1" strokeWidth="1.8" strokeDasharray="4 4" />
          </svg>

          <div className="floating-chip chip-search">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563EB" strokeWidth="2.2">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
          </div>

          <div className="floating-chip chip-briefcase">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563EB" strokeWidth="2.2">
              <rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect>
              <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path>
            </svg>
          </div>

          <div className="floating-chip chip-stats">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563EB" strokeWidth="2.2">
              <line x1="18" y1="20" x2="18" y2="10"></line>
              <line x1="12" y1="20" x2="12" y2="4"></line>
              <line x1="6" y1="20" x2="6" y2="14"></line>
            </svg>
          </div>

          <div className="floating-resume-card">
            <div className="resume-sheet">
              <div className="sheet-lines">
                <div className="sheet-line line-1"></div>
                <div className="sheet-line line-2"></div>
                <div className="sheet-line line-3"></div>
                <div className="sheet-line line-4"></div>
              </div>
            </div>
            <div className="sheet-upload-badge">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3">
                <line x1="12" y1="19" x2="12" y2="5"></line>
                <polyline points="5 12 12 5 19 12"></polyline>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function UploadDropzone({ onFileSelected, isProcessing, fileInputRef }) {
  const [isDragActive, setIsDragActive] = useState(false);

  return (
    <div
      className={`dashed-dropzone ${isDragActive ? "drag-active" : ""}`}
      onDragEnter={(e) => { e.preventDefault(); setIsDragActive(true); }}
      onDragOver={(e) => { e.preventDefault(); setIsDragActive(true); }}
      onDragLeave={(e) => { e.preventDefault(); setIsDragActive(false); }}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
          onFileSelected(e.dataTransfer.files[0]);
        }
      }}
      onClick={() => fileInputRef.current && fileInputRef.current.click()}
    >
      <input
        type="file"
        ref={fileInputRef}
        accept=".pdf,.docx,.doc,.txt"
        className="hidden-input"
        onChange={(e) => {
          if (e.target.files && e.target.files[0]) {
            onFileSelected(e.target.files[0]);
          }
        }}
      />

      <div className="dropzone-icon-wrapper">
        <div className="dropzone-doc-icon">
          <svg width="42" height="52" viewBox="0 0 42 52" fill="none">
            <path d="M4 8C4 4.68629 6.68629 2 10 2H26L38 14V44C38 47.3137 35.3137 50 32 50H10C6.68629 50 4 47.3137 4 44V8Z" fill="#F1F5F9" stroke="#94A3B8" strokeWidth="2.5" strokeLinejoin="round" />
            <path d="M26 2V14H38" fill="#E2E8F0" stroke="#94A3B8" strokeWidth="2.5" strokeLinejoin="round" />
            <line x1="12" y1="24" x2="26" y2="24" stroke="#CBD5E1" strokeWidth="2.5" strokeLinecap="round" />
            <line x1="12" y1="32" x2="30" y2="32" stroke="#CBD5E1" strokeWidth="2.5" strokeLinecap="round" />
            <line x1="12" y1="40" x2="22" y2="40" stroke="#CBD5E1" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
          <div className="dropzone-badge-circle">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3">
              <line x1="12" y1="19" x2="12" y2="5"></line>
              <polyline points="5 12 12 5 19 12"></polyline>
            </svg>
          </div>
        </div>
      </div>

      <h3 className="dropzone-title">Upload your résumé</h3>
      <p className="dropzone-specs">PDF or DOCX • Max 10 MB</p>

      <div className="dropzone-actions">
        <button
          type="button"
          className="btn-choose-resume"
          disabled={isProcessing}
          onClick={(e) => {
            e.stopPropagation();
            fileInputRef.current && fileInputRef.current.click();
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="19" x2="12" y2="5"></line>
            <polyline points="5 12 12 5 19 12"></polyline>
          </svg>
          <span>{isProcessing ? "Processing Résumé..." : "Choose résumé"}</span>
        </button>
      </div>

      <p className="dropzone-drag-hint">or drag and drop your file here</p>
    </div>
  );
}

function Stepper({ currentStep }) {
  return (
    <div className="stepper-wrapper">
      <div className={`step-item ${currentStep === 1 ? "active" : currentStep > 1 ? "completed" : ""}`}>
        <div className="step-node-circle">{currentStep > 1 ? <Check size={16} aria-hidden="true" /> : "1"}</div>
        <div className="step-text-group">
          <span className="step-heading">Upload résumé</span>
          <span className="step-subheading">Add your latest résumé</span>
        </div>
      </div>

      <div className="step-connector connector-1-2" style={{ background: currentStep >= 2 ? "#10B981" : "#2563EB" }}></div>

      <div className={`step-item ${currentStep === 2 ? "active" : currentStep > 2 ? "completed" : ""}`}>
        <div className="step-node-circle">{currentStep > 2 ? <Check size={16} aria-hidden="true" /> : "2"}</div>
        <div className="step-text-group">
          <span className="step-heading">Extract your skills</span>
          <span className="step-subheading">We'll find your skills and experience</span>
        </div>
      </div>

      <div
        className="step-connector connector-2-3"
        style={{
          borderTop: currentStep >= 3 ? "2px solid #10B981" : "2px dotted #CBD5E1",
          background: "transparent"
        }}
      ></div>

      <div className={`step-item ${currentStep === 3 ? "completed active" : ""}`}>
        <div className="step-node-circle">{currentStep >= 3 ? <Check size={16} aria-hidden="true" /> : "3"}</div>
        <div className="step-text-group">
          <span className="step-heading">Find matching jobs</span>
          <span className="step-subheading">Discover roles tailored to you</span>
        </div>
      </div>
    </div>
  );
}

function NextStepsSection({ resume, matchedCount, onViewJobs, onChangeResume, onViewProfile }) {
  return (
    <div className="what-next-section">
      <h2 className="section-title">What happens next?</h2>
      <div className="what-next-grid">
        <div className="next-features-row">
          <div className="next-feature-card">
            <div className="feature-icon-box icon-blue">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2563EB" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
              </svg>
            </div>
            <div className="feature-text">
              <h4 className="feature-title">Skills extracted</h4>
              <p className="feature-desc">Identify skills, experience, and job titles.</p>
            </div>
          </div>

          <div className="next-feature-card">
            <div className="feature-icon-box icon-green">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
            </div>
            <div className="feature-text">
              <h4 className="feature-title">Relevant matches</h4>
              <p className="feature-desc">Find roles aligned with your profile.</p>
            </div>
          </div>

          <div className="next-feature-card">
            <div className="feature-icon-box icon-purple">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7C3AED" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                <circle cx="12" cy="7" r="4"></circle>
              </svg>
            </div>
            <div className="feature-text">
              <h4 className="feature-title">Your control</h4>
              <p className="feature-desc">Review your profile before searching.</p>
            </div>
          </div>
        </div>

        {/* RIGHT STATUS CARD */}
        <div className="resume-status-card">
          {!resume ? (
            <div className="empty-state">
              <div className="empty-doc-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="1.8">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                  <line x1="16" y1="13" x2="8" y2="13"></line>
                  <line x1="16" y1="17" x2="8" y2="17"></line>
                </svg>
              </div>
              <h4 className="status-title">No résumé uploaded yet</h4>
              <p className="status-subtitle">Your résumé is used to personalize your job search.</p>
            </div>
          ) : (
            <div className="active-state">
              <div className="active-header">
                <span className="active-badge"><CheckCircle2 size={14} aria-hidden="true" /> Active Profile</span>
                <span className="file-name-label">{resume.filename}</span>
              </div>
              {resume.candidate_name && <h3 className="candidate-name">{resume.candidate_name}</h3>}
              <p className="candidate-meta">
                {[
                  resume.target_roles && resume.target_roles[0],
                  resume.years_of_experience > 0
                    ? `${resume.years_of_experience}+ yrs`
                    : resume.seniority_level && resume.seniority_level !== "Unknown" ? resume.seniority_level : null,
                ].filter(Boolean).join(" • ")}
              </p>
              <div className="candidate-quick-skills">
                {(resume.skills || []).slice(0, 5).map((s, i) => (
                  <span key={i} className="quick-skill-tag">
                    {s}
                  </span>
                ))}
                {(resume.skills || []).length > 5 && (
                  <span className="quick-skill-tag">+{resume.skills.length - 5} more</span>
                )}
              </div>

              {resume.profile_strength && (
                <div
                  className="mini-strength-card"
                  onClick={onViewProfile}
                  style={{ cursor: "pointer", transition: "all 0.2s ease" }}
                  title="Click to view full Profile Strength breakdown & fix gaps"
                >
                  <div className="mini-strength-top">
                    <span className="mini-strength-title">Profile Strength: {resume.profile_strength.strength_tier}</span>
                    <span className="mini-strength-score">{resume.profile_strength.overall_score}%</span>
                  </div>
                  <div className="profile-strength-bar-bg" style={{ height: "6px" }}>
                    <div
                      className={`profile-strength-bar-fill tier-${resume.profile_strength.tier_badge_color || "blue"}`}
                      style={{ width: `${resume.profile_strength.overall_score}%` }}
                    />
                  </div>
                </div>
              )}
              <div className="active-card-actions">
                <button type="button" className="btn-view-matches" onClick={onViewJobs}>
                  <span>View <strong>{matchedCount}</strong> Jobs</span>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="9 18 15 12 9 6"></polyline>
                  </svg>
                </button>
                <button type="button" className="btn-text-change" onClick={onChangeResume}>
                  Replace
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Returns "" when the posting date is unknown so the UI can hide it.
function formatJobAge(dateStr) {
  const d = getPostedDate({ posted_at: dateStr });
  if (!d) return "";
  const diffDays = Math.floor((Date.now() - d.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays <= 0) return "today";
  if (diffDays === 1) return "1d ago";
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`;
  return `${Math.floor(diffDays / 365)}y ago`;
}

function getCompanySummary(job) {
  const provided = job.company_description || job.company_overview || job.about_company;
  if (typeof provided === "string" && provided.trim()) return sanitizeDisplayText(provided);
  return "No company description available.";
}

function getJobWorkMode(job) {
  const text = `${job.location || ""} ${job.title || ""} ${(job.description || "").slice(0, 1500)}`;
  if (/\bhybrid\b/i.test(text)) return "Hybrid";
  if (job.is_remote || /\bremote\b/i.test(text)) return "Remote";
  if (/\b(on[- ]?site|in[- ]office|office[- ]based|in[- ]person)\b/i.test(text)) return "On-site";
  return "";
}

function formatSalaryRange(job) {
  const amounts = getSalaryAmounts(job);
  if (!amounts.length) return "";
  const currency = amounts[0].currency;
  const same = amounts.filter((a) => a.currency === currency).map((a) => a.amount).filter((n) => n >= 1000);
  if (!same.length) return "";
  const symbol = { GBP: "£", EUR: "€", USD: "$" }[currency] || `${currency} `;
  const fmt = (n) => (n >= 1000 ? `${symbol}${Math.round(n / 1000)}K` : `${symbol}${n}`);
  const lo = Math.min(...same);
  const hi = Math.max(...same);
  return lo === hi ? fmt(lo) : `${fmt(lo)} – ${fmt(hi)}`;
}

function getVisaState(job) {
  const inIreland = Boolean(job.job_in_ireland);
  if (job.visa_sponsored && job.visa_sponsor_country === "Ireland") {
    const permits = job.ireland_permits_issued || {};
    const total = Object.values(permits).reduce((sum, n) => sum + n, 0);
    const years = Object.keys(permits).sort();
    return {
      tone: "ok",
      title: "Verified sponsor · Ireland",
      detail: total
        ? `Issued ${total.toLocaleString()} Irish employment permit${total === 1 ? "" : "s"} in ${years.join("–")}`
        : "Listed in the Irish employment permit data",
      tip: job.visa_sponsor_disclaimer || "Ireland has no sponsor licence register. Verify directly with the employer.",
    };
  }
  if (job.visa_sponsored) {
    return {
      tone: "ok",
      title: "Verified sponsor · UK",
      detail: "On the UK Home Office register · UK location confirmed",
      tip: `Employer matches the official UK Sponsor Register as ${job.visa_sponsor_registered_names?.join(", ") || "a listed organisation"}. This does not guarantee sponsorship for this vacancy.`,
    };
  }
  if (inIreland) {
    return job.visa_sponsor_registered
      ? {
        tone: "warn",
        title: "Not verified",
        detail: "A UK sponsor, but not found in the Irish employment permit data for this Ireland role",
        tip: "Verify directly with the employer.",
      }
      : {
        tone: "none",
        title: "No sponsorship evidence",
        detail: "Employer not found in the Irish employment permit data or the UK sponsor register",
        tip: "Verify directly with the employer.",
      };
  }
  if (job.visa_sponsor_registered) {
    return {
      tone: "warn",
      title: "Not verified",
      detail: job.visa_sponsor_location_status === "NON_UK"
        ? "Employer is a UK sponsor, but this role is outside the UK"
        : "Employer is a UK sponsor; this role's UK location isn't confirmed",
      tip: "Being on the sponsor register does not guarantee sponsorship for this vacancy.",
    };
  }
  return {
    tone: "none",
    title: "No sponsorship evidence",
    detail: "Employer was not found on the UK sponsor register",
    tip: "Verify directly with the employer.",
  };
}

function matchTone(score) {
  return score >= 85 ? "high" : score >= 70 ? "mid" : "low";
}

// Turns a posting's HTML into plain blocks (heading / paragraph / bullet) so it can be shown without injecting HTML.
function parseJobDescription(raw) {
  if (!raw) return [];
  const read = (html) => new DOMParser().parseFromString(html, "text/html");
  let doc = read(raw);
  // Some feeds send the HTML escaped (&lt;p&gt;…); decode once more when real tags only appear after decoding.
  const decoded = doc.body.textContent || "";
  if (!doc.body.querySelector("p, li, h1, h2, h3, h4, div, br, ul") && /<(p|li|h\d|div|ul|br)\b/i.test(decoded)) doc = read(decoded);
  const blocks = [];
  const push = (type, text) => {
    const t = (text || "").replace(/\s+/g, " ").trim();
    if (t) blocks.push({ type, text: t });
  };
  const walk = (node) => {
    node.childNodes.forEach((child) => {
      if (child.nodeType === 3) return;
      const tag = child.tagName?.toLowerCase();
      if (!tag || ["script", "style"].includes(tag)) return;
      if (/^h[1-6]$/.test(tag)) push("h", child.textContent);
      else if (tag === "li") push("li", child.textContent);
      else if (tag === "p") {
        const only = child.children.length === 1 && ["strong", "b"].includes(child.children[0].tagName.toLowerCase())
          && child.children[0].textContent.trim() === child.textContent.trim();
        push(only && child.textContent.trim().length < 90 ? "h" : "p", child.textContent);
      } else if (["ul", "ol", "div", "section", "article", "span", "body"].includes(tag)) {
        const hasBlocks = child.querySelector("p, li, h1, h2, h3, h4, h5, h6, ul, ol, div");
        if (hasBlocks) walk(child);
        else push("p", child.textContent);
      } else push("p", child.textContent);
    });
  };
  walk(doc.body);
  if (!blocks.length) (doc.body.textContent || "").split(/\n+/).forEach((line) => push("p", line));
  return blocks;
}

function JobListItem({ job, selected, inPipeline, onSelect, onTogglePipeline }) {
  const postingAge = formatJobAge(job.posted_at || job.created_at);
  const score = Number(job.match_score);
  const level = EXPERIENCE_LEVELS.find(([value]) => value === getExperienceLevel(job));
  return (
    <li className={`jd-item ${selected ? "selected" : ""}`}>
      <div
        className="jd-item-main"
        role="button"
        tabIndex={0}
        aria-pressed={selected}
        onClick={onSelect}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(); } }}
      >
        <div className="jd-item-logo">
          <div className="jd-logo"><CompanyBrandLogo company={job.company} /></div>
          {postingAge && <span className="jd-item-age"><Clock size={11} aria-hidden="true" /> {postingAge}</span>}
        </div>
        <div className="jd-item-body">
          <div className="jd-item-top">
            <h3>{job.title}</h3>
            {Number.isFinite(score) && score > 0 && <span className={`jd-match ${matchTone(score)}`}>{Math.round(score)}% Match</span>}
          </div>
          <div className="jd-sub">
            <span>{job.company || "Company not listed"}</span>
            <span className="jd-dot">•</span>
            <span>{job.location || "Location not listed"}</span>
          </div>
          <div className="jd-item-tags">
            {job.employment_type && <span>{job.employment_type}</span>}
            {job.visa_sponsored && <span className="visa">Visa Sponsorship</span>}
            {level && <span>{level[1]}</span>}
          </div>
        </div>
        <ChevronRight size={18} className="jd-item-chevron" aria-hidden="true" />
      </div>
      <button
        type="button"
        className={`jd-bookmark jd-item-bookmark ${inPipeline ? "saved" : ""}`}
        onClick={onTogglePipeline}
        aria-label={inPipeline ? `Remove ${job.title} from pipeline` : `Save ${job.title} to pipeline`}
        aria-pressed={inPipeline}
      >
        <Bookmark size={17} fill={inPipeline ? "currentColor" : "none"} aria-hidden="true" />
      </button>
    </li>
  );
}

function JobDetailPane({ job, inPipeline, onTogglePipeline, onOpenWorkspace }) {
  const [tab, setTab] = useState("details");
  const [company, setCompany] = useState({ jobId: null, data: null, error: "" });
  useEffect(() => { setTab("details"); }, [job?.id]);
  // Company research is fetched the first time the Company Info tab is opened for a job.
  useEffect(() => {
    if (tab !== "company" || !job?.id || company.jobId === job.id) return undefined;
    let cancelled = false;
    setCompany({ jobId: job.id, data: null, error: "" });
    fetch(`${API_BASE}/api/job-intelligence/${encodeURIComponent(job.id)}/company`)
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Company research is unavailable.");
        if (!cancelled) setCompany({ jobId: job.id, data: body, error: "" });
      })
      .catch((err) => { if (!cancelled) setCompany({ jobId: job.id, data: null, error: err.message }); });
    return () => { cancelled = true; };
  }, [tab, job?.id]);
  const blocks = useMemo(() => parseJobDescription(job?.description), [job?.id]);
  if (!job) return null;

  const postingAge = formatJobAge(job.posted_at || job.created_at);
  const score = Number(job.match_score);
  const level = EXPERIENCE_LEVELS.find(([value]) => value === getExperienceLevel(job));
  const salary = formatSalaryRange(job);
  const mode = getJobWorkMode(job);
  const visa = getVisaState(job);
  const skills = (job.matched_skills || []).filter(Boolean);
  const missing = (job.missing_skills || []).filter(Boolean);
  const reasons = (job.match_reasons || []).filter(Boolean);
  const co = company.jobId === job.id ? company.data : null;
  const companyLoading = tab === "company" && company.jobId === job.id && !co && !company.error;
  const companyRows = [
    ["Industry", co?.industry || job.industry],
    ["Headquarters", co?.headquarters || job.company_headquarters],
    ["Company size", co?.company_size || job.company_size],
    ["Website", co?.official_website || job.company_website],
    ["Careers page", co?.career_page],
    ["Hiring locations", co?.operating_locations?.length ? co.operating_locations.join("; ") : ""],
  ].filter(([, value]) => value);
  const companyOverview = co?.overview || (job.company_description ? sanitizeDisplayText(job.company_description) : "");

  return (
    <section className="jd-detail" aria-label={`${job.title} at ${job.company}`}>
      <header className="jd-detail-head">
        <div className="jd-logo big"><CompanyBrandLogo company={job.company} /></div>
        <div className="jd-detail-title">
          <h2>{job.title}</h2>
          <div className="jd-sub">
            <Building2 size={14} aria-hidden="true" />
            <span>{job.company || "Company not listed"}</span>
            <span className="jd-dot">•</span>
            <MapPin size={14} aria-hidden="true" />
            <span>{job.location || "Location not listed"}</span>
          </div>
        </div>
        {Number.isFinite(score) && score > 0 && <span className={`jd-match big ${matchTone(score)}`}>{Math.round(score)}% Match</span>}
      </header>

      <div className="jd-detail-chips">
        {job.employment_type && <span>{job.employment_type}</span>}
        {job.visa_sponsored && <span className="visa">Visa Sponsorship · {job.visa_sponsor_country}</span>}
        {level && <span>{level[1]}</span>}
        {mode && <span>{mode}</span>}
        {salary && <span>{salary}</span>}
        {postingAge && <span className="muted"><Clock size={13} aria-hidden="true" /> Posted {postingAge}</span>}
      </div>

      <div className="jd-detail-actions">
        <button type="button" className={`jd-save-btn ${inPipeline ? "saved" : ""}`} onClick={onTogglePipeline} aria-pressed={inPipeline}
          aria-label={inPipeline ? "Remove from pipeline" : "Save to pipeline"} title={inPipeline ? "In pipeline" : "Save to pipeline"}>
          <Bookmark size={18} fill={inPipeline ? "currentColor" : "none"} aria-hidden="true" />
        </button>
        <button type="button" className="jd-tailor-btn" onClick={onOpenWorkspace}>
          <Sparkles size={15} aria-hidden="true" /> Tailor with Cafy
        </button>
        {job.url ? (
          <a className="jd-apply-btn" href={job.url} target="_blank" rel="noopener noreferrer">
            Apply Now <ExternalLink size={15} aria-hidden="true" />
          </a>
        ) : (
          <button type="button" className="jd-apply-btn" onClick={onOpenWorkspace}>View details</button>
        )}
      </div>

      <div className="jd-tabs" role="tablist">
        {[["details", "Job Details"], ["company", "Company Info"], ["intelligence", "Job Intelligence"], ["why", "Why This Job?"]].map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      <div className="jd-tab-body">
        {tab === "details" && (
          <>
            {blocks.length === 0 && <p className="jd-muted">No full description is available for this job. Use Apply Now to read it on the employer's site.</p>}
            {blocks.map((b, i) => (
              b.type === "h" ? <h4 key={i}>{b.text}</h4>
                : b.type === "li" ? <p key={i} className="jd-li"><CheckCircle2 size={15} aria-hidden="true" /><span>{b.text}</span></p>
                  : <p key={i}>{b.text}</p>
            ))}
          </>
        )}

        {tab === "company" && (
          <>
            {companyLoading && <p className="jd-muted"><Loader2 size={14} className="doc-spin" aria-hidden="true" /> Researching {job.company}…</p>}
            {company.error && <p className="jd-muted">{company.error}</p>}
            {companyOverview && (
              <p>{companyOverview}{co?.overview_source && <span className="jd-muted"> (source: {co.overview_source})</span>}</p>
            )}
            {companyRows.length > 0 ? (
              <dl className="jd-facts">
                {companyRows.map(([label, value]) => (
                  <React.Fragment key={label}>
                    <dt>{label}</dt>
                    <dd>{/^https?:\/\//.test(value) ? <a href={value} target="_blank" rel="noopener noreferrer">{value.replace(/^https?:\/\//, "")}</a> : value}</dd>
                  </React.Fragment>
                ))}
              </dl>
            ) : !companyLoading && !companyOverview && <p className="jd-muted">No public company details were found for {job.company || "this company"}.</p>}
            {(co?.notes || []).map((n, i) => <p key={i} className="jd-muted jd-note">{n}</p>)}
          </>
        )}

        {tab === "intelligence" && <JobIntelligence key={job.id} job={job} />}

        {tab === "why" && (
          <>
            {reasons.length > 0 ? reasons.map((r, i) => <p key={i} className="jd-li"><CheckCircle2 size={15} aria-hidden="true" /><span>{r}</span></p>)
              : <p className="jd-muted">No match explanation is available for this job.</p>}
            {skills.length > 0 && (<><h4>Your matching skills</h4><div className="jd-skills">{skills.map((sk) => <span key={sk} className="jd-skill">{sk}</span>)}</div></>)}
            {missing.length > 0 && (<><h4>Skills the posting asks for that your résumé doesn't show</h4><div className="jd-skills">{missing.map((sk) => <span key={sk} className="jd-skill more">{sk}</span>)}</div></>)}
          </>
        )}
      </div>

      <div className={`jd-visa ${visa.tone}`} title={visa.tip}>
        <span className="jd-visa-icon" aria-hidden="true">
          {visa.tone === "ok" ? <Check size={14} /> : visa.tone === "warn" ? <AlertTriangle size={13} /> : <X size={13} />}
        </span>
        <div>
          <strong>Visa sponsorship · {visa.title}</strong>
          <span>{visa.detail}</span>
        </div>
      </div>
    </section>
  );
}

function normalizeClientResume(raw, masterResume, job) {
  if (!raw || typeof raw !== "object") raw = {};

  const parseBullets = (bullets) => {
    if (!bullets) return [];
    if (typeof bullets === "string") {
      const trimmed = bullets.trim();
      if ((trimmed.startsWith("[") && trimmed.endsWith("]")) || (trimmed.startsWith("(") && trimmed.endsWith(")"))) {
        try {
          const parsed = JSON.parse(trimmed.replace(/'/g, '"'));
          if (Array.isArray(parsed)) return parseBullets(parsed);
        } catch {
          const matches = trimmed.match(/'([^']+)'|"([^"]+)"/g);
          if (matches && matches.length) {
            return matches.map((m) => m.replace(/^['"]|['"]$/g, "").trim()).filter(Boolean);
          }
        }
      }
      return trimmed
        .split(/\r?\n/)
        .map((s) => s.replace(/^[\s\-\*•\d\.\)]+/, "").trim())
        .filter(Boolean);
    }
    if (Array.isArray(bullets)) {
      const res = [];
      for (const b of bullets) {
        if (typeof b === "string") {
          const bTrim = b.trim();
          if (bTrim.startsWith("[") && bTrim.endsWith("]")) {
            try {
              const parsed = JSON.parse(bTrim.replace(/'/g, '"'));
              if (Array.isArray(parsed)) {
                res.push(...parseBullets(parsed));
                continue;
              }
            } catch {
              const matches = bTrim.match(/'([^']+)'|"([^"]+)"/g);
              if (matches && matches.length) {
                res.push(...matches.map((m) => m.replace(/^['"]|['"]$/g, "").trim()).filter(Boolean));
                continue;
              }
            }
          }
          const cleaned = bTrim.replace(/^[\s\-\*•\d\.\)]+/, "").trim();
          if (cleaned) res.push(cleaned);
        } else if (Array.isArray(b)) {
          res.push(...parseBullets(b));
        } else if (b) {
          res.push(String(b).trim());
        }
      }
      return res;
    }
    return [];
  };

  const parseEntries = (entries, type) => {
    if (typeof entries === "string") {
      try {
        const parsed = JSON.parse(entries.replace(/'/g, '"'));
        if (Array.isArray(parsed)) entries = parsed;
      } catch {
        entries = [];
      }
    }
    if (!Array.isArray(entries)) return [];
    return entries
      .map((entry) => {
        if (!entry || typeof entry !== "object") return null;
        const title = String(entry.title || entry.role || entry.name || entry.degree || "").trim();
        const org = String(
          entry.organization || entry.company || entry.institution || entry.school || entry.issuer || ""
        ).trim();
        const dates = String(entry.dates || entry.date || entry.period || "").trim();
        const location = String(entry.location || "").trim();
        const description = String(entry.description || entry.summary || "").trim();
        const bullets = parseBullets(entry.bullets);
        return {
          title,
          organization: org,
          company: org,
          institution: org,
          degree: type === "education" ? title : "",
          name: title,
          dates,
          location,
          description,
          bullets,
        };
      })
      .filter((e) => e && (e.title || e.organization || e.bullets.length || e.description));
  };

  const pInfo = raw.personal_info || {};
  const masterSkills = Array.isArray(masterResume?.skills) ? masterResume.skills : [];
  const rawSkills = Array.isArray(raw.skills) ? raw.skills : parseBullets(raw.skills);

  const trimmedSummary = String(raw.professional_summary || masterResume?.summary || "").trim();
  const summarySentences = trimmedSummary.split(/(?<=[.!?])\s+/);
  const finalSummary = trimmedSummary.length > 450 && summarySentences.length >= 3
    ? summarySentences.slice(0, 3).join(" ")
    : trimmedSummary;

  const rawExp = (Array.isArray(raw.experience) && raw.experience.length) ? raw.experience : (masterResume?.experience || []);
  const rawProj = (Array.isArray(raw.projects) && raw.projects.length) ? raw.projects : (masterResume?.projects || []);
  const rawEdu = (Array.isArray(raw.education) && raw.education.length) ? raw.education : (masterResume?.education || []);
  const rawCerts = (Array.isArray(raw.certifications) && raw.certifications.length) ? raw.certifications : (masterResume?.certifications || []);

  let exps = parseEntries(rawExp, "experience").slice(0, 3).map((e) => ({
    ...e,
    bullets: (e.bullets || []).slice(0, 3),
  }));

  let projs = parseEntries(rawProj, "projects").slice(0, 3).map((p) => ({
    ...p,
    bullets: (p.bullets || []).slice(0, 3),
  }));

  let totalBullets = exps.reduce((acc, e) => acc + (e.bullets?.length || 0), 0) +
    projs.reduce((acc, p) => acc + (p.bullets?.length || 0), 0);
  if (totalBullets > 12) {
    projs = projs.map((p) => ({ ...p, bullets: (p.bullets || []).slice(0, 2) }));
    totalBullets = exps.reduce((acc, e) => acc + (e.bullets?.length || 0), 0) +
      projs.reduce((acc, p) => acc + (p.bullets?.length || 0), 0);
    if (totalBullets > 12) {
      exps = exps.map((e) => ({ ...e, bullets: (e.bullets || []).slice(0, 2) }));
    }
  }

  const edus = parseEntries(rawEdu, "education").slice(0, 3).map((e) => ({
    ...e,
    bullets: (e.bullets || []).slice(0, 2),
  }));
  const certs = parseEntries(rawCerts, "certifications").slice(0, 4);
  const skillsList = (rawSkills.length ? rawSkills : masterSkills).slice(0, 18);

  return {
    personal_info: {
      name: String(pInfo.name || masterResume?.candidate_name || "").trim(),
      email: String(pInfo.email || masterResume?.email || "").trim(),
      phone: String(pInfo.phone || masterResume?.phone || "").trim(),
      location: String(pInfo.location || masterResume?.location || "").trim(),
      linkedin: String(pInfo.linkedin || masterResume?.linkedin || "").trim(),
      github: String(pInfo.github || masterResume?.github || "").trim(),
      portfolio: String(pInfo.portfolio || pInfo.website || masterResume?.portfolio || masterResume?.website || "").trim(),
    },
    target_role: String(job?.title || raw.target_role || "").trim(),
    company: String(job?.company || raw.company || "").trim(),
    professional_summary: finalSummary,
    experience: exps,
    projects: projs,
    education: edus,
    certifications: certs,
    skills: skillsList,
  };
}

const sanitizeLinkedInHandle = (val) => {
  if (!val) return "";
  let clean = String(val).trim();
  clean = clean.replace(/^https?:\/\/(www\.)?/i, "");
  while (/^linkedin\.com\/in\/?/i.test(clean) || /^linkedin\.com\/?/i.test(clean)) {
    clean = clean.replace(/^linkedin\.com\/in\/?/i, "").replace(/^linkedin\.com\/?/i, "");
  }
  return clean.replace(/\/$/, "");
};

const sanitizeGitHubHandle = (val) => {
  if (!val) return "";
  let clean = String(val).trim();
  clean = clean.replace(/^https?:\/\/(www\.)?/i, "");
  while (/^github\.com\/?/i.test(clean)) {
    clean = clean.replace(/^github\.com\/?/i, "");
  }
  return clean.replace(/\/$/, "");
};

const sanitizePortfolioUrl = (val) => {
  if (!val) return "";
  let clean = String(val).trim();
  return clean.replace(/^https?:\/\//i, "").replace(/\/$/, "");
};

function LinkifiedText({ text }) {
  if (!text) return null;
  const parts = [];
  const urlRegex = /(https?:\/\/[^\s<]+[^<.,:;"')\]\s])/g;
  let lastIndex = 0;
  let match;
  while ((match = urlRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const url = match[0];
    parts.push(
      <a key={match.index} href={url} target="_blank" rel="noopener noreferrer" style={{ color: "#2563EB", textDecoration: "underline" }}>
        {url}
      </a>
    );
    lastIndex = match.index + url.length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return <>{parts.length > 0 ? parts : text}</>;
}

function ResumeDocumentPreview({ resume, job, resumeReady, isGeneratingResume }) {
  if (isGeneratingResume) {
    return (
      <div className="resume-paper is-empty">
        <div className="preview-empty-state">
          <div className="career-chat-thinking-bubble" style={{ margin: "0 auto 12px", width: "fit-content" }}>
            <span />
            <span />
            <span />
          </div>
          <strong>Generating ATS-Tailored Resume…</strong>
          <p>Analyzing job requirements and formatting your experience.</p>
        </div>
      </div>
    );
  }

  if (!resumeReady || !resume) {
    return (
      <div className="resume-paper is-empty">
        <div className="preview-empty-state">
          <div className="preview-empty-icon"><Sparkles size={28} aria-hidden="true" /></div>
          <strong>Your tailored resume preview</strong>
          <p>Generate a draft to see the role-focused version here.</p>
        </div>
      </div>
    );
  }

  const pInfo = resume.personal_info || {};
  const targetRole = resume.target_role || job?.title || "";
  const linkedInHandle = sanitizeLinkedInHandle(pInfo.linkedin);
  const gitHubHandle = sanitizeGitHubHandle(pInfo.github);
  const portfolioClean = sanitizePortfolioUrl(pInfo.portfolio || pInfo.website);

  return (
    <div className="resume-preview-sheet-wrapper">
      <div className="resume-paper-doc" id="resume-printable-doc">
        <div className="resume-paper-content">
          {/* 1. Header: Sebastian Bennett ATS Style */}
          {pInfo.name && <h1 style={{ letterSpacing: "0.04em" }}>{pInfo.name.toUpperCase()}</h1>}
          {targetRole && <div className="paper-role">{targetRole}</div>}

          <div className="paper-contact-bar">
            {pInfo.phone && (
              <span>
                <Phone size={12} aria-hidden="true" /> <a href={`tel:${pInfo.phone.replace(/[^\d+]/g, "")}`}>{pInfo.phone}</a>
              </span>
            )}
            {pInfo.email && (
              <span>
                <Mail size={12} aria-hidden="true" /> <a href={`mailto:${pInfo.email}`}>{pInfo.email}</a>
              </span>
            )}
            {pInfo.location && <span><MapPin size={12} aria-hidden="true" /> {pInfo.location}</span>}
            {linkedInHandle && (
              <span>
                <Linkedin size={12} aria-hidden="true" /> <a href={`https://linkedin.com/in/${linkedInHandle}`} target="_blank" rel="noopener noreferrer">linkedin.com/in/{linkedInHandle}</a>
              </span>
            )}
            {gitHubHandle && (
              <span>
                <Github size={12} aria-hidden="true" /> <a href={`https://github.com/${gitHubHandle}`} target="_blank" rel="noopener noreferrer">github.com/{gitHubHandle}</a>
              </span>
            )}
            {portfolioClean && (
              <span>
                <Globe size={12} aria-hidden="true" /> <a href={`https://${portfolioClean}`} target="_blank" rel="noopener noreferrer">{portfolioClean}</a>
              </span>
            )}
          </div>
          <hr className="paper-header-hr" />

          {/* 2. Professional Summary / About Me */}
          {resume.professional_summary && (
            <div className="paper-section">
              <div className="paper-section-title">Professional Summary</div>
              <p className="paper-summary" style={{ textAlign: "justify" }}>{resume.professional_summary}</p>
              <hr className="paper-section-hr" />
            </div>
          )}

          {/* 3. Work Experience */}
          {resume.experience && resume.experience.length > 0 && (
            <div className="paper-section">
              <div className="paper-section-title">Work Experience</div>
              {resume.experience.map((exp, idx) => (
                <div className="paper-entry" key={`exp-${idx}`} style={{ marginBottom: 10 }}>
                  <div className="paper-entry-meta">
                    <span className="paper-entry-company">
                      {exp.organization || exp.company || ""}
                      {exp.location ? ` | ${exp.location}` : ""}
                    </span>
                    {exp.dates && <span className="paper-entry-dates">{exp.dates}</span>}
                  </div>
                  {exp.title && <div className="paper-entry-title">{exp.title}</div>}
                  {exp.description && <p className="paper-summary">{exp.description}</p>}
                  {exp.bullets && exp.bullets.length > 0 && (
                    <ul className="paper-bullets">
                      {exp.bullets.map((b, bIdx) => (
                        <li key={`exp-${idx}-b-${bIdx}`}><LinkifiedText text={b} /></li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
              <hr className="paper-section-hr" />
            </div>
          )}

          {/* 4. Projects */}
          {resume.projects && resume.projects.length > 0 && (
            <div className="paper-section">
              <div className="paper-section-title">Projects</div>
              {resume.projects.map((proj, idx) => (
                <div className="paper-entry" key={`proj-${idx}`} style={{ marginBottom: 10 }}>
                  <div className="paper-entry-meta">
                    <span className="paper-entry-company">
                      {proj.title || ""}
                      {proj.organization ? ` | ${proj.organization}` : ""}
                    </span>
                    {proj.dates && <span className="paper-entry-dates">{proj.dates}</span>}
                  </div>
                  {proj.description && <p className="paper-summary"><LinkifiedText text={proj.description} /></p>}
                  {proj.bullets && proj.bullets.length > 0 && (
                    <ul className="paper-bullets">
                      {proj.bullets.map((b, bIdx) => (
                        <li key={`proj-${idx}-b-${bIdx}`}><LinkifiedText text={b} /></li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
              <hr className="paper-section-hr" />
            </div>
          )}

          {/* 5. Education */}
          {resume.education && resume.education.length > 0 && (
            <div className="paper-section">
              <div className="paper-section-title">Education</div>
              {resume.education.map((edu, idx) => (
                <div className="paper-entry" key={`edu-${idx}`} style={{ marginBottom: 8 }}>
                  <div className="paper-entry-meta">
                    <span className="paper-entry-company">
                      {edu.institution || edu.organization || edu.school || ""}
                      {edu.location ? ` | ${edu.location}` : ""}
                    </span>
                    {edu.dates && <span className="paper-entry-dates">{edu.dates}</span>}
                  </div>
                  {(edu.degree || edu.title) && <div className="paper-entry-title">{edu.degree || edu.title}</div>}
                  {edu.description && <p className="paper-summary"><LinkifiedText text={edu.description} /></p>}
                  {edu.bullets && edu.bullets.length > 0 && (
                    <ul className="paper-bullets">
                      {edu.bullets.map((b, bIdx) => (
                        <li key={`edu-${idx}-b-${bIdx}`}><LinkifiedText text={b} /></li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
              <hr className="paper-section-hr" />
            </div>
          )}

          {/* 6. Skills in 3-column bulleted grid matching Sebastian Bennett image */}
          {resume.skills && resume.skills.length > 0 && (
            <div className="paper-section">
              <div className="paper-section-title">Core Skills</div>
              <div className="paper-skills-grid">
                {resume.skills.map((skill, sIdx) => (
                  <div className="paper-skill-item" key={`sk-${sIdx}`}>
                    <span className="paper-bullet-dot">•</span> {skill}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 7. Certifications if any */}
          {resume.certifications && resume.certifications.length > 0 && (
            <div className="paper-section" style={{ marginTop: 8 }}>
              <hr className="paper-section-hr" />
              <div className="paper-section-title">Certifications</div>
              {resume.certifications.map((cert, idx) => (
                <div className="paper-entry" key={`cert-${idx}`} style={{ marginBottom: 4 }}>
                  <div className="paper-entry-meta">
                    <span className="paper-entry-title">{cert.name || cert.title || ""}</span>
                    {cert.dates && <span className="paper-entry-dates">{cert.dates}</span>}
                  </div>
                  {cert.issuer && <div className="paper-entry-loc">{cert.issuer}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SuggestionsPanel({ job, resume, tailoredResume, onRewriteSummary, isRewriting }) {
  const missingSkills = Array.isArray(job.missing_skills) ? job.missing_skills : [];
  const targetRole = job.title || "this role";
  const company = job.company || "the employer";

  return (
    <div className="suggestions-wrap">
      <div className="suggestion-box">
        <div className="suggestion-box-header">
          <strong>1. Professional Summary Alignment</strong>
          <button
            type="button"
            className="ai-action"
            onClick={onRewriteSummary}
            disabled={isRewriting}
            title="Rewrite summary with AI"
          >
            {isRewriting ? "Rewriting with AI…" : "Improve with AI"}
          </button>
        </div>
        <p>
          Tailor your opening statement to directly emphasize how your background solves key engineering challenges for{" "}
          <strong>{company}</strong> as a <strong>{targetRole}</strong>.
        </p>
      </div>

      <div className="suggestion-box">
        <div className="suggestion-box-header">
          <strong>2. Project & Experience Prioritization</strong>
        </div>
        <p>
          Lead each work experience entry with technical accomplishments that demonstrate overlapping stack
          capabilities. Place projects directly related to {targetRole} near the top of your document.
        </p>
      </div>

      <div className="suggestion-box">
        <div className="suggestion-box-header">
          <strong>3. Bullet-Point Clarity & Measurable Outcomes</strong>
        </div>
        <p>
          Use strong action verbs followed by scope and measurable business impact (e.g., "Engineered FastAPI
          microservices reducing API latency by 35%"). Review bullets in the editor to ensure each claim is supported
          by your source background.
        </p>
      </div>

      {missingSkills.length > 0 && (
        <div className="suggestion-box">
          <div className="suggestion-box-header">
            <strong>4. Genuine Keyword Coverage</strong>
          </div>
          <p>
            The role highlights <strong>{missingSkills.slice(0, 3).join(", ")}</strong>. If you have touched these tools
            in academic or personal projects, add those specific bullet points in the Editor tab.
          </p>
        </div>
      )}

      <div className="suggestion-box">
        <div className="suggestion-box-header">
          <strong>5. ATS-Friendly Layout</strong>
        </div>
        <p>
          The template uses a single column, standard section headings and no graphics or tables, which
          applicant tracking systems generally parse well. Keep the resume to one or two pages.
        </p>
      </div>
    </div>
  );
}

function JobDetailModal({ job, onClose, resume, onUpdateResume, onTogglePipeline, inPipeline, fullPage = false, resumeOnly = false }) {
  const [activeTab, setActiveTab] = useState("application");
  const [workspaceTab, setWorkspaceTab] = useState("editor");
  const [isGeneratingResume, setIsGeneratingResume] = useState(false);
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [isRewriting, setIsRewriting] = useState(false);
  const [resumeError, setResumeError] = useState("");
  const [resumeReady, setResumeReady] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [applicationStatus, setApplicationStatus] = useState("Not started");
  const [draftSaved, setDraftSaved] = useState(false);
  const [generatedOutput, setGeneratedOutput] = useState(null);
  // The editor's in-browser PDF of the current edits, reused by Download Resume.
  const pdfFileRef = useRef(null);
  const handlePdfReady = useCallback((file) => { pdfFileRef.current = file; }, []);
  const [tailoredResume, setTailoredResume] = useState(() => normalizeClientResume({}, resume, job));
  // Last generated/saved version, used by the editor's Reset button.
  const [savedSnapshot, setSavedSnapshot] = useState(null);
  // Outcome of the last full "Rewrite with AI": lines kept unchanged + skills to consider adding.
  const [rewriteResult, setRewriteResult] = useState(null);
  // Tailor flow inputs (Screen 2): the job description is pre-filled from the job and can be edited.
  const [tailorJobDescription, setTailorJobDescription] = useState(() => sanitizeDisplayText(job?.description || ""));
  const [additionalInstructions, setAdditionalInstructions] = useState("");

  useEffect(() => {
    setTailorJobDescription(sanitizeDisplayText(job?.description || ""));
  }, [job?.id, job?.description]);

  // Live job-match scoring of the tailored resume while it is open in the editor. Re-runs
  // (debounced) on every change, including AI rewrites, so section scores stay current.
  const editorProfile = useMemo(() => tailoredResumeToProfile(tailoredResume, resume), [tailoredResume, resume]);
  const editorScoring = useJobMatchAnalysis(
    resumeReady && workspaceTab === "editor" ? job.id : null,
    editorProfile,
    600
  );

  const existingSkillsLower = new Set((tailoredResume?.skills || []).map((s) => String(s).trim().toLowerCase()));
  const candidateJobSkills = [
    ...(Array.isArray(job.extracted_skills) ? job.extracted_skills : []),
    ...(Array.isArray(job.missing_skills) ? job.missing_skills : []),
    ...(Array.isArray(job.matched_skills) ? job.matched_skills : []),
  ];
  const recommendedSkills = Array.from(
    new Set(
      candidateJobSkills
        .map((s) => String(s).trim())
        .filter((s) => s.length > 1 && !existingSkillsLower.has(s.toLowerCase()))
    )
  ).slice(0, 15);

  // Load existing saved tailored resume from backend if available
  useEffect(() => {
    let isCancelled = false;
    async function loadSavedResume() {
      if (!job?.id) return;
      try {
        const resp = await fetch(`${API_BASE}/api/resumes/job/${job.id}`);
        if (resp.ok) {
          const data = await resp.json();
          if (!isCancelled && data.status === "found" && data.tailored_resume) {
            const normalized = normalizeClientResume(data.tailored_resume, resume, job);
            setTailoredResume(normalized);
            setSavedSnapshot(normalized);
            setGeneratedOutput(data);
            setResumeReady(true);
            setApplicationStatus("Tailored resume ready");
          }
        }
      } catch (e) {
        // Fall back to clean initial state
      }
    }
    loadSavedResume();
    return () => {
      isCancelled = true;
    };
  }, [job?.id]);

  const handleGenerateResume = async () => {
    if (!resume) {
      setResumeError("Upload a résumé before generating a tailored version.");
      return;
    }

    setResumeError("");
    setIsGeneratingResume(true);
    setApplicationStatus("Tailoring resume…");

    try {
      const response = await fetch(`${API_BASE}/api/resumes/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: job.id,
          resume_data: resume,
          job_description: tailorJobDescription.trim() !== String(job?.description || "").trim() ? tailorJobDescription : undefined,
          additional_instructions: additionalInstructions.trim() || undefined,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `Generation failed (${response.status})`);
      }
      const rawGen = data.resume || data.tailored_resume || {};
      const normalized = normalizeClientResume(rawGen, resume, job);
      setGeneratedOutput(data);
      setTailoredResume(normalized);
      setSavedSnapshot(normalized);
      setResumeReady(true);
      setApplicationStatus("Tailored resume ready");
      setDraftSaved(false);
      setWorkspaceTab("editor");
    } catch (error) {
      setResumeError(error.message || "Resume generation failed. Please retry.");
      setApplicationStatus("Generation failed");
    } finally {
      setIsGeneratingResume(false);
    }
  };

  const handleSaveDraft = async () => {
    setIsSavingDraft(true);
    try {
      const resp = await fetch(`${API_BASE}/api/resumes/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: job.id,
          resume_id: generatedOutput?.resume_id,
          resume: tailoredResume,
        }),
      });
      const data = await resp.json();
      if (resp.ok) {
        setGeneratedOutput((prev) => ({ ...prev, ...data }));
        setSavedSnapshot(tailoredResume);
        setDraftSaved(true);
        setApplicationStatus("Draft saved");
        setTimeout(() => setDraftSaved(false), 3000);
      }
    } catch (e) {
      setResumeError("Failed to save draft to server.");
    } finally {
      setIsSavingDraft(false);
    }
  };

  // Rewrites the whole resume for this job and stores it as a new version. The backend rejects any
  // line that would add facts; missing job skills come back as recommendations, never inserted.
  const handleRewriteFull = async () => {
    setIsRewriting(true);
    setResumeError("");
    setRewriteResult(null);
    try {
      const resp = await fetch(`${API_BASE}/api/resumes/rewrite-full`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: job.id, resume_id: generatedOutput?.resume_id, resume: tailoredResume }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `AI rewrite failed (${resp.status})`);
      const normalized = normalizeClientResume(data.resume, resume, job);
      setTailoredResume(normalized);
      setSavedSnapshot(normalized);
      setGeneratedOutput((prev) => ({ ...prev, ...data }));
      setRewriteResult({ rejectedLines: data.rejected_lines || 0, recommendedSkills: data.recommended_skills || [] });
      setApplicationStatus("Rewritten with AI");
    } catch (error) {
      setResumeError(error.message || "AI rewrite failed. Please try again.");
    } finally {
      setIsRewriting(false);
    }
  };

  const generatePrintableResumeHtml = (resumeData, jobData) => {
    const res = resumeData || {};
    const pInfo = res.personal_info || {};
    const role = res.target_role || jobData?.title || "";
    const linkedInHandle = sanitizeLinkedInHandle(pInfo.linkedin);
    const gitHubHandle = sanitizeGitHubHandle(pInfo.github);
    const portfolioClean = sanitizePortfolioUrl(pInfo.portfolio || pInfo.website);

    const renderClickableText = (text) => {
      if (!text) return "";
      const urlRegex = /(https?:\/\/[^\s<]+[^<.,:;"')\]\s])/g;
      return String(text).replace(urlRegex, (url) => {
        return `<a href="${url}" target="_blank" rel="noopener noreferrer" style="color: #2563EB; text-decoration: underline;">${url}</a>`;
      });
    };

    const expHtml = (res.experience || []).map((exp) => `
      <div class="paper-entry">
        <div class="paper-entry-meta">
          <span class="paper-entry-company">${exp.organization || exp.company || ""}${exp.location ? ` | ${exp.location}` : ""}</span>
          ${exp.dates ? `<span class="paper-entry-dates">${exp.dates}</span>` : ""}
        </div>
        ${exp.title ? `<div class="paper-entry-title">${exp.title}</div>` : ""}
        ${exp.description ? `<p class="paper-summary">${renderClickableText(exp.description)}</p>` : ""}
        ${exp.bullets && exp.bullets.length > 0 ? `
          <ul class="paper-bullets">
            ${exp.bullets.map(b => `<li>${renderClickableText(b)}</li>`).join("")}
          </ul>
        ` : ""}
      </div>
    `).join("");

    const projHtml = (res.projects || []).map((proj) => `
      <div class="paper-entry">
        <div class="paper-entry-meta">
          <span class="paper-entry-company">${proj.title || ""}${proj.organization ? ` | ${proj.organization}` : ""}</span>
          ${proj.dates ? `<span class="paper-entry-dates">${proj.dates}</span>` : ""}
        </div>
        ${proj.description ? `<p class="paper-summary">${renderClickableText(proj.description)}</p>` : ""}
        ${proj.bullets && proj.bullets.length > 0 ? `
          <ul class="paper-bullets">
            ${proj.bullets.map(b => `<li>${renderClickableText(b)}</li>`).join("")}
          </ul>
        ` : ""}
      </div>
    `).join("");

    const eduHtml = (res.education || []).map((edu) => `
      <div class="paper-entry">
        <div class="paper-entry-meta">
          <span class="paper-entry-company">${edu.institution || edu.organization || edu.school || ""}${edu.location ? ` | ${edu.location}` : ""}</span>
          ${edu.dates ? `<span class="paper-entry-dates">${edu.dates}</span>` : ""}
        </div>
        ${(edu.degree || edu.title) ? `<div class="paper-entry-title">${edu.degree || edu.title}</div>` : ""}
        ${edu.description ? `<p class="paper-summary">${renderClickableText(edu.description)}</p>` : ""}
        ${edu.bullets && edu.bullets.length > 0 ? `
          <ul class="paper-bullets">
            ${edu.bullets.map(b => `<li>${renderClickableText(b)}</li>`).join("")}
          </ul>
        ` : ""}
      </div>
    `).join("");

    const skillsHtml = (res.skills || []).map(skill => `
      <div class="paper-skill-item">
        <span class="paper-bullet-dot">•</span> <span>${skill}</span>
      </div>
    `).join("");

    const certsHtml = (res.certifications || []).map((cert) => `
      <div class="paper-entry">
        <div class="paper-entry-meta">
          <span class="paper-entry-title">${cert.name || cert.title || ""}</span>
          ${cert.dates ? `<span class="paper-entry-dates">${cert.dates}</span>` : ""}
        </div>
        ${cert.issuer ? `<div class="paper-entry-loc">${cert.issuer}</div>` : ""}
      </div>
    `).join("");

    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${pInfo.name ? `${pInfo.name}_Resume` : "Resume"}</title>
  <style>
    @page {
      size: A4 portrait;
      margin: 12mm 14mm 10mm 14mm;
    }
    * {
      box-sizing: border-box;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    html, body {
      margin: 0;
      padding: 0;
      background: #FFFFFF;
      color: #0F172A;
      font-family: "Calibri", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 10.2pt;
      line-height: 1.44;
    }
    .resume-paper-doc {
      width: 100%;
      max-width: 794px;
      margin: 0 auto;
      padding: 0;
      background: #FFFFFF;
      box-sizing: border-box;
    }
    h1 {
      font-size: 1.75rem;
      font-weight: 800;
      text-align: center;
      color: #0F172A;
      margin: 0 0 3px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .paper-role {
      font-size: 1.05rem;
      text-align: center;
      color: #334155;
      font-weight: 600;
      margin: 0 0 6px;
    }
    .paper-contact-bar {
      display: flex;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
      gap: 6px 14px;
      font-size: 0.84rem;
      color: #475569;
      margin: 3px 0 8px;
    }
    .paper-contact-bar a {
      color: #0F172A;
      text-decoration: underline;
      text-decoration-color: #94A3B8;
      text-underline-offset: 2px;
      transition: color 0.15s ease;
    }
    .paper-contact-bar a:hover {
      color: #2563EB;
      text-decoration-color: #2563EB;
    }
    .paper-bullets a, .paper-summary a {
      color: #2563EB;
      text-decoration: underline;
      text-underline-offset: 2px;
    }
    .paper-header-hr, .paper-section-hr {
      border: none;
      border-top: 1.5px solid #CBD5E1;
      margin: 7px 0;
    }
    .paper-section {
      margin-top: 8px;
      page-break-inside: avoid;
      break-inside: avoid;
    }
    .paper-section-title {
      font-size: 0.94rem;
      font-weight: 800;
      color: #0F172A;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 2px solid #0F172A;
      padding-bottom: 2px;
      margin: 8px 0 5px;
    }
    .paper-summary {
      font-size: 0.88rem;
      line-height: 1.45;
      margin: 3px 0 6px;
      text-align: justify;
      color: #1E293B;
    }
    .paper-entry {
      margin-bottom: 8px;
      page-break-inside: avoid;
      break-inside: avoid;
    }
    .paper-entry-meta {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      font-size: 0.86rem;
      color: #64748B;
      margin-bottom: 2px;
    }
    .paper-entry-company {
      font-weight: 700;
      color: #334155;
    }
    .paper-entry-dates {
      font-size: 0.84rem;
      color: #64748B;
    }
    .paper-entry-title {
      font-size: 0.90rem;
      font-weight: 750;
      color: #0F172A;
    }
    .paper-entry-loc {
      font-size: 0.82rem;
      color: #64748B;
    }
    .paper-bullets {
      margin: 3px 0 6px;
      padding-left: 20px;
    }
    .paper-bullets li {
      font-size: 0.85rem;
      line-height: 1.42;
      margin-bottom: 2.5px;
      color: #1E293B;
    }
    .paper-skills-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 5px 14px;
      margin: 5px 0;
    }
    .paper-skill-item {
      font-size: 0.85rem;
      color: #334155;
      display: flex;
      align-items: center;
      gap: 6px;
      line-height: 1.35;
    }
    .paper-bullet-dot {
      color: #0F172A;
      font-weight: bold;
    }
  </style>
</head>
<body>
  <div class="resume-paper-doc" id="resume-printable-doc">
    <div class="resume-paper-content">
      ${pInfo.name ? `<h1>${pInfo.name.toUpperCase()}</h1>` : ""}
      ${role ? `<div class="paper-role">${role}</div>` : ""}
      <div class="paper-contact-bar">
        ${pInfo.phone ? `<span><a href="tel:${pInfo.phone.replace(/[^\d+]/g, '')}">${pInfo.phone}</a></span>` : ""}
        ${pInfo.email ? `<span><a href="mailto:${pInfo.email}">${pInfo.email}</a></span>` : ""}
        ${pInfo.location ? `<span>${pInfo.location}</span>` : ""}
        ${linkedInHandle ? `<span><a href="https://linkedin.com/in/${linkedInHandle}" target="_blank" rel="noopener noreferrer">linkedin.com/in/${linkedInHandle}</a></span>` : ""}
        ${gitHubHandle ? `<span><a href="https://github.com/${gitHubHandle}" target="_blank" rel="noopener noreferrer">github.com/${gitHubHandle}</a></span>` : ""}
        ${portfolioClean ? `<span><a href="https://${portfolioClean}" target="_blank" rel="noopener noreferrer">${portfolioClean}</a></span>` : ""}
      </div>
      <hr class="paper-header-hr" />

      ${res.professional_summary ? `
        <div class="paper-section">
          <div class="paper-section-title">Professional Summary</div>
          <p class="paper-summary">${res.professional_summary}</p>
          <hr class="paper-section-hr" />
        </div>
      ` : ""}

      ${expHtml ? `
        <div class="paper-section">
          <div class="paper-section-title">Work Experience</div>
          ${expHtml}
          <hr class="paper-section-hr" />
        </div>
      ` : ""}

      ${projHtml ? `
        <div class="paper-section">
          <div class="paper-section-title">Projects</div>
          ${projHtml}
          <hr class="paper-section-hr" />
        </div>
      ` : ""}

      ${eduHtml ? `
        <div class="paper-section">
          <div class="paper-section-title">Education</div>
          ${eduHtml}
          <hr class="paper-section-hr" />
        </div>
      ` : ""}

      ${skillsHtml ? `
        <div class="paper-section">
          <div class="paper-section-title">Core Skills</div>
          <div class="paper-skills-grid">
            ${skillsHtml}
          </div>
        </div>
      ` : ""}

      ${certsHtml ? `
        <div class="paper-section">
          <hr class="paper-section-hr" />
          <div class="paper-section-title">Certifications</div>
          ${certsHtml}
        </div>
      ` : ""}
    </div>
  </div>
</body>
</html>`;
  };

  const handleDownloadResume = (format = "pdf") => {
    if (format === "pdf") {
      if (pdfFileRef.current) {
        saveBlob(pdfFileRef.current.blob, pdfFileRef.current.name);
        return;
      }
      if (generatedOutput?.pdf_url) {
        window.open(withToken(`${API_BASE}${generatedOutput.pdf_url}`), "_blank", "noopener,noreferrer");
        return;
      }
      const printableHtml = generatePrintableResumeHtml(tailoredResume, job);

      // Open a clean dedicated print window containing ONLY the resume (guaranteed 1 page)
      try {
        const printWin = window.open("", "_blank", "width=850,height=1100");
        if (printWin) {
          printWin.document.open();
          printWin.document.write(printableHtml);
          printWin.document.close();
          printWin.focus();
          setTimeout(() => {
            try {
              printWin.print();
            } catch (err) {
              console.error("Print window error:", err);
            }
          }, 350);
          return;
        }
      } catch (err) {
        console.warn("Popup blocked, trying off-screen iframe:", err);
      }

      // Fallback: off-screen iframe with A4 layout
      const printFrame = document.createElement("iframe");
      printFrame.style.position = "fixed";
      printFrame.style.left = "-10000px";
      printFrame.style.top = "-10000px";
      printFrame.style.width = "800px";
      printFrame.style.height = "1150px";
      printFrame.style.border = "none";
      document.body.appendChild(printFrame);

      const frameDoc = printFrame.contentWindow?.document;
      if (frameDoc) {
        frameDoc.open();
        frameDoc.write(printableHtml);
        frameDoc.close();
        setTimeout(() => {
          try {
            printFrame.contentWindow.focus();
            printFrame.contentWindow.print();
          } catch (e) {
            window.print();
          } finally {
            setTimeout(() => {
              try { document.body.removeChild(printFrame); } catch (_) { }
            }, 2500);
          }
        }, 350);
        return;
      }
      window.print();
      return;
    }
    if (format === "docx") {
      if (generatedOutput?.docx_url) {
        window.open(withToken(`${API_BASE}${generatedOutput.docx_url}`), "_blank", "noopener,noreferrer");
      } else {
        setResumeError("DOCX file is not ready yet. Please save draft or re-generate.");
      }
      return;
    }
    if (format === "latex") {
      if (generatedOutput?.tex_url) {
        window.open(withToken(`${API_BASE}${generatedOutput.tex_url}`), "_blank", "noopener,noreferrer");
      } else {
        setResumeError("LaTeX source is not ready yet.");
      }
      return;
    }
  };

  const handleRewriteSection = async (sectionKey, itemIndex = null, bulletIndex = null) => {
    setIsRewriting(true);
    setResumeError("");
    try {
      let content = "";
      if (sectionKey === "professional_summary") {
        content = tailoredResume.professional_summary;
      } else if (sectionKey === "experience" && itemIndex !== null) {
        if (bulletIndex !== null) {
          content = tailoredResume.experience[itemIndex]?.bullets?.[bulletIndex] || "";
        } else {
          content = (tailoredResume.experience[itemIndex]?.bullets || []).join("\n") || tailoredResume.experience[itemIndex]?.description || "";
        }
      } else if (sectionKey === "projects" && itemIndex !== null) {
        if (bulletIndex !== null) {
          content = tailoredResume.projects[itemIndex]?.bullets?.[bulletIndex] || "";
        } else {
          content = (tailoredResume.projects[itemIndex]?.bullets || []).join("\n") || tailoredResume.projects[itemIndex]?.description || "";
        }
      } else if (sectionKey === "all") {
        content = tailoredResume.professional_summary;
      }

      // An empty summary is drafted by the server from the rest of the resume. Anything else needs
      // something to work from, since the AI must not invent experience.
      const isSummary = sectionKey === "professional_summary" || sectionKey === "all";
      if (!String(content || "").trim() && !isSummary) {
        setResumeError("Write a rough first draft (even one line) and AI will polish it. AI will not make up experience you have not entered.");
        return;
      }

      const resp = await fetch(`${API_BASE}/api/resumes/rewrite-section`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: job.id,
          section: bulletIndex !== null ? "bullet" : sectionKey,
          content,
          resume_data: tailoredResume,
        }),
      });
      const data = await resp.json();
      if (resp.ok && data.rewritten) {
        if (sectionKey === "professional_summary" || sectionKey === "all") {
          setTailoredResume((prev) => ({ ...prev, professional_summary: data.rewritten }));
        } else if (sectionKey === "experience" && itemIndex !== null) {
          setTailoredResume((prev) => {
            const list = [...(prev.experience || [])];
            if (bulletIndex !== null) {
              const bullets = [...(list[itemIndex].bullets || [])];
              bullets[bulletIndex] = data.rewritten;
              list[itemIndex] = { ...list[itemIndex], bullets };
            } else {
              const bullets = data.rewritten
                .split("\n")
                .map((b) => b.replace(/^[\s\-\*•\d\.\)]+/, "").trim())
                .filter(Boolean);
              list[itemIndex] = { ...list[itemIndex], bullets: bullets.length ? bullets : list[itemIndex].bullets };
            }
            return { ...prev, experience: list };
          });
        } else if (sectionKey === "projects" && itemIndex !== null) {
          setTailoredResume((prev) => {
            const list = [...(prev.projects || [])];
            if (bulletIndex !== null) {
              const bullets = [...(list[itemIndex].bullets || [])];
              bullets[bulletIndex] = data.rewritten;
              list[itemIndex] = { ...list[itemIndex], bullets };
            } else {
              const bullets = data.rewritten
                .split("\n")
                .map((b) => b.replace(/^[\s\-\*•\d\.\)]+/, "").trim())
                .filter(Boolean);
              list[itemIndex] = { ...list[itemIndex], bullets: bullets.length ? bullets : list[itemIndex].bullets };
            }
            return { ...prev, projects: list };
          });
        }
        setDraftSaved(false);
      } else {
        setResumeError(data.detail || "AI rewrite returned empty result.");
      }
    } catch (e) {
      setResumeError("AI section rewrite failed. Please try again.");
    } finally {
      setIsRewriting(false);
    }
  };

  const handleOpenCareerPortal = async () => {
    const targetUrl = job.url || job.apply_url || job.application_url;
    if (!targetUrl) {
      setApplicationStatus("No external application URL available");
      return;
    }
    // Register the application first (also checks for an earlier application to the same job).
    let result = await startApplication(job);
    if (result.status === 409 && result.data?.duplicate) {
      const when = result.data.existing?.applied_at ? new Date(result.data.existing.applied_at).toLocaleDateString() : "earlier";
      if (!window.confirm(`You already applied to this job through Cafy (${when}). Apply again anyway?`)) {
        setApplicationStatus("Already applied – duplicate prevented");
        return;
      }
      result = await startApplication(job, true);
    }
    if (!result.ok) {
      setApplicationStatus(result.data?.message || "Could not start the application");
      if (result.status === 422) return; // no résumé stored: autofill is not possible yet
    } else {
      setApplicationStatus(result.data.resumed ? "Resumed existing application" : "Application started – use the Cafy extension on the company page");
    }
    window.open(targetUrl, "_blank", "noopener,noreferrer");
  };

  const addSkill = (skill) => {
    const s = skill.trim();
    if (!s) return;
    setTailoredResume((prev) => {
      if (prev.skills.includes(s)) return prev;
      return { ...prev, skills: [...prev.skills, s] };
    });
    setDraftSaved(false);
  };

  const tabs = [
    { key: "overview", label: "Overview" },
    { key: "requirements", label: "Requirements" },
    { key: "company", label: "Company" },
    { key: "intelligence", label: "Job Intelligence" },
    { key: "application", label: "Application" },
  ];

  const summaryText = sanitizeDisplayText(job.description) || "No full description text available.";
  const requirementItems = [
    ...(job.matched_skills || []).slice(0, 6),
    ...(job.missing_skills || []).slice(0, 4),
  ];

  return (
    <div className={`modal-overlay ${fullPage ? "full-page-overlay" : "side-panel-overlay"}`} onClick={onClose}>
      <div
        className={`modal-card modal-drawer workflow-drawer ${fullPage ? "full-page-workspace" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Job Context Header matching resume-pipeline.jpeg Screen 3 */}
        <div className="drawer-header">
          <div className="workspace-header-row">
            <div className="workspace-header-main">
              <div className="workspace-company-avatar" title={job.company || "Company not listed"}>
                {(job.company || "?").charAt(0).toUpperCase()}
              </div>
              <div className="drawer-title-wrap">
                <h2 className="drawer-title" style={{ margin: 0, fontSize: "1.35rem" }}>{job.title}</h2>
                <div className="workspace-header-meta">
                  <span className="badge-location"><MapPin size={13} aria-hidden="true" /> {job.location || "Location not listed"}</span>
                  {job.visa_sponsored && (
                    <span className="badge-visa-sponsored" title="Employer is listed on the UK Sponsor Register for this UK location">
                      <Check size={13} aria-hidden="true" /> Visa Sponsored
                    </span>
                  )}
                  {job.employment_type && (
                    <span className="badge-work-type"><Briefcase size={13} aria-hidden="true" /> {job.employment_type}</span>
                  )}
                  {job.match_score > 0 && (
                    <span className="badge-match-pill">
                      <Check size={13} aria-hidden="true" /> {job.match_score}% match
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="workspace-header-actions" style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {!resumeOnly && (
                <button
                  type="button"
                  className="btn-job-details-toggle"
                  onClick={() => setActiveTab(activeTab === "application" ? "overview" : "application")}
                >
                  <Eye size={15} aria-hidden="true" /> {activeTab === "application" ? "Job Details" : "Resume Workspace"}
                </button>
              )}
              <button type="button" className="drawer-close-btn" onClick={onClose} aria-label="Close job drawer">
                ×
              </button>
            </div>
          </div>
        </div>

        {/* Drawer Tabs */}
        {!resumeOnly && (
          <div className="job-modal-tabs drawer-tabs" role="tablist" aria-label="Job details tabs">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={`job-modal-tab ${activeTab === tab.key ? "active" : ""}`}
                onClick={() => setActiveTab(tab.key)}
                role="tab"
                aria-selected={activeTab === tab.key}
              >
                {tab.label}
              </button>
            ))}
          </div>
        )}

        <div className="modal-body modal-body-tabs drawer-body">
          {/* TAB 1: OVERVIEW */}
          {activeTab === "overview" && (
            <div className="job-detail-panel">
              {job.match_score && (
                <div className="job-match-banner">
                  <div className="job-match-banner-top">
                    <strong>Match score: {job.match_score}%</strong>
                    <span>Based on your résumé</span>
                  </div>
                  <p>
                    <strong>Matching skills:</strong> {(job.matched_skills || []).join(", ") || "No overlapping skills listed"}
                  </p>
                  {job.missing_skills && job.missing_skills.length > 0 && (
                    <p>
                      <strong>Skills to highlight:</strong> {job.missing_skills.join(", ")}
                    </p>
                  )}
                </div>
              )}

              <div className="drawer-section-block">
                <h4 className="modal-section-heading">Overview</h4>
                <div className="overview-grid">
                  <div>
                    <span className="muted-label">Experience</span>
                    <strong>{job.experience_level || "Not listed"}</strong>
                  </div>
                  <div>
                    <span className="muted-label">Employment type</span>
                    <strong>{job.employment_type || "Not listed"}</strong>
                  </div>
                  <div>
                    <span className="muted-label">Location</span>
                    <strong>{job.location || "Location not listed"}</strong>
                  </div>
                  <div>
                    <span className="muted-label">Visa sponsorship</span>
                    <strong>{job.visa_sponsored ? "Visa Sponsored" : "Not listed"}</strong>
                  </div>
                </div>
              </div>

              <div className="drawer-section-block">
                <h4 className="modal-section-heading">Role description</h4>
                <div className="modal-job-description">{summaryText}</div>
              </div>
            </div>
          )}

          {/* TAB 2: REQUIREMENTS */}
          {activeTab === "requirements" && (
            <div className="job-detail-panel">
              <div className="drawer-section-block">
                <h4 className="modal-section-heading">Required & preferred skills</h4>
                {requirementItems.length === 0 && <p className="pipeline-desc">Role requirements not listed.</p>}
                <div className="skill-tag-list">
                  {requirementItems.map((item, index) => (
                    <span
                      key={`${item}-${index}`}
                      className={`skill-tag ${index < (job.matched_skills || []).length ? "matched" : "missing"}`}
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>

              <div className="drawer-section-block">
                <h4 className="modal-section-heading">Resume comparison</h4>
                <div className="resume-comparison-box">
                  <div className="compare-header-row">
                    <span>Your skills</span>
                    <span>Role needs</span>
                  </div>
                  <div className="compare-list">
                    {(job.matched_skills || []).slice(0, 6).map((skill) => (
                      <span className="compare-pill matched" key={skill}>
                        {skill}
                      </span>
                    ))}
                    {(job.missing_skills || []).slice(0, 6).map((skill) => (
                      <span className="compare-pill missing" key={skill}>
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB: JOB INTELLIGENCE (Pipeline 4) */}
          {activeTab === "intelligence" && <JobIntelligence key={job.id} job={job} />}

          {/* TAB 3: COMPANY */}
          {activeTab === "company" && (
            <div className="job-detail-panel">
              <div className="drawer-section-block">
                <h4 className="modal-section-heading">Company</h4>
                <p className="company-description">{getCompanySummary(job)}</p>
                {(() => {
                  return (
                    <div className="company-summary-box">
                      <div className="company-summary-row">
                        <span className="company-summary-label">Company</span>
                        <strong>{job.company || "Company not listed"}</strong>
                      </div>
                      <div className="company-summary-row">
                        <span className="company-summary-label">Industry</span>
                        <span>{job.industry || "Not listed"}</span>
                      </div>
                      <div className="company-summary-row">
                        <span className="company-summary-label">Location</span>
                        <span>{job.location || "Location not listed"}</span>
                      </div>
                      <div className="company-summary-row">
                        <span className="company-summary-label">Headquarters</span>
                        <span>{job.company_headquarters || "Not listed"}</span>
                      </div>
                      <div className="company-summary-row">
                        <span className="company-summary-label">Company size</span>
                        <span>{job.company_size || "Not listed"}</span>
                      </div>
                      <div className="company-summary-row">
                        <span className="company-summary-label">Website</span>
                        {job.company_website ? (
                          <a href={job.company_website} target="_blank" rel="noopener noreferrer">
                            {job.company_website}
                          </a>
                        ) : (
                          <span>Not listed</span>
                        )}
                      </div>
                    </div>
                  );
                })()}
              </div>
            </div>
          )}

          {/* TAB 4: APPLICATION & RESUME WORKSPACE */}
          {activeTab === "application" && (
            <div className="job-detail-panel" style={{ padding: "0 0 16px" }}>
              {/* Background tailoring status banner (resume generation handled on backend) */}
              {isGeneratingResume && (
                <div className="pipeline-generating-banner">
                  <span className="pipeline-spinner" />
                  <span>Tailoring resume in background…</span>
                </div>
              )}

              {/* If not yet ready and not generating */}
              {!resumeReady && !isGeneratingResume && (
                <div>
                  {resume && resumeOnly ? (
                    <>
                      <div className="pipeline-card tailor-setup">
                        <h3 className="tailor-setup-title">Tailor your resume</h3>
                        <label className="tailor-field">
                          <span>Base resume</span>
                          <input type="text" readOnly value={resume.filename || resume.candidate_name || "Uploaded resume"} />
                        </label>
                        <label className="tailor-field">
                          <span>Target job</span>
                          <input type="text" readOnly value={[job.title, job.company].filter(Boolean).join(" - ")} />
                        </label>
                        <label className="tailor-field">
                          <span>Job description {job.description ? "(retrieved from the job; edit if needed)" : "(paste it here)"}</span>
                          <textarea
                            rows={5}
                            value={tailorJobDescription}
                            onChange={(e) => setTailorJobDescription(e.target.value)}
                          />
                        </label>
                        <label className="tailor-field">
                          <span>Additional instructions (optional)</span>
                          <textarea
                            rows={2}
                            maxLength={500}
                            placeholder="e.g. Emphasise my Python and RAG experience"
                            value={additionalInstructions}
                            onChange={(e) => setAdditionalInstructions(e.target.value)}
                          />
                        </label>
                      </div>
                      <ApplicationAnalysis
                        job={job}
                        resume={resume}
                        onResumeUpdated={onUpdateResume}
                        onViewDetails={() => setActiveTab("requirements")}
                      />
                    </>
                  ) : resume ? (
                    <ApplicationAnalysis
                      job={job}
                      resume={resume}
                      onResumeUpdated={onUpdateResume}
                      onViewDetails={() => setActiveTab("requirements")}
                    />
                  ) : (
                    <div className="pipeline-card">
                      <p className="pipeline-desc">{resumeOnly ? "Upload a résumé to tailor it for this job." : "Upload a résumé to see your profile analysis for this job."}</p>
                    </div>
                  )}
                  {resumeError && <div className="pipeline-error" style={{ marginTop: 16 }}>{resumeError}</div>}
                  <div className="aa-generate-row">
                    <span className="pipeline-desc" style={{ margin: 0 }}>
                      Tailored strictly using facts from your uploaded profile.
                    </span>
                    <button
                      type="button"
                      className="pipeline-btn-primary"
                      onClick={handleGenerateResume}
                      disabled={isGeneratingResume}
                    >
                      {resumeOnly && resumeError ? "Try again" : "Generate Tailored Resume"}
                    </button>
                  </div>
                </div>
              )}

              {/* Once resumeReady: Full 4-tab review workspace */}
              {resumeReady && (
                <div>
                  {/* Workspace Sub-tabs matching resume-pipeline.jpeg Screen 3 & 4 */}
                  <div className="workspace-tabs-bar" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
                    <div className="workspace-tabs" role="tablist" aria-label="Resume workspace tabs" style={{ margin: 0 }}>
                      <button
                        type="button"
                        className={workspaceTab === "editor" ? "active" : ""}
                        onClick={() => setWorkspaceTab("editor")}
                        role="tab"
                        aria-selected={workspaceTab === "editor"}
                      >
                        Resume Editor
                      </button>
                      <button
                        type="button"
                        className={workspaceTab === "preview" ? "active" : ""}
                        onClick={() => setWorkspaceTab("preview")}
                        role="tab"
                        aria-selected={workspaceTab === "preview"}
                      >
                        Preview
                      </button>
                      <button
                        type="button"
                        className={workspaceTab === "suggestions" ? "active" : ""}
                        onClick={() => setWorkspaceTab("suggestions")}
                        role="tab"
                        aria-selected={workspaceTab === "suggestions"}
                      >
                        Suggestions
                      </button>
                    </div>
                  </div>

                  {resumeError && <div className="pipeline-error" style={{ marginBottom: 12 }}>{resumeError}</div>}

                  {/* SUBTAB: RESUME EDITOR (Desktop Split: Editor on Left, Live Preview on Right) */}
                  {workspaceTab === "editor" && (
                    <ResumeEditor
                      resume={tailoredResume}
                      setResume={setTailoredResume}
                      job={job}
                      apiBase={API_BASE}
                      generatedOutput={generatedOutput}
                      savedSnapshot={savedSnapshot}
                      isSaving={isSavingDraft}
                      onSave={handleSaveDraft}
                      isRewriting={isRewriting}
                      onImprove={handleRewriteSection}
                      onPdfReady={handlePdfReady}
                      scoring={editorScoring}
                      recommendedSkills={recommendedSkills}
                      fallbackPreview={
                        <ResumeDocumentPreview
                          resume={tailoredResume}
                          job={job}
                          resumeReady={resumeReady}
                          isGeneratingResume={isGeneratingResume}
                        />
                      }
                    />
                  )}

                  {/* SUBTAB: LIVE PREVIEW (Full width standalone) */}
                  {workspaceTab === "preview" && (
                    <div className="workspace-single-panel">
                      <ResumeDocumentPreview
                        resume={tailoredResume}
                        job={job}
                        resumeReady={resumeReady}
                        isGeneratingResume={isGeneratingResume}
                      />
                    </div>
                  )}

                  {/* SUBTAB: SUGGESTIONS */}
                  {workspaceTab === "suggestions" && (
                    <div className="workspace-single-panel">
                      <SuggestionsPanel
                        job={job}
                        resume={resume}
                        tailoredResume={tailoredResume}
                        onRewriteSummary={() => handleRewriteSection("professional_summary")}
                        isRewriting={isRewriting}
                      />
                    </div>
                  )}

                  {/* SUBTAB: CONTINUE TO APPLICATION */}
                  {workspaceTab === "scenarios" && (
                    <div className="scenarios-container">
                      <div className="scenarios-title-bar">
                        <div className="scenarios-heading">
                          <span className="scenario-badge-circle">5</span>
                          <div>
                            <h3>Continue to Application</h3>
                            <p style={{ margin: "2px 0 0", color: "#64748B", fontSize: "0.8rem" }}>
                              Select your preferred method to complete and submit your application with your tailored resume.
                            </p>
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                          <button
                            type="button"
                            className="btn-tracking-view"
                            onClick={() => {
                              if (!inPipeline) onTogglePipeline(job.id);
                              setApplicationStatus("In pipeline");
                            }}
                          >
                            {inPipeline ? "Tracked" : "Track Application"}
                          </button>
                          <button
                            type="button"
                            className="btn-mark-applied-hero"
                            onClick={() => {
                              if (!inPipeline) onTogglePipeline(job.id);
                              setApplicationStatus("Applied");
                              setSubmitted(true);
                            }}
                          >
                            <span><Check size={14} aria-hidden="true" /></span> {submitted ? "Marked as Applied" : "Mark as Applied"}
                          </button>
                        </div>
                      </div>

                      <div className="scenarios-grid">
                        <div className="scenario-card">
                          <div>
                            <div className="scenario-card-header">
                              <div className="scenario-number-row"><span className="scenario-step-num">1</span><span className="scenario-card-title">External Application Page (Most Common)</span></div>
                              <p className="scenario-card-subtitle">Opens the official application page with your resume ready.</p>
                            </div>
                            <div className="scenario-inner-box scenario-external-box">
                              <strong>{job.company || "Company careers"}</strong>
                              <p className="scenario-role-name">{job.title}</p>
                              <p className="scenario-role-loc">{job.location || "Location not listed"}{job.employment_type ? ` | ${job.employment_type}` : ""}</p>
                              <button type="button" className="btn-scenario-blue" onClick={handleOpenCareerPortal} disabled={!(job.url || job.apply_url || job.application_url)}>
                                Apply on {job.company || "company careers"} <ExternalLink size={13} aria-hidden="true" />
                              </button>
                            </div>
                          </div>
                        </div>

                        <div className="scenario-card">
                          <div>
                            <div className="scenario-card-header">
                              <div className="scenario-number-row"><span className="scenario-step-num" style={{ background: "#10B981" }}>2</span><span className="scenario-card-title">Supported Form Autofill (Where Available)</span></div>
                              <p className="scenario-card-subtitle">We pre-fill the application form using your profile information.</p>
                            </div>
                            <div className="scenario-inner-box">
                              <div className="scenario-pink-header">Application Form (Auto-filled)</div>
                              <div className="autofill-preview-form">
                                <label>Full Name<input value={resume?.candidate_name || resume?.name || ""} readOnly /></label>
                                <label>Email<input value={resume?.email || ""} readOnly /></label>
                                <label>Phone<input value={resume?.phone || ""} readOnly /></label>
                                <div className="autofill-resume-pill">Resume <span>Tailored resume.pdf</span></div>
                              </div>
                              <button type="button" className="btn-scenario-green" onClick={handleOpenCareerPortal} disabled={!(job.url || job.apply_url || job.application_url)}>Review &amp; Submit</button>
                            </div>
                          </div>
                        </div>

                        <div className="scenario-card">
                          <div>
                            <div className="scenario-card-header">
                              <div className="scenario-number-row"><span className="scenario-step-num">3</span><span className="scenario-card-title">Multi-step Application (Company Specific)</span></div>
                              <p className="scenario-card-subtitle">We guide you through each step with your information ready.</p>
                            </div>
                            <div className="scenario-inner-box">
                              <div className="multistep-scenario-list">
                                {["Personal Information", "Additional Questions", "Upload Documents", "Review & Submit"].map((step, index) => (
                                  <div className="multistep-scenario-item" key={step}><span><span className="step-num-badge">{index + 1}</span> {step}</span>{index < 2 && <Check size={13} color="#10B981" />}</div>
                                ))}
                              </div>
                              <button type="button" className="btn-scenario-blue">Continue to Next Step <ArrowRight size={13} aria-hidden="true" /></button>
                            </div>
                          </div>
                        </div>

                        <div className="scenario-card">
                          <div>
                            <div className="scenario-card-header">
                              <div className="scenario-number-row"><span className="scenario-step-num" style={{ background: "#BE123C" }}>4</span><span className="scenario-card-title">Manual Application (If Automation Not Possible)</span></div>
                              <p className="scenario-card-subtitle">Some companies require manual submission. We still make it easy.</p>
                            </div>
                            <div className="scenario-inner-box">
                              <div className="scenario-pink-header">Application Checklist</div>
                              <div className="manual-checklist-items">
                                <div className="manual-check-step"><span>① Download your tailored resume</span><span style={{ display: "flex", gap: 6 }}><button type="button" className="manual-mini-btn" onClick={() => handleDownloadResume("pdf")}>Download PDF</button><button type="button" className="manual-mini-btn" onClick={() => handleDownloadResume("docx")}>DOCX</button></span></div>
                                <div className="manual-check-step"><span>② Go to company application page</span><button type="button" className="manual-mini-btn" onClick={handleOpenCareerPortal} disabled={!(job.url || job.apply_url || job.application_url)}>Open Application Page <ExternalLink size={12} /></button></div>
                                <div className="manual-check-step"><span>③ Upload resume and fill details</span></div>
                                <div className="manual-check-step"><span>④ Submit your application</span></div>
                              </div>
                              <div className="scenario-yellow-note">We keep this page open with job details and your resume so you can complete the application easily.</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {rewriteResult && (
                    <div className="pipeline-card" data-testid="rewrite-result" style={{ marginTop: 16 }}>
                      <strong>Rewritten with AI and saved as a new version.</strong>
                      <p className="pipeline-desc" style={{ margin: "6px 0 0" }}>
                        {rewriteResult.rejectedLines === 0
                          ? "Every line was rewritten using only facts already in your resume."
                          : `${rewriteResult.rejectedLines} ${rewriteResult.rejectedLines === 1 ? "line was" : "lines were"} kept as written because the rewrite would have added new facts.`}
                      </p>
                      {rewriteResult.recommendedSkills.length > 0 && (
                        <div style={{ marginTop: 10 }}>
                          <span className="pipeline-desc">
                            This job also asks for these skills. They are not in your resume, so add one only if it is true for you:
                          </span>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                            {rewriteResult.recommendedSkills.map((skill) => (
                              <button
                                key={skill}
                                type="button"
                                className="btn-tool-draft"
                                disabled={existingSkillsLower.has(String(skill).toLowerCase())}
                                onClick={() => addSkill(skill)}
                              >
                                + {skill}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {/* Bottom actions keep the official application link next to the resume download. */}
                  <div className="workflow-output-row" style={{ marginTop: 24 }}>
                    <div className="editor-toolbar-actions" style={{ width: "100%" }}>
                      <button
                        type="button"
                        className="btn-tool-draft"
                        onClick={handleSaveDraft}
                        disabled={isSavingDraft}
                      >
                        <Save size={14} aria-hidden="true" /> {isSavingDraft ? "Saving…" : draftSaved ? "Draft Saved" : "Save Draft"}
                      </button>
                      <button
                        type="button"
                        className="btn-tool-ai"
                        onClick={handleRewriteFull}
                        disabled={isRewriting}
                        title="Rewrite the whole resume for this job and save it as a new version"
                      >
                        <Sparkles size={14} aria-hidden="true" /> {isRewriting ? "Rewriting…" : "Rewrite with AI"}
                      </button>
                      <button
                        type="button"
                        className="btn-tool-draft"
                        onClick={() => setWorkspaceTab("editor")}
                        title="Edit this resume in the built-in editor"
                      >
                        <PenLine size={14} aria-hidden="true" /> Edit Resume
                      </button>
                      <button
                        type="button"
                        className="btn-tool-draft"
                        onClick={() => handleDownloadResume("pdf")}
                      >
                        <Download size={14} aria-hidden="true" /> Download Resume
                      </button>
                      <button
                        type="button"
                        className="btn-continue-app"
                        onClick={handleOpenCareerPortal}
                        disabled={!(job.url || job.apply_url || job.application_url)}
                        title="Open the official job application page"
                      >
                        Continue to Application <ArrowRight size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer drawer-footer">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close
          </button>
          <button
            type="button"
            className="btn-primary-apply"
            onClick={() => {
              if (!inPipeline) onTogglePipeline(job.id);
              onClose();
            }}
          >
            {inPipeline ? "In pipeline" : "Add to pipeline"}
          </button>
        </div>
      </div>
    </div>
  );
}

function splitFilterTerms(value) {
  return value
    .split(",")
    .map((term) => term.trim().toLowerCase())
    .filter(Boolean);
}

function getJobSearchText(job) {
  return [
    job.title,
    job.company,
    job.location,
    job.department,
    job.description,
    ...(job.extracted_skills || [])
  ].filter(Boolean).join(" ").toLowerCase();
}

function getPostedDate(job) {
  const raw = job && job.posted_at;
  if (raw === null || raw === undefined || raw === "") return null;
  const text = String(raw).trim();

  // Epoch timestamps (Lever sends milliseconds)
  if (/^\d{10,13}$/.test(text)) {
    const n = Number(text);
    const d = new Date(text.length === 13 ? n : n * 1000);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  // Relative text such as Workday's "Posted Today", "Posted Yesterday", "Posted 3 Days Ago"
  if (/^posted\s+today/i.test(text)) return new Date();
  if (/^posted\s+yesterday/i.test(text)) return new Date(Date.now() - 24 * 60 * 60 * 1000);
  const relativeDate = text.match(/posted\s+(\d+)\+?\s+(hour|day|week|month)s?\s+ago/i);
  if (relativeDate) {
    const count = Number(relativeDate[1]);
    const unit = relativeDate[2].toLowerCase();
    const days = unit === "hour" ? 1 / 24 : unit === "week" ? 7 : unit === "month" ? 30 : 1;
    return new Date(Date.now() - count * days * 24 * 60 * 60 * 1000);
  }

  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function getSalaryAmounts(job) {
  const salaryLines = (job.description || "")
    .split(/\r?\n/)
    .filter((line) => (
      /\b(salary|compensation|pay range|base pay|remuneration|annual|per year|per annum)\b/i.test(line)
      && !/\b(hourly|per hour|an hour)\b/i.test(line)
    ));
  const text = salaryLines.join(" ");
  const currencyCodes = { "$": "USD", "£": "GBP", "€": "EUR" };
  const matches = text.matchAll(/(USD|CAD|GBP|EUR|INR|[$£€])\s*([\d,]+(?:\.\d+)?)\s*(k)?/gi);
  const amounts = [];

  for (const match of matches) {
    const currency = currencyCodes[match[1]] || match[1].toUpperCase();
    const amount = Number(match[2].replace(/,/g, "")) * (match[3] ? 1000 : 1);
    if (Number.isFinite(amount)) amounts.push({ currency, amount });
  }

  return amounts;
}

const EXPERIENCE_LEVELS = [
  ["entry", "Entry level"],
  ["graduate", "Graduate scheme"],
  ["junior", "Junior"],
  ["mid", "Mid-level"],
  ["senior", "Senior"],
];

// Level comes from the job title first (the strongest signal), then from the years of experience asked for.
function getExperienceLevel(job) {
  const title = job.title || "";
  if (/\b(graduate|grad scheme|new grad|early careers?|campus|trainee|school leaver|placement year)\b/i.test(title)) return "graduate";
  if (/\b(entry[- ]level|apprentice(ship)?|intern(ship)?|sales development|business development rep\w*|sdr|bdr|assistant|coordinator)\b/i.test(title)) return "entry";
  if (/\b(junior|jr\.?)(?!\w)/i.test(title)) return "junior";
  if (/\b(senior|sr\.?|lead|principal|staff|head of|director|vp|vice president|chief|architect|president)(?!\w)/i.test(title)) return "senior";
  if (/\b(mid[- ]?level|intermediate)\b/i.test(title)) return "mid";
  // The highest "N years of experience" in the posting is the real bar (a lone "2 years of X" is just one skill).
  const asks = [...(job.description || "").slice(0, 6000).matchAll(/(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs)(?:['’]s?)?\s*(?:of\s*)?(?:relevant\s*|professional\s*|commercial\s*|hands[- ]on\s*)*(?:experience|exp)/gi)]
    .map((m) => Number(m[1]))
    .filter((n) => n <= 15);
  if (asks.length) {
    const n = Math.max(...asks);
    return n <= 1 ? "entry" : n <= 2 ? "junior" : n <= 4 ? "mid" : "senior";
  }
  if (/\bmanager\b/i.test(title)) return "mid";
  return null;
}

function DirectoryView({
  jobs = [],
  matchedJobs = [],
  resume,
  platforms = [],
  pipelineJobIds = new Set(),
  onTogglePipeline,
  onAddAllToPipeline,
  onSelectJob,
  onRefresh
}) {
  const [filterQuery, setFilterQuery] = useState("");
  const [selectedCompany, setSelectedCompany] = useState("all");
  const [selectedLocation, setSelectedLocation] = useState("");
  const [selectedLevel, setSelectedLevel] = useState("all");
  const [selectedWorkMode, setSelectedWorkMode] = useState("all");
  const [selectedPostedWithin, setSelectedPostedWithin] = useState("any");
  const [sortBy, setSortBy] = useState("newest");
  const [activeJobId, setActiveJobId] = useState(null);
  const [discoverySubmitted, setDiscoverySubmitted] = useState(false);
  const [salaryError, setSalaryError] = useState("");
  const [discoveryFilters, setDiscoveryFilters] = useState({
    roles: "",
    location: "",
    postedWithin: "7",
    sources: ["greenhouse", "lever", "ashby", "workday", "workable", "oracle_cloud", "breezyhr", "pinpoint"],
    workModes: [],
    experienceLevel: "all",
    relocationAssistance: false,
    salaryMin: "",
    salaryMax: "",
    salaryCurrency: "USD",
    techStack: "",
    keywords: ""
  });
  const resultsRef = useRef(null);

  const updateDiscoveryFilter = (key, value) => {
    setDiscoveryFilters((current) => ({ ...current, [key]: value }));
  };

  const toggleDiscoveryOption = (key, value) => {
    setDiscoveryFilters((current) => {
      const selected = current[key];
      return {
        ...current,
        [key]: selected.includes(value)
          ? selected.filter((item) => item !== value)
          : [...selected, value]
      };
    });
  };

  const handleDiscoverySubmit = (event) => {
    event.preventDefault();
    if (
      discoveryFilters.salaryMin
      && discoveryFilters.salaryMax
      && Number(discoveryFilters.salaryMax) < Number(discoveryFilters.salaryMin)
    ) {
      setSalaryError("Maximum salary must be at least the minimum salary.");
      return;
    }
    setSalaryError("");
    setDiscoverySubmitted(true);
    requestAnimationFrame(() => resultsRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }));
  };

  // With a resume, show the backend's skill-ranked matches (it applies the score threshold).
  const sourcePool = useMemo(() => (resume ? matchedJobs || [] : jobs), [resume, matchedJobs, jobs]);

  // Extract unique companies from sourcePool
  const companiesList = useMemo(() => {
    const set = new Set();
    sourcePool.forEach((j) => {
      if (j.company) set.add(j.company);
    });
    return Array.from(set).sort();
  }, [sourcePool]);

  // Filtered jobs
  const filtered = useMemo(() => {
    return sourcePool.filter((j) => {
      if (!resume) {
        const jobText = getJobSearchText(j);
        const roles = splitFilterTerms(discoveryFilters.roles);
        if (roles.length && !roles.some((role) => (j.title || "").toLowerCase().includes(role))) {
          return false;
        }

        const locations = splitFilterTerms(discoveryFilters.location);
        if (locations.length && !locations.some((location) => (
          (j.location || "").toLowerCase().includes(location)
          || (location === "remote" && j.is_remote)
        ))) {
          return false;
        }

        if (
          discoveryFilters.postedWithin
          && discoveryFilters.postedWithin !== "any"
        ) {
          const postedDate = getPostedDate(j);
          const ageInDays = postedDate
            ? (Date.now() - postedDate.getTime()) / (24 * 60 * 60 * 1000)
            : Number.POSITIVE_INFINITY;
          if (postedDate && (ageInDays < 0 || ageInDays > Number(discoveryFilters.postedWithin))) {
            return false;
          }
        }

        if (!discoveryFilters.sources.includes((j.platform || "").toLowerCase())) {
          return false;
        }

        if (discoveryFilters.experienceLevel !== "all" && getExperienceLevel(j) !== discoveryFilters.experienceLevel) {
          return false;
        }


        if (discoveryFilters.workModes.length) {
          const isHybrid = /\bhybrid\b/i.test(jobText);
          const isRemote = j.is_remote || /\bremote\b/i.test(jobText);
          const isOnSite = /\b(on[- ]?site|in[- ]office|office[- ]based|in[- ]person)\b/i.test(jobText);
          if (
            !discoveryFilters.workModes.some((mode) => (
              mode === "Remote" ? isRemote : mode === "Hybrid" ? isHybrid : isOnSite
            ))
          ) {
            return false;
          }
        }

        if (
          discoveryFilters.relocationAssistance
          && !/\brelocation\s+(?:assistance|support|package|provided|available|offered)\b/i.test(jobText)
        ) {
          return false;
        }

        const salaryMin = Number(discoveryFilters.salaryMin);
        const salaryMax = Number(discoveryFilters.salaryMax);
        if (discoveryFilters.salaryMin || discoveryFilters.salaryMax) {
          const amounts = getSalaryAmounts(j).filter((salary) => (
            salary.currency === discoveryFilters.salaryCurrency
          ));
          if (!amounts.length) return false;
          const low = Math.min(...amounts.map((salary) => salary.amount));
          const high = Math.max(...amounts.map((salary) => salary.amount));
          if (
            (discoveryFilters.salaryMin && high < salaryMin)
            || (discoveryFilters.salaryMax && low > salaryMax)
          ) {
            return false;
          }
        }

        const techTerms = splitFilterTerms(discoveryFilters.techStack);
        if (techTerms.length && !techTerms.some((term) => jobText.includes(term))) {
          return false;
        }

        const keywords = splitFilterTerms(discoveryFilters.keywords);
        if (keywords.length && !keywords.every((term) => jobText.includes(term))) {
          return false;
        }
      }

      if (resume) {
        const jobText = getJobSearchText(j);
        const locationQuery = selectedLocation.trim().toLowerCase();
        if (
          locationQuery
          && !(j.location || "").toLowerCase().includes(locationQuery)
          && !(locationQuery === "remote" && j.is_remote)
        ) {
          return false;
        }

        if (selectedLevel !== "all" && getExperienceLevel(j) !== selectedLevel) {
          return false;
        }

        const isRemote = j.is_remote || /\bremote\b/i.test(jobText);
        const isHybrid = /\bhybrid\b/i.test(jobText);
        const isOnSite = /\b(on[- ]?site|in[- ]office|office[- ]based|in[- ]person)\b/i.test(jobText);
        if (
          (selectedWorkMode === "remote" && !isRemote)
          || (selectedWorkMode === "hybrid" && !isHybrid)
          || (selectedWorkMode === "on-site" && !isOnSite)
        ) {
          return false;
        }

        if (selectedPostedWithin !== "any") {
          const postedDate = getPostedDate(j);
          const ageInDays = postedDate
            ? (Date.now() - postedDate.getTime()) / (24 * 60 * 60 * 1000)
            : Number.POSITIVE_INFINITY;
          if (!postedDate || ageInDays < 0 || ageInDays > Number(selectedPostedWithin)) {
            return false;
          }
        }

      }

      // Company filter
      if (selectedCompany !== "all" && (j.company || "").toLowerCase() !== selectedCompany.toLowerCase()) {
        return false;
      }
      // Search query
      if (filterQuery) {
        const q = filterQuery.toLowerCase();
        const inTitle = (j.title || "").toLowerCase().includes(q);
        const inComp = (j.company || "").toLowerCase().includes(q);
        const inLoc = (j.location || "").toLowerCase().includes(q);
        const inSkills = (j.matched_skills || []).some((s) => s.toLowerCase().includes(q));
        if (!inTitle && !inComp && !inLoc && !inSkills) return false;
      }
      return true;
    });
  }, [
    sourcePool,
    selectedCompany,
    selectedLocation,
    selectedLevel,
    selectedWorkMode,
    selectedPostedWithin,
    filterQuery,
    resume,
    discoveryFilters
  ]);

  const visibleJobs = useMemo(() => {
    const list = [...filtered];
    if (sortBy === "newest") {
      // Newest first; jobs with no posting date go last, equal dates fall back to the better match.
      list.sort((a, b) => (getPostedDate(b)?.getTime() || 0) - (getPostedDate(a)?.getTime() || 0)
        || (Number(b.match_score) || 0) - (Number(a.match_score) || 0));
    } else if (sortBy === "company") {
      list.sort((a, b) => (a.company || "").localeCompare(b.company || ""));
    } else if (sortBy === "best") {
      list.sort((a, b) => (Number(b.match_score) || 0) - (Number(a.match_score) || 0));
    }
    return list;
  }, [filtered, sortBy]);

  const lastUpdated = useMemo(() => {
    const stamps = sourcePool.map((j) => Date.parse(j.last_checked || "")).filter(Number.isFinite);
    return stamps.length ? new Date(Math.max(...stamps)) : null;
  }, [sourcePool]);

  const stats = useMemo(() => {
    const scores = sourcePool.map((j) => Number(j.match_score)).filter((n) => Number.isFinite(n) && n > 0);
    const dayMs = 24 * 60 * 60 * 1000;
    return {
      total: sourcePool.length,
      today: sourcePool.filter((j) => { const d = getPostedDate(j); return d && Date.now() - d.getTime() <= dayMs; }).length,
      average: scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null,
      sponsors: sourcePool.filter((j) => j.visa_sponsored).length,
      top: scores.filter((n) => n >= 90).length,
    };
  }, [sourcePool]);

  const activeJob = useMemo(
    () => visibleJobs.find((j) => j.id === activeJobId) || visibleJobs[0] || null,
    [visibleJobs, activeJobId]
  );

  const filtersActive = Boolean(
    filterQuery || selectedLocation || selectedPostedWithin !== "any" || selectedCompany !== "all"
    || selectedLevel !== "all" || selectedWorkMode !== "all"
  );
  const clearFilters = () => {
    setFilterQuery("");
    setSelectedLocation("");
    setSelectedPostedWithin("any");
    setSelectedCompany("all");
    setSelectedLevel("all");
    setSelectedWorkMode("all");
  };

  const allVisibleInPipeline = useMemo(() => {
    if (filtered.length === 0) return false;
    return filtered.every((j) => pipelineJobIds.has(j.id));
  }, [filtered, pipelineJobIds]);

  return (
    <div className="content-container">
      {resume && (
        <>
          <header className="jd-page-header jd-page-header-row">
            <div>
              <h1>Job Discovery</h1>
              <p>Discover the best UK and Ireland opportunities tailored to your profile.</p>
            </div>
            <div className="jd-header-actions">
              {lastUpdated && (
                <span className="jd-updated">
                  Updated {lastUpdated.toLocaleString("en-GB", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                </span>
              )}
              <button type="button" className="jd-refresh" onClick={onRefresh}>
                <RefreshCw size={16} aria-hidden="true" /> Refresh jobs
              </button>
            </div>
          </header>
          <section className="jd-stats" aria-label="Job summary">
            {[
              [Briefcase, "blue", stats.total, "Matched opportunities", `${stats.today} posted in the last 24 hours`],
              [Target, "green", stats.average === null ? "–" : `${stats.average}%`, "Average match with your profile", "Across all matched jobs"],
              [Building2, "indigo", stats.sponsors, "Verified visa sponsors", "UK or Ireland, location confirmed"],
              [Star, "amber", stats.top, "Top matches", "90% match or higher"],
            ].map(([Icon, tone, value, label, note]) => (
              <div key={label} className="jd-stat">
                <span className={`jd-stat-icon ${tone}`} aria-hidden="true"><Icon size={24} /></span>
                <div>
                  <strong>{value}</strong>
                  <span>{label}</span>
                  <small>{note}</small>
                </div>
              </div>
            ))}
          </section>
        </>
      )}

      {!resume && (
        <>
          <div className="find-jobs-page-header">
            <div>
              <span className="hero-tag">PUBLIC JOB SEARCH</span>
              <h1 className="page-title">Find jobs</h1>
              <p className="page-subtitle">
                Filter the latest jobs already collected from selected ATS sources. Upload a résumé later for personalized matches.
              </p>
            </div>
          </div>

          <form className="job-discovery-form" onSubmit={handleDiscoverySubmit}>
            <div className="discovery-field">
              <label htmlFor="discovery-roles">Roles to Find</label>
              <input
                id="discovery-roles"
                type="text"
                value={discoveryFilters.roles}
                onChange={(event) => updateDiscoveryFilter("roles", event.target.value)}
                placeholder="Teacher, Accountant, Sales Executive, Hardware Engineer..."
              />
            </div>

            <div className="discovery-field">
              <label htmlFor="discovery-location">City or Location</label>
              <input
                id="discovery-location"
                type="text"
                value={discoveryFilters.location}
                onChange={(event) => updateDiscoveryFilter("location", event.target.value)}
                placeholder="London, New York, Remote..."
              />
            </div>

            <div className="discovery-row">
              <fieldset className="discovery-field discovery-choice-group">
                <legend>Posted Within</legend>
                <div className="discovery-options">
                  {[["1", "24h"], ["3", "3d"], ["7", "7d"], ["14", "14d"], ["30", "30d"], ["any", "Any"]].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className={`discovery-chip ${discoveryFilters.postedWithin === value ? "selected" : ""}`}
                      onClick={() => updateDiscoveryFilter("postedWithin", value)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </fieldset>

              <fieldset className="discovery-field discovery-choice-group">
                <legend>Sources</legend>
                <div className="discovery-options">
                  {[
                    ["greenhouse", "Greenhouse"],
                    ["lever", "Lever"],
                    ["ashby", "Ashby"],
                    ["workday", "Workday"],
                    ["workable", "Workable"],
                    ["oracle_cloud", "Oracle Cloud"],
                    ["breezyhr", "BreezyHR"],
                    ["pinpoint", "Pinpoint"]
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      aria-pressed={discoveryFilters.sources.includes(value)}
                      className={`discovery-chip ${discoveryFilters.sources.includes(value) ? "selected" : ""}`}
                      onClick={() => toggleDiscoveryOption("sources", value)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>

            <div className="discovery-row">
              <fieldset className="discovery-field discovery-choice-group">
                <legend>Work Mode</legend>
                <div className="discovery-options">
                  {["Remote", "Hybrid", "On-site"].map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      aria-pressed={discoveryFilters.workModes.includes(mode)}
                      className={`discovery-chip ${discoveryFilters.workModes.includes(mode) ? "selected" : ""}`}
                      onClick={() => toggleDiscoveryOption("workModes", mode)}
                    >
                      {mode}
                    </button>
                  ))}
                  <span className="discovery-hint">No selection shows all modes</span>
                </div>
              </fieldset>

              <fieldset className="discovery-field discovery-choice-group">
                <legend>Relocation</legend>
                <label className="discovery-checkbox">
                  <input
                    type="checkbox"
                    checked={discoveryFilters.relocationAssistance}
                    onChange={(event) => updateDiscoveryFilter("relocationAssistance", event.target.checked)}
                  />
                  <span>Only listings mentioning relocation assistance</span>
                </label>
              </fieldset>
            </div>

            <div className="discovery-row">
              <div className="discovery-field">
                <label>Salary (annual amount as listed)</label>
                <div className="salary-range-inputs">
                  <input
                    type="number"
                    min="0"
                    value={discoveryFilters.salaryMin}
                    onChange={(event) => {
                      setSalaryError("");
                      updateDiscoveryFilter("salaryMin", event.target.value);
                    }}
                    placeholder="Minimum"
                    aria-label="Minimum annual salary"
                  />
                  <span>to</span>
                  <input
                    type="number"
                    min="0"
                    value={discoveryFilters.salaryMax}
                    onChange={(event) => {
                      setSalaryError("");
                      updateDiscoveryFilter("salaryMax", event.target.value);
                    }}
                    placeholder="Maximum"
                    aria-label="Maximum annual salary"
                  />
                  <select
                    value={discoveryFilters.salaryCurrency}
                    onChange={(event) => updateDiscoveryFilter("salaryCurrency", event.target.value)}
                    aria-label="Salary currency"
                  >
                    {["USD", "GBP", "EUR", "CAD", "INR"].map((currency) => (
                      <option key={currency} value={currency}>{currency}</option>
                    ))}
                  </select>
                </div>
                <span className="discovery-hint">Only jobs whose description includes a matching currency amount are included. No currency conversion.</span>
                {salaryError && <span className="discovery-error" role="alert">{salaryError}</span>}
              </div>

              <div className="discovery-field">
                <label htmlFor="discovery-tech">Tech Stack</label>
                <input
                  id="discovery-tech"
                  type="text"
                  value={discoveryFilters.techStack}
                  onChange={(event) => updateDiscoveryFilter("techStack", event.target.value)}
                  placeholder="Python, React, AWS..."
                />
              </div>
            </div>

            <div className="discovery-row">
              <div className="discovery-field">
                <label htmlFor="discovery-level">Experience level</label>
                <select
                  id="discovery-level"
                  value={discoveryFilters.experienceLevel}
                  onChange={(event) => updateDiscoveryFilter("experienceLevel", event.target.value)}
                >
                  <option value="all">All levels</option>
                  {EXPERIENCE_LEVELS.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>

              <div className="discovery-field">
                <label htmlFor="discovery-keywords">Keywords</label>
                <input
                  id="discovery-keywords"
                  type="text"
                  value={discoveryFilters.keywords}
                  onChange={(event) => updateDiscoveryFilter("keywords", event.target.value)}
                  placeholder="Comma-separated terms that must all match..."
                />
              </div>
            </div>

            <div className="discovery-form-footer">
              <button type="submit" className="btn-discover-jobs">
                Show {filtered.length.toLocaleString()} matching jobs
              </button>
              <span className="discovery-hint">Search uses saved job listings; it does not start a live scrape.</span>
            </div>
          </form>
        </>
      )}

      {resume && (
        <>
          <div className="jd-filters">
            <label className="jd-field jd-search">
              <Search size={17} aria-hidden="true" />
              <input
                type="text"
                placeholder="Search roles, skills or company..."
                aria-label="Search roles, skills or company"
                value={filterQuery}
                onChange={(e) => setFilterQuery(e.target.value)}
              />
            </label>

            <label className="jd-field">
              <MapPin size={16} aria-hidden="true" />
              <span className="jd-field-body">
                <small>Location</small>
                <input
                  type="text"
                  placeholder="UK, Ireland"
                  aria-label="Filter by location"
                  value={selectedLocation}
                  onChange={(event) => setSelectedLocation(event.target.value)}
                />
              </span>
            </label>

            <label className="jd-field">
              <CalendarDays size={16} aria-hidden="true" />
              <span className="jd-field-body">
                <small>Posted within</small>
                <select aria-label="Posted Within" value={selectedPostedWithin} onChange={(event) => setSelectedPostedWithin(event.target.value)}>
                  <option value="any">Any time</option>
                  <option value="1">24 hours</option>
                  <option value="7">7 days</option>
                  <option value="14">14 days</option>
                  <option value="30">30 days</option>
                </select>
              </span>
              <ChevronDown size={15} className="jd-caret" aria-hidden="true" />
            </label>

            <label className="jd-field">
              <Building2 size={16} aria-hidden="true" />
              <span className="jd-field-body">
                <small>Company</small>
                <select aria-label="Filter by company" value={selectedCompany} onChange={(e) => setSelectedCompany(e.target.value)}>
                  <option value="all">All companies</option>
                  {companiesList.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </span>
              <ChevronDown size={15} className="jd-caret" aria-hidden="true" />
            </label>

            <label className="jd-field">
              <Briefcase size={16} aria-hidden="true" />
              <span className="jd-field-body">
                <small>Experience level</small>
                <select aria-label="Filter by experience level" value={selectedLevel} onChange={(event) => setSelectedLevel(event.target.value)}>
                  <option value="all">All levels</option>
                  {EXPERIENCE_LEVELS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </span>
              <ChevronDown size={15} className="jd-caret" aria-hidden="true" />
            </label>

            <label className="jd-field">
              <User size={16} aria-hidden="true" />
              <span className="jd-field-body">
                <small>Work mode</small>
                <select aria-label="Filter by work mode" value={selectedWorkMode} onChange={(event) => setSelectedWorkMode(event.target.value)}>
                  <option value="all">All modes</option>
                  <option value="remote">Remote</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="on-site">On-site</option>
                </select>
              </span>
              <ChevronDown size={15} className="jd-caret" aria-hidden="true" />
            </label>

            {filtersActive && (
              <button type="button" className="jd-clear" onClick={clearFilters}>Clear all filters</button>
            )}

            <label className="jd-sort">
              <span>Sort by</span>
              <select aria-label="Sort by" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                <option value="newest">Newest first</option>
                <option value="best">Best match</option>
                <option value="company">Company A–Z</option>
              </select>
            </label>
          </div>

        </>
      )}

      {/* Job list + selected job */}
      {(resume || discoverySubmitted) && (
        <div className="jd-split" ref={resultsRef}>
          <div className="jd-list-pane">
            <div className="jd-list-head">
              <h2>{visibleJobs.length} Job{visibleJobs.length === 1 ? "" : "s"} Found</h2>
              <button
                type="button"
                className="jd-addall"
                onClick={() => onAddAllToPipeline(visibleJobs)}
                disabled={visibleJobs.length === 0 || allVisibleInPipeline}
              >
                {allVisibleInPipeline ? "All saved" : "Save all"}
              </button>
            </div>
            {visibleJobs.length === 0 ? (
              <div className="empty-results-box">
                <h4>No roles match your filter criteria</h4>
                <p>Try clearing search keywords or filters.</p>
              </div>
            ) : (
              <ul className="jd-list">
                {visibleJobs.map((job) => (
                  <JobListItem
                    key={job.id}
                    job={job}
                    selected={activeJob?.id === job.id}
                    inPipeline={pipelineJobIds.has(job.id)}
                    onSelect={() => setActiveJobId(job.id)}
                    onTogglePipeline={() => onTogglePipeline(job.id)}
                  />
                ))}
              </ul>
            )}
          </div>
          {activeJob && (
            <JobDetailPane
              job={activeJob}
              inPipeline={pipelineJobIds.has(activeJob.id)}
              onTogglePipeline={() => onTogglePipeline(activeJob.id)}
              onOpenWorkspace={() => onSelectJob(activeJob)}
            />
          )}
        </div>
      )}
    </div>
  );
}

function CompaniesView({ platforms, onOpenAdd, onScrapePlatform }) {
  return (
    <div className="content-container">
      <div className="section-page-header">
        <div>
          <span className="hero-tag">ATS CONNECTOR CATALOG</span>
          <h1 className="page-title">Supported ATS Platforms & Companies</h1>
          <p className="page-subtitle">Public job-board APIs for the {platforms.length} configured applicant tracking systems.</p>
        </div>
        <button type="button" className="btn-choose-resume" onClick={onOpenAdd}>
          <span>+ Add Company to Scrape</span>
        </button>
      </div>

      <div className="platforms-grid">
        {platforms.map((p) => (
          <div key={p.id} className="platform-card">
            <div className="platform-card-header">
              <span className="platform-title" style={{ color: p.color }}>
                {p.name}
              </span>
              <span className="badge-pill">{p.stored_jobs_count || 0} Jobs Stored</span>
            </div>
            <p className="platform-desc">
              Configured company career boards: {p.companies_count || 0}
            </p>
            <div className="platform-companies-list">
              {(p.companies || []).map((c, i) => (
                <span key={i} className="company-pill">
                  {c}
                </span>
              ))}
            </div>
            <div className="platform-footer">
              <span style={{ fontSize: "0.76rem", color: "#64748B" }}>
                Status: {!p.status || p.status === "never_run" ? "Never run" : String(p.status).replace(/_/g, " ")}
              </span>
              <button
                type="button"
                className="btn-scrape-platform"
                onClick={() => onScrapePlatform(p.id)}
              >
                Scrape {p.name}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


// ==========================================================================
// PROFILE STRENGTH METER & PROFILE COMPLETION COMPONENTS
// ==========================================================================

function ProfileStrengthMeter({ resume, onUpdateResume, onUploadNew }) {
  const [showEditor, setShowEditor] = useState(false);
  const [editorInitialTab, setEditorInitialTab] = useState("skills");

  if (!resume) return null;

  // Only show scores the backend actually computed.
  const strength = resume.profile_strength;
  if (!strength) {
    return (
      <div className="profile-strength-card">
        <p className="profile-strength-desc">Profile score unavailable.</p>
      </div>
    );
  }

  const sections = strength.sections || {};
  const incompleteKeys = strength.incomplete_sections || [];
  const suggestions = strength.suggestions || [];
  const tierColor = strength.tier_badge_color || "blue";

  const openSectionEditor = (sectionKey) => {
    setEditorInitialTab(sectionKey);
    setShowEditor(true);
  };

  const sectionIconMap = {
    skills: Wrench,
    experience: Briefcase,
    education: GraduationCap,
    basics: User,
    projects: Rocket,
    certifications: ScrollText
  };

  return (
    <div className="profile-strength-container">
      {/* 1. HERO COMPLETENESS SCORE CARD */}
      <div className="profile-strength-hero-card">
        <div className="profile-strength-top-row">
          <div className="profile-score-badge-group">
            <div className={`profile-score-dial tier-${tierColor}`}>
              <span className="profile-score-number">{strength.overall_score}%</span>
              <span className="profile-score-label">COMPLETE</span>
            </div>
            <div className="profile-strength-meta">
              <div className="profile-strength-tier-row">
                <span className={`profile-tier-pill tier-${tierColor}`}>
                  {strength.strength_tier}
                </span>
                <span style={{ fontSize: "0.82rem", color: "var(--slate-500)", fontWeight: 600 }}>
                  ATS Readiness Meter
                </span>
              </div>
              <h2 className="profile-strength-headline">
                {strength.overall_score >= 88
                  ? "Your profile covers every section well."
                  : strength.overall_score >= 70
                    ? "Strong profile. A few sections could be filled in further."
                    : "Profile in progress. Complete the highlighted sections below."}
              </h2>
              <p className="profile-strength-desc">
                Evaluates Skills (25%), Work Experience (25%), Education (15%), Contact & Summary (15%), Projects (10%), and Certifications (10%).
              </p>
            </div>
          </div>

          <button
            type="button"
            className="btn-suggestion-action"
            style={{ padding: "10px 20px", fontSize: "0.88rem" }}
            onClick={() => openSectionEditor("skills")}
          >
            <Pencil size={14} aria-hidden="true" /> Edit & Boost Profile
          </button>
        </div>

        {/* Master Progress Bar */}
        <div className="profile-strength-progress-wrap">
          <div className="profile-strength-bar-bg">
            <div
              className={`profile-strength-bar-fill tier-${tierColor}`}
              style={{ width: `${strength.overall_score}%` }}
            />
          </div>
        </div>
      </div>

      {/* 2. INCOMPLETE SECTIONS ALERT BANNER */}
      {incompleteKeys.length > 0 && (
        <div className="profile-incomplete-banner">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <AlertTriangle size={20} color="#B45309" aria-hidden="true" />
            <div>
              <span style={{ fontSize: "0.86rem", fontWeight: 800, color: "#92400E" }}>
                Incomplete Sections ({incompleteKeys.length}):
              </span>
              <span style={{ fontSize: "0.84rem", color: "#B45309", marginLeft: "6px" }}>
                These sections are missing or below 75% completeness.
              </span>
            </div>
          </div>
          <div className="profile-incomplete-chips">
            {incompleteKeys.map((key) => {
              const sec = sections[key];
              if (!sec) return null;
              return (
                <button
                  key={key}
                  type="button"
                  className="incomplete-chip"
                  onClick={() => openSectionEditor(key)}
                >
                  + Add {sec.name} ({sec.score}%)
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* 3. SECTION-BY-SECTION COMPLETION CARDS */}
      <div>
        <h3 style={{ fontSize: "1.05rem", fontWeight: 800, color: "var(--slate-900)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
          <BarChart3 size={18} aria-hidden="true" />
          <span>Section-by-Section Breakdown</span>
        </h3>
        <div className="profile-sections-grid">
          {Object.entries(sections).map(([key, sec]) => {
            const SectionIcon = sectionIconMap[key] || FileText;
            const statusClass = `status-${sec.status || "incomplete"}`;
            const fillClass = sec.score >= 80 ? "tier-emerald" : sec.score >= 45 ? "tier-amber" : "tier-rose";

            return (
              <div key={key} className={`profile-section-card ${statusClass}`}>
                <div>
                  <div className="profile-section-header">
                    <div className="profile-section-title-wrap">
                      <span className="profile-section-icon"><SectionIcon size={18} aria-hidden="true" /></span>
                      <div>
                        <div className="profile-section-name">{sec.name}</div>
                        <div className="profile-section-weight">{sec.weight}% of score</div>
                      </div>
                    </div>
                    <span className={`profile-section-status-pill ${statusClass}`}>
                      {sec.status === "complete" ? <><Check size={12} aria-hidden="true" /> Complete</> : sec.status === "in_progress" ? <><Hourglass size={12} aria-hidden="true" /> In Progress</> : <><X size={12} aria-hidden="true" /> Missing</>}
                    </span>
                  </div>

                  <div className="profile-section-meter" style={{ marginTop: "14px" }}>
                    <div className="profile-section-meter-labels">
                      <span>Completeness</span>
                      <span className="profile-section-meter-percent">{sec.score}%</span>
                    </div>
                    <div className="profile-strength-bar-bg" style={{ height: "7px" }}>
                      <div
                        className={`profile-strength-bar-fill ${fillClass}`}
                        style={{ width: `${sec.score}%` }}
                      />
                    </div>
                  </div>

                  <div className="profile-section-details" style={{ marginTop: "10px" }}>
                    {sec.details}
                  </div>

                  {sec.gaps && sec.gaps.length > 0 && (
                    <div style={{ marginTop: "8px", fontSize: "0.76rem", color: "#B91C1C", background: "#FEF2F2", padding: "4px 8px", borderRadius: "6px" }}>
                      Tip: {sec.gaps[0]}
                    </div>
                  )}
                </div>

                <div className="profile-section-actions">
                  <button
                    type="button"
                    className="btn-section-edit"
                    onClick={() => openSectionEditor(key)}
                  >
                    {sec.score >= 80 ? "Edit" : "+ Complete"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 4. WHAT TO ADD NEXT: PRIORITIZED SUGGESTIONS */}
      {suggestions.length > 0 && (
        <div className="profile-suggestions-section">
          <div className="profile-suggestions-header">
            <div className="profile-suggestions-title">
              <span><Lightbulb size={16} aria-hidden="true" /> Suggestions to Maximize Profile Strength</span>
              <span className="badge-pill" style={{ background: "#EFF6FF", color: "#2563EB", border: "1px solid #BFDBFE" }}>
                {suggestions.length} recommendations
              </span>
            </div>
            <span style={{ fontSize: "0.80rem", color: "var(--slate-500)" }}>
              Ranked by impact on ATS visibility
            </span>
          </div>

          <div className="profile-suggestions-list">
            {suggestions.map((sug, i) => (
              <div key={sug.id || i} className="profile-suggestion-item">
                <div className="profile-suggestion-content">
                  <div className="profile-suggestion-meta-row">
                    <span className={`profile-suggestion-priority ${sug.priority || "medium"}`}>
                      {sug.priority || "medium"} priority
                    </span>
                    <span className="profile-suggestion-impact">
                      {sug.impact ? `Impact: ${sug.impact}` : null}
                    </span>
                  </div>
                  <div className="profile-suggestion-title-text">
                    {sug.title || "Improve section"}
                  </div>
                  <div className="profile-suggestion-desc">
                    {sug.text}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn-suggestion-action"
                  onClick={() => openSectionEditor(sug.section || "skills")}
                >
                  Add Now
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. INTERACTIVE PROFILE EDITOR MODAL */}
      {showEditor && (
        <ProfileEditorModal
          resume={resume}
          initialTab={editorInitialTab}
          onClose={() => setShowEditor(false)}
          onSaved={(updated) => {
            setShowEditor(false);
            if (onUpdateResume) onUpdateResume(updated);
          }}
        />
      )}
    </div>
  );
}

function ProfileEditorModal({ resume, initialTab = "skills", onClose, onSaved }) {
  const [tab, setTab] = useState(initialTab);
  const [saving, setSaving] = useState(false);

  // Form State
  const [skills, setSkills] = useState(resume.skills || []);
  const [newSkillInput, setNewSkillInput] = useState("");
  const [summary, setSummary] = useState(resume.summary || "");
  const [experience, setExperience] = useState(resume.experience || []);
  const [education, setEducation] = useState(resume.education || []);
  const [projects, setProjects] = useState(resume.projects || []);
  const [certifications, setCertifications] = useState(resume.certifications || []);
  const [linkedin, setLinkedin] = useState(resume.linkedin || "");
  const [github, setGithub] = useState(resume.github || "");
  const [portfolio, setPortfolio] = useState(resume.portfolio || "");
  const [phone, setPhone] = useState(resume.phone || "");

  // Skill Helpers
  const handleAddSkill = (skillToAdd) => {
    const trimmed = (skillToAdd || newSkillInput).trim();
    if (!trimmed) return;
    if (!skills.some((s) => s.toLowerCase() === trimmed.toLowerCase())) {
      setSkills((prev) => [...prev, trimmed]);
    }
    setNewSkillInput("");
  };

  const handleRemoveSkill = (skillToRemove) => {
    setSkills((prev) => prev.filter((s) => s !== skillToRemove));
  };

  // Add Item Helpers
  const handleAddExperience = () => {
    setExperience((prev) => [
      ...prev,
      {
        title: "",
        company: "",
        dates: "",
        bullets: []
      }
    ]);
  };

  const handleAddEducation = () => {
    setEducation((prev) => [
      ...prev,
      {
        degree: "",
        institution: "",
        dates: ""
      }
    ]);
  };

  const handleAddProject = () => {
    setProjects((prev) => [
      ...prev,
      {
        title: "",
        description: "",
        bullets: []
      }
    ]);
  };

  const handleAddCertification = () => {
    setCertifications((prev) => [
      ...prev,
      {
        name: "",
        issuer: "",
        dates: ""
      }
    ]);
  };

  const handleSave = async () => {
    setSaving(true);
    const payload = {
      skills,
      summary,
      experience,
      education,
      projects,
      certifications,
      linkedin,
      github,
      portfolio,
      phone
    };

    try {
      const res = await fetch(`${API_BASE}/api/resume/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        const data = await res.json();
        onSaved(data.resume);
      } else {
        // Fallback local update
        const updated = { ...resume, ...payload };
        onSaved(updated);
      }
    } catch (e) {
      console.error("Failed to save profile:", e);
      const updated = { ...resume, ...payload };
      onSaved(updated);
    } finally {
      setSaving(false);
    }
  };

  const popularSkills = [
    "Python", "JavaScript", "TypeScript", "React", "Node.js", "Docker", "Kubernetes",
    "AWS", "PostgreSQL", "FastAPI", "GraphQL", "CI/CD", "Terraform", "Git"
  ];

  return (
    <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 1200 }}>
      <div
        className="modal-container"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: "780px", maxHeight: "90vh", display: "flex", flexDirection: "column" }}
      >
        <div className="modal-header">
          <div>
            <span className="hero-tag">PROFILE ENHANCER</span>
            <h2 className="modal-title">Edit Profile & Boost Completeness</h2>
          </div>
          <button type="button" className="btn-modal-close" onClick={onClose}>
            <X size={14} aria-hidden="true" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div style={{ display: "flex", gap: "8px", borderBottom: "1px solid var(--slate-200)", padding: "0 24px", overflowX: "auto" }}>
          {[
            { id: "skills", label: "Skills", Icon: Wrench },
            { id: "experience", label: "Experience", Icon: Briefcase },
            { id: "education", label: "Education", Icon: GraduationCap },
            { id: "projects", label: "Projects", Icon: Rocket },
            { id: "certifications", label: "Certifications", Icon: ScrollText },
            { id: "basics", label: "Contact & Summary", Icon: User },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              style={{
                padding: "12px 14px",
                borderBottom: tab === t.id ? "3px solid var(--primary-blue)" : "3px solid transparent",
                fontWeight: tab === t.id ? 800 : 600,
                color: tab === t.id ? "var(--primary-blue)" : "var(--slate-600)",
                background: "transparent",
                borderTop: "none",
                borderLeft: "none",
                borderRight: "none",
                cursor: "pointer",
                whiteSpace: "nowrap"
              }}
            >
              <t.Icon size={14} aria-hidden="true" /> {t.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div style={{ padding: "24px", overflowY: "auto", flex: 1, display: "flex", flexDirection: "column", gap: "18px" }}>
          {/* TAB: SKILLS */}
          {tab === "skills" && (
            <div>
              <label style={{ display: "block", fontSize: "0.88rem", fontWeight: 700, color: "var(--slate-900)", marginBottom: "6px" }}>
                Technical Skills ({skills.length} listed)
              </label>
              <p style={{ fontSize: "0.82rem", color: "var(--slate-500)", marginBottom: "12px" }}>
                Add core languages, frameworks, cloud platforms, and engineering tools to maximize ATS job matching.
              </p>

              <div style={{ display: "flex", gap: "8px", marginBottom: "14px" }}>
                <input
                  type="text"
                  placeholder="Type a skill (e.g., PyTorch, GraphQL, Redis)..."
                  value={newSkillInput}
                  onChange={(e) => setNewSkillInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAddSkill(); } }}
                  style={{ flex: 1, padding: "8px 14px", border: "1px solid var(--slate-300)", borderRadius: "8px", fontSize: "0.9rem" }}
                />
                <button
                  type="button"
                  className="btn-suggestion-action"
                  onClick={() => handleAddSkill()}
                >
                  + Add Skill
                </button>
              </div>

              <div style={{ marginBottom: "12px" }}>
                <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--slate-600)", marginRight: "8px" }}>
                  Quick Suggestions:
                </span>
                <div style={{ display: "inline-flex", flexWrap: "wrap", gap: "6px", marginTop: "6px" }}>
                  {popularSkills.filter((ps) => !skills.some((s) => s.toLowerCase() === ps.toLowerCase())).slice(0, 8).map((ps) => (
                    <button
                      key={ps}
                      type="button"
                      onClick={() => handleAddSkill(ps)}
                      style={{
                        fontSize: "0.76rem",
                        padding: "3px 8px",
                        borderRadius: "999px",
                        background: "#F1F5F9",
                        border: "1px solid #CBD5E1",
                        color: "var(--slate-700)",
                        cursor: "pointer"
                      }}
                    >
                      + {ps}
                    </button>
                  ))}
                </div>
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", border: "1px solid var(--slate-200)", padding: "14px", borderRadius: "10px", background: "#F8FAFC", minHeight: "80px" }}>
                {skills.map((s, idx) => (
                  <span
                    key={idx}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      background: "#FFFFFF",
                      border: "1px solid var(--slate-300)",
                      padding: "4px 10px",
                      borderRadius: "999px",
                      fontSize: "0.82rem",
                      fontWeight: 600,
                      color: "var(--slate-800)"
                    }}
                  >
                    {s}
                    <button
                      type="button"
                      onClick={() => handleRemoveSkill(s)}
                      style={{ background: "none", border: "none", color: "#EF4444", cursor: "pointer", fontWeight: 800, fontSize: "0.85rem", padding: "0 2px" }}
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* TAB: EXPERIENCE */}
          {tab === "experience" && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <div>
                  <h4 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--slate-900)" }}>Work Experience ({experience.length})</h4>
                  <p style={{ fontSize: "0.82rem", color: "var(--slate-500)" }}>Include company, role, dates, and metric-backed achievements.</p>
                </div>
                <button type="button" className="btn-section-edit" onClick={handleAddExperience}>
                  + Add Role
                </button>
              </div>

              {experience.map((exp, idx) => (
                <div key={idx} style={{ background: "#F8FAFC", border: "1px solid var(--slate-200)", borderRadius: "10px", padding: "14px", marginBottom: "12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                    <span style={{ fontWeight: 800, fontSize: "0.85rem", color: "var(--slate-800)" }}>Role #{idx + 1}</span>
                    <button
                      type="button"
                      onClick={() => setExperience((prev) => prev.filter((_, i) => i !== idx))}
                      style={{ background: "none", border: "none", color: "#EF4444", cursor: "pointer", fontSize: "0.8rem", fontWeight: 700 }}
                    >
                      Remove
                    </button>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "8px" }}>
                    <input
                      type="text"
                      placeholder="Job Title (e.g. Accountant, Teacher, Sales Executive)"
                      value={exp.title || ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        setExperience((prev) => prev.map((item, i) => i === idx ? { ...item, title: val } : item));
                      }}
                      style={{ padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                    />
                    <input
                      type="text"
                      placeholder="Company Name"
                      value={exp.company || exp.organization || ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        setExperience((prev) => prev.map((item, i) => i === idx ? { ...item, company: val, organization: val } : item));
                      }}
                      style={{ padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                    />
                  </div>
                  <input
                    type="text"
                    placeholder="Dates (e.g. 2021 – Present)"
                    value={exp.dates || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setExperience((prev) => prev.map((item, i) => i === idx ? { ...item, dates: val } : item));
                    }}
                    style={{ width: "100%", padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem", marginBottom: "8px" }}
                  />
                  <textarea
                    rows={2}
                    placeholder="Key achievements with metrics (e.g. Scaled platform serving 50k users, reduced latency by 35%)"
                    value={Array.isArray(exp.bullets) ? exp.bullets.join("\n") : (exp.description || "")}
                    onChange={(e) => {
                      const lines = e.target.value.split("\n");
                      setExperience((prev) => prev.map((item, i) => i === idx ? { ...item, bullets: lines, description: e.target.value } : item));
                    }}
                    style={{ width: "100%", padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                  />
                </div>
              ))}
            </div>
          )}

          {/* TAB: EDUCATION */}
          {tab === "education" && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <div>
                  <h4 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--slate-900)" }}>Education ({education.length})</h4>
                  <p style={{ fontSize: "0.82rem", color: "var(--slate-500)" }}>Add your degree title, college/university, and graduation year.</p>
                </div>
                <button type="button" className="btn-section-edit" onClick={handleAddEducation}>
                  + Add Degree
                </button>
              </div>

              {education.map((edu, idx) => (
                <div key={idx} style={{ background: "#F8FAFC", border: "1px solid var(--slate-200)", borderRadius: "10px", padding: "14px", marginBottom: "12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                    <span style={{ fontWeight: 800, fontSize: "0.85rem", color: "var(--slate-800)" }}>Qualification #{idx + 1}</span>
                    <button
                      type="button"
                      onClick={() => setEducation((prev) => prev.filter((_, i) => i !== idx))}
                      style={{ background: "none", border: "none", color: "#EF4444", cursor: "pointer", fontSize: "0.8rem", fontWeight: 700 }}
                    >
                      Remove
                    </button>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "8px" }}>
                    <input
                      type="text"
                      placeholder="Degree (e.g. B.Sc. in Computer Science)"
                      value={edu.degree || edu.title || ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        setEducation((prev) => prev.map((item, i) => i === idx ? { ...item, degree: val, title: val } : item));
                      }}
                      style={{ padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                    />
                    <input
                      type="text"
                      placeholder="University / College Name"
                      value={edu.institution || edu.organization || ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        setEducation((prev) => prev.map((item, i) => i === idx ? { ...item, institution: val, organization: val } : item));
                      }}
                      style={{ padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                    />
                  </div>
                  <input
                    type="text"
                    placeholder="Graduation Year / Period (e.g. 2018 - 2022)"
                    value={edu.dates || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setEducation((prev) => prev.map((item, i) => i === idx ? { ...item, dates: val } : item));
                    }}
                    style={{ width: "100%", padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                  />
                </div>
              ))}
            </div>
          )}

          {/* TAB: PROJECTS */}
          {tab === "projects" && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <div>
                  <h4 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--slate-900)" }}>Technical Projects ({projects.length})</h4>
                  <p style={{ fontSize: "0.82rem", color: "var(--slate-500)" }}>Showcase personal, open-source, or academic software projects.</p>
                </div>
                <button type="button" className="btn-section-edit" onClick={handleAddProject}>
                  + Add Project
                </button>
              </div>

              {projects.map((proj, idx) => (
                <div key={idx} style={{ background: "#F8FAFC", border: "1px solid var(--slate-200)", borderRadius: "10px", padding: "14px", marginBottom: "12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                    <span style={{ fontWeight: 800, fontSize: "0.85rem", color: "var(--slate-800)" }}>Project #{idx + 1}</span>
                    <button
                      type="button"
                      onClick={() => setProjects((prev) => prev.filter((_, i) => i !== idx))}
                      style={{ background: "none", border: "none", color: "#EF4444", cursor: "pointer", fontSize: "0.8rem", fontWeight: 700 }}
                    >
                      Remove
                    </button>
                  </div>
                  <input
                    type="text"
                    placeholder="Project Title (e.g. Real-Time Chat Engine)"
                    value={proj.title || proj.name || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setProjects((prev) => prev.map((item, i) => i === idx ? { ...item, title: val, name: val } : item));
                    }}
                    style={{ width: "100%", padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem", marginBottom: "8px" }}
                  />
                  <textarea
                    rows={2}
                    placeholder="Description, tech stack, and key architecture (e.g. Built with Go, WebSockets, and Redis pub/sub)"
                    value={proj.description || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setProjects((prev) => prev.map((item, i) => i === idx ? { ...item, description: val } : item));
                    }}
                    style={{ width: "100%", padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                  />
                </div>
              ))}
            </div>
          )}

          {/* TAB: CERTIFICATIONS */}
          {tab === "certifications" && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <div>
                  <h4 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--slate-900)" }}>Certifications ({certifications.length})</h4>
                  <p style={{ fontSize: "0.82rem", color: "var(--slate-500)" }}>Add industry credentials (AWS, GCP, CKA, PMP, CompTIA, Scrum, etc.).</p>
                </div>
                <button type="button" className="btn-section-edit" onClick={handleAddCertification}>
                  + Add Certification
                </button>
              </div>

              {certifications.map((cert, idx) => (
                <div key={idx} style={{ background: "#F8FAFC", border: "1px solid var(--slate-200)", borderRadius: "10px", padding: "14px", marginBottom: "12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                    <span style={{ fontWeight: 800, fontSize: "0.85rem", color: "var(--slate-800)" }}>Certificate #{idx + 1}</span>
                    <button
                      type="button"
                      onClick={() => setCertifications((prev) => prev.filter((_, i) => i !== idx))}
                      style={{ background: "none", border: "none", color: "#EF4444", cursor: "pointer", fontSize: "0.8rem", fontWeight: 700 }}
                    >
                      Remove
                    </button>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "8px" }}>
                    <input
                      type="text"
                      placeholder="Certificate Name (e.g. AWS Solutions Architect)"
                      value={cert.name || cert.title || ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        setCertifications((prev) => prev.map((item, i) => i === idx ? { ...item, name: val, title: val } : item));
                      }}
                      style={{ padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                    />
                    <input
                      type="text"
                      placeholder="Issuer (e.g. Amazon Web Services)"
                      value={cert.issuer || ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        setCertifications((prev) => prev.map((item, i) => i === idx ? { ...item, issuer: val } : item));
                      }}
                      style={{ padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                    />
                  </div>
                  <input
                    type="text"
                    placeholder="Year / Date (e.g. 2023)"
                    value={cert.dates || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      setCertifications((prev) => prev.map((item, i) => i === idx ? { ...item, dates: val } : item));
                    }}
                    style={{ width: "100%", padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                  />
                </div>
              ))}
            </div>
          )}

          {/* TAB: BASICS & SUMMARY */}
          {tab === "basics" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 700, color: "var(--slate-900)", marginBottom: "4px" }}>
                  Professional Career Summary
                </label>
                <textarea
                  rows={3}
                  placeholder="2-3 sentence overview of your career focus, core stack, and impact..."
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  style={{ width: "100%", padding: "10px", border: "1px solid var(--slate-300)", borderRadius: "8px", fontSize: "0.88rem" }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 700, color: "var(--slate-800)", marginBottom: "4px" }}>
                    LinkedIn URL
                  </label>
                  <input
                    type="text"
                    placeholder="linkedin.com/in/username"
                    value={linkedin}
                    onChange={(e) => setLinkedin(e.target.value)}
                    style={{ width: "100%", padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 700, color: "var(--slate-800)", marginBottom: "4px" }}>
                    GitHub URL
                  </label>
                  <input
                    type="text"
                    placeholder="github.com/username"
                    value={github}
                    onChange={(e) => setGithub(e.target.value)}
                    style={{ width: "100%", padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                  />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 700, color: "var(--slate-800)", marginBottom: "4px" }}>
                    Portfolio / Website
                  </label>
                  <input
                    type="text"
                    placeholder="https://myportfolio.dev"
                    value={portfolio}
                    onChange={(e) => setPortfolio(e.target.value)}
                    style={{ width: "100%", padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 700, color: "var(--slate-800)", marginBottom: "4px" }}>
                    Phone Number
                  </label>
                  <input
                    type="text"
                    placeholder="+44 7700 900077"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    style={{ width: "100%", padding: "8px", border: "1px solid var(--slate-300)", borderRadius: "6px", fontSize: "0.85rem" }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="modal-footer" style={{ borderTop: "1px solid var(--slate-200)", padding: "16px 24px", display: "flex", justifyContent: "flex-end", gap: "10px" }}>
          <button type="button" className="btn-modal-close" onClick={onClose} style={{ padding: "8px 16px" }}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-suggestion-action"
            disabled={saving}
            onClick={handleSave}
            style={{ padding: "8px 24px" }}
          >
            {saving ? "Saving & Recalculating..." : "Save & Recalculate Score"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ResumeProfileView({ resume, onUploadNew, onUpdateResume }) {
  if (!resume) {
    return (
      <div className="content-container">
        <div className="empty-state-card">
          <p>No résumé uploaded yet. Upload one on the Home page to build your profile.</p>
        </div>
      </div>
    );
  }
  const displayResume = resume;

  return (
    <div className="content-container">
      <div className="section-page-header">
        <div>
          <span className="hero-tag">PROFILE STRENGTH & INSIGHTS</span>
          <h1 className="page-title">Candidate Profile & Strength</h1>
          <p className="page-subtitle">Track your ATS completeness score, evaluate gaps, and optimize for top employer matches.</p>
        </div>
        <button type="button" className="btn-choose-resume" onClick={onUploadNew}>
          <span>Upload New Résumé</span>
        </button>
      </div>

      {!resume && (
        <div style={{ background: "#EFF6FF", border: "1px solid #BFDBFE", borderRadius: "12px", padding: "14px 18px", marginBottom: "20px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <span style={{ fontWeight: 800, color: "#1D4ED8", fontSize: "0.9rem" }}><Info size={14} aria-hidden="true" /> Ready to start: </span>
            <span style={{ fontSize: "0.85rem", color: "#1E40AF" }}>Upload a résumé on the Home tab, or use the interactive editor below to build your profile and watch your strength score climb!</span>
          </div>
          <button type="button" className="btn-choose-resume" onClick={onUploadNew} style={{ padding: "6px 14px", fontSize: "0.82rem" }}>
            Upload Résumé (PDF/DOCX)
          </button>
        </div>
      )}

      {/* 1. PROFILE STRENGTH METER */}
      <ProfileStrengthMeter
        resume={displayResume}
        onUpdateResume={onUpdateResume}
        onUploadNew={onUploadNew}
      />

      {/* 2. PROFILE DETAILS CARD */}
      <div className="profile-card">
        <div className="profile-header-grid">
          <div className="profile-avatar-circle">
            {(displayResume.candidate_name || "U").charAt(0).toUpperCase()}
          </div>
          <div>
            <h2 style={{ fontSize: "1.6rem", fontWeight: 800, color: "#0F172A", marginBottom: "4px" }}>
              {displayResume.candidate_name}
            </h2>
            <p style={{ fontSize: "0.95rem", color: "#475569", marginBottom: "10px" }}>
              {[
                (displayResume.target_roles || []).join(" • "),
                displayResume.years_of_experience > 0
                  ? `${displayResume.years_of_experience}+ years experience`
                  : displayResume.seniority_level && displayResume.seniority_level !== "Unknown" ? displayResume.seniority_level : "",
              ].filter(Boolean).join(" • ")}
            </p>
            <div style={{ display: "flex", gap: "16px", fontSize: "0.84rem", color: "#64748B", flexWrap: "wrap" }}>
              {displayResume.email && <span><Mail size={13} aria-hidden="true" /> {displayResume.email}</span>}
              {displayResume.phone && <span><Phone size={13} aria-hidden="true" /> {displayResume.phone}</span>}
              {displayResume.linkedin && <span><Linkedin size={13} aria-hidden="true" /> {displayResume.linkedin}</span>}
              {displayResume.github && <span><Github size={13} aria-hidden="true" /> {displayResume.github}</span>}
            </div>
          </div>
        </div>

        <div style={{ borderTop: "1px solid #E2E8F0", paddingTop: "24px" }}>
          <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#0F172A", marginBottom: "16px" }}>
            Skills Taxonomy ({displayResume.skills ? displayResume.skills.length : 0} skills extracted)
          </h3>
          {Object.entries(displayResume.categorized_skills || {}).length > 0 ? (
            Object.entries(displayResume.categorized_skills || {}).map(([cat, sks]) => (
              <div key={cat} className="skill-category-block">
                <h4 className="category-name">
                  {cat} ({sks.length})
                </h4>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {sks.map((s, i) => (
                    <span key={i} className="skill-chip">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            ))
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {(displayResume.skills || []).map((s, i) => (
                <span key={i} className="skill-chip">
                  {s}
                </span>
              ))}
              {(!displayResume.skills || displayResume.skills.length === 0) && (
                <span style={{ fontSize: "0.85rem", color: "#64748B" }}>No skills listed yet. Click "Edit & Boost Profile" above to add your technical skills.</span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function InsightsView({ platforms = [] }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/stats`)
      .then((r) => {
        if (!r.ok) throw new Error(`Could not load statistics (${r.status})`);
        return r.json();
      })
      .then(setStats)
      .catch((err) => setError(err.message || "Could not load statistics."));
  }, []);

  if (error) return <div className="content-container"><div className="pipeline-error">{error}</div></div>;
  if (!stats) return <div className="content-container">Loading analytics...</div>;

  // A platform counts as active when it has jobs stored from a real scrape.
  const activePlatforms = platforms.filter((p) => (p.stored_jobs_count || 0) > 0);

  return (
    <div className="content-container">
      <h1 className="page-title">Job Market & Skill Insights</h1>
      <p className="page-subtitle">Stats from the jobs stored in the local database.</p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "20px", margin: "24px 0" }}>
        <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: "16px", padding: "24px" }}>
          <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#64748B" }}>TOTAL STORED LIVE JOBS</span>
          <h2 style={{ fontSize: "2.2rem", fontWeight: 800, color: "#2563EB", marginTop: "6px" }}>
            {stats.total_active_jobs}
          </h2>
          <p style={{ fontSize: "0.78rem", color: "#10B981", marginTop: "4px" }}><Check size={13} aria-hidden="true" /> Stored in local database</p>
        </div>

        <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: "16px", padding: "24px" }}>
          <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#64748B" }}>ACTIVE PLATFORMS</span>
          <h2 style={{ fontSize: "2.2rem", fontWeight: 800, color: "#0F172A", marginTop: "6px" }}>
            {activePlatforms.length} / {platforms.length}
          </h2>
          <p style={{ fontSize: "0.78rem", color: "#64748B", marginTop: "4px" }}>
            {activePlatforms.length > 0
              ? activePlatforms.map((p) => p.name || p.id).join(", ")
              : "No platform has stored jobs yet."}
          </p>
        </div>
      </div>

      <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: "16px", padding: "24px" }}>
        <h3 style={{ fontSize: "1.1rem", fontWeight: 800, color: "#0F172A", marginBottom: "16px" }}>
          Most In-Demand Skills Across Stored Jobs
        </h3>
        {(stats.top_skills || []).map((item, idx) => (
          <div
            key={idx}
            style={{
              display: "flex",
              justifyContent: "space-between",
              padding: "10px 0",
              borderBottom: "1px solid #F1F5F9"
            }}
          >
            <span style={{ fontWeight: 600, fontSize: "0.88rem", color: "#1E293B" }}>
              #{idx + 1} {item.skill}
            </span>
            <span className="badge-pill">{item.count} mentions</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SettingsView() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => {
        if (!r.ok) throw new Error(`Could not reach the backend (${r.status})`);
        return r.json();
      })
      .then(setHealth)
      .catch((err) => setError(err.message || "Could not reach the backend."));
  }, []);

  return (
    <div className="content-container">
      <h1 className="page-title">Settings</h1>
      <p className="page-subtitle">Current status of the Cafy Agent backend.</p>
      {error && <div className="pipeline-error">{error}</div>}
      {!health && !error && <p>Loading status...</p>}
      {health && (
        <div className="settings-card">
          <div className="setting-item">
            <div>
              <strong>Background Scraper Service</strong>
              <p>Scrapes all configured ATS platforms every 6 hours while the backend is running.</p>
            </div>
            <span className="badge-pill">{health.scheduler_active ? "Running" : "Stopped"}</span>
          </div>
          <div className="setting-item">
            <div>
              <strong>Supported ATS platforms</strong>
              <p>{health.total_active_jobs} jobs currently stored.</p>
            </div>
            <span className="badge-pill">{health.platforms_supported}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function AddCompanyModal({ onClose, onSuccess }) {
  const [platform, setPlatform] = useState("greenhouse");
  const [name, setName] = useState("");
  const [token, setToken] = useState("");
  const [host, setHost] = useState("");
  const [site, setSite] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("platform", platform);
      formData.append("name", name);
      formData.append("token", token);
      if (host) formData.append("host", host);
      if (site) formData.append("site", site);

      const res = await fetch(`${API_BASE}/api/companies/add`, {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        onSuccess();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card modal-sm" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Company to Scrape</h3>
          <button type="button" className="modal-close-btn" onClick={onClose}>
            &times;
          </button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body form-body">
          <div className="form-group">
            <label>ATS Platform</label>
            <select className="form-select" value={platform} onChange={(e) => setPlatform(e.target.value)}>
              <option value="greenhouse">Greenhouse (boards-api.greenhouse.io)</option>
              <option value="ashby">Ashby (api.ashbyhq.com)</option>
              <option value="lever">Lever (api.lever.co)</option>
              <option value="workday">Workday (*.myworkdayjobs.com)</option>
              <option value="workable">Workable (apply.workable.com)</option>
              <option value="oracle_cloud">Oracle Cloud HCM / CX</option>
              <option value="breezyhr">BreezyHR (*.breezy.hr)</option>
              <option value="pinpoint">Pinpoint (*.pinpointhq.com)</option>
            </select>
          </div>
          <div className="form-group">
            <label>Company Name</label>
            <input
              type="text"
              className="form-input"
              placeholder="e.g. Linear"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label>Board Token / Slug</label>
            <input
              type="text"
              className="form-input"
              placeholder="e.g. linear"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              required
            />
          </div>
          {platform === "workday" && (
            <div className="form-group">
              <label>Workday Host & Site</label>
              <input
                type="text"
                className="form-input"
                style={{ marginBottom: "8px" }}
                placeholder="e.g. nvidia.wd5.myworkdayjobs.com"
                value={host}
                onChange={(e) => setHost(e.target.value)}
              />
              <input
                type="text"
                className="form-input"
                placeholder="e.g. NVIDIAExternalCareerSite"
                value={site}
                onChange={(e) => setSite(e.target.value)}
              />
            </div>
          )}
          <div className="modal-footer pt-3">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary-apply" disabled={submitting}>
              {submitting ? "Adding..." : "Save & Scrape"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ApplicationTrackingView({
  pipelineJobIds,
  allJobs,
  onSelectJob,
}) {
  const [filter, setFilter] = useState("all");
  // Statuses the user sets here; every job starts as "In pipeline".
  const [statusMap, setStatusMap] = useState({});

  const STATUS_FLOW = ["In pipeline", "Applied", "Interview", "Rejected"];
  const pipelineJobs = allJobs.filter((j) => pipelineJobIds.has(j.id));
  const getStatus = (job) => statusMap[job.id] || STATUS_FLOW[0];
  const getStatusKey = (status) => status.toLowerCase().replace(/\s+/g, "_");

  const cycleStatus = (jobId) => {
    setStatusMap((prev) => {
      const current = prev[jobId] || STATUS_FLOW[0];
      return { ...prev, [jobId]: STATUS_FLOW[(STATUS_FLOW.indexOf(current) + 1) % STATUS_FLOW.length] };
    });
  };

  const tabs = [{ key: "all", label: "All" }, ...STATUS_FLOW.map((st) => ({ key: getStatusKey(st), label: st }))];
  const countFor = (key) =>
    key === "all" ? pipelineJobs.length : pipelineJobs.filter((j) => getStatusKey(getStatus(j)) === key).length;
  const filteredJobs = pipelineJobs.filter((j) => filter === "all" || getStatusKey(getStatus(j)) === filter);

  return (
    <div className="content-container">
      <div className="tracking-container" style={{ marginTop: 0 }}>
        <div className="tracking-title-bar">
          <div className="tracking-heading">
            <div>
              <h2 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 800, color: "#0F172A" }}>
                Application Tracking
              </h2>
              <p style={{ margin: "3px 0 0", color: "#64748B", fontSize: "0.85rem" }}>
                Jobs you added to your pipeline. Click a status to update it.
              </p>
            </div>
          </div>
        </div>

        <div className="tracking-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`tracking-tab-btn ${filter === tab.key ? "active" : ""}`}
              onClick={() => setFilter(tab.key)}
            >
              {tab.label} ({countFor(tab.key)})
            </button>
          ))}
        </div>

        <div className="tracking-cards-list">
          {filteredJobs.length === 0 ? (
            <div style={{ textAlign: "center", padding: "32px 16px", color: "#64748B" }}>
              {pipelineJobs.length === 0
                ? "No tracked applications yet. Add jobs to your pipeline from Find Jobs."
                : "No applications in this category."}
            </div>
          ) : (
            filteredJobs.map((job) => {
              const currentStatus = getStatus(job);
              return (
                <div key={job.id} className="tracking-card-item">
                  <div className="tracking-item-left">
                    <div className="tracking-item-avatar" style={{ fontWeight: 800 }}>
                      {(job.company || "?").charAt(0).toUpperCase()}
                    </div>
                    <div className="tracking-item-details">
                      <strong>{job.title}</strong>
                      <span>{job.company || "Company not listed"} · {job.location || "Location not listed"}</span>
                    </div>
                  </div>
                  <div className="tracking-item-right">
                    <button
                      type="button"
                      className={`tracking-status-pill ${getStatusKey(currentStatus)}`}
                      style={{ cursor: "pointer", border: "none" }}
                      title="Click to change status"
                      onClick={() => cycleStatus(job.id)}
                    >
                      {currentStatus} <ChevronDown size={12} aria-hidden="true" />
                    </button>
                    <button type="button" className="btn-tracking-view" onClick={() => onSelectJob(job)}>
                      View
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

export { DirectoryView, JobDetailModal, ApplicationTrackingView, ProfileStrengthMeter, ResumeProfileView };
export default App;

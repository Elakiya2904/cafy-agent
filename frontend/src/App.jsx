/**
 * Main React application for Cafy Agent's job, resume, and career workflows.
 * Composes page navigation, job search, application tracking, and career tools.
 */
// ==========================================================================
// CAFY AGENT • REACT APPLICATION
// ==========================================================================

import { withToken } from "./auth.js";
import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import logo from "./logo.png";
import { SidebarAccount } from "./AuthGate.jsx";
import {
  tailoredResumeToProfile,
  useJobMatchAnalysis,
} from "./JobMatchScore.jsx";
import ApplicationAnalysis from "./ApplicationAnalysis.jsx";
import ResumeEditor from "./ResumeEditor.jsx";
import TailorResumeScreen from "./TailorResumeScreen.jsx";
import ResumeVersionHistory from "./ResumeVersionHistory.jsx";
import DataExport from "./DataExport.jsx";
import EmailAgentDashboard from "./EmailAgentDashboard.jsx";
import MyApplications, { startApplication } from "./MyApplications.jsx";
import JobIntelligence from "./JobIntelligence.jsx";
import JobFilterPanel, { EMPTY_JOB_FILTERS, LEVEL_BANDS, getEmploymentType } from "./JobFilterPanel.jsx";
import { dedupeEntries, renderSections, sameRecord } from "./resumeSections.js";
import MatchBreakdown from "./MatchBreakdown.jsx";
import "./analytics.css";
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
  Trash2,
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

const ACTIVE_TAB_STORAGE_KEY = "cafy-agent-active-tab";
const APP_TABS = new Set([
  "home",
  "find-jobs",
  "job-alerts",
  "my-applications",
  "resume",
  "files",
  "follow-ups",
  "insights",
  "settings",
]);

function getInitialActiveTab() {
  if (typeof window === "undefined") return "home";
  const savedTab = window.sessionStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
  return APP_TABS.has(savedTab) ? savedTab : "home";
}

function App() {
  // Navigation & View State
  const [activeTab, setActiveTab] = useState(getInitialActiveTab);
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
  // Set when the workspace was opened with "Create resume", which starts generation at once.
  const [createOnOpen, setCreateOnOpen] = useState(false);
  const openJobForResume = useCallback((job) => { setCreateOnOpen(true); setSelectedJob(job); }, []);
  const openJob = useCallback((job) => { setCreateOnOpen(false); setSelectedJob(job); }, []);
  const [showAddCompanyModal, setShowAddCompanyModal] = useState(false);

  // Toasts & Pipeline State
  const [toasts, setToasts] = useState([]);
  const [pipelineJobIds, setPipelineJobIds] = useState(new Set());
  const fileInputRef = useRef(null);

  useEffect(() => {
    window.sessionStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTab);
  }, [activeTab]);

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
  }, [loadPlatformsAndJobs]);

  useEffect(() => {
    let active = true;
    fetch(`${API_BASE}/api/resume/current`)
      .then(async (response) => {
        if (!response.ok) throw new Error(`Could not load saved résumé (${response.status}).`);
        return response.json();
      })
      .then((data) => {
        if (!active) return;
        setCurrentResume(data.resume || null);
        setMatchedJobs(data.matched_jobs || []);
        setCurrentStep(data.resume ? 3 : 1);
      })
      .catch((error) => {
        console.error("Failed to load saved résumé", error);
      });
    return () => {
      active = false;
    };
  }, []);

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

  const handleRemoveResume = async () => {
    if (!window.confirm("Remove your saved résumé and uploaded file?")) return;

    try {
      const response = await fetch(`${API_BASE}/api/resume`, { method: "DELETE" });
      if (!response.ok) {
        throw new Error(`Remove failed (${response.status})`);
      }

      setCurrentResume(null);
      setMatchedJobs([]);
      setCurrentStep(1);
      showToast("Résumé removed.");
    } catch (error) {
      console.error("Failed to remove saved résumé", error);
      showToast(`Could not remove résumé: ${error.message}`);
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
            onSelectJob={openJobForResume}
            onRefresh={loadPlatformsAndJobs}
            onRemoveResume={handleRemoveResume}
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
        {activeTab === "my-applications" && (
          <ApplicationTrackingView
            pipelineJobIds={pipelineJobIds}
            allJobs={allJobs}
            onSelectJob={openJob}
            onCustomizeResume={openJobForResume}
            resume={currentResume}
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
          key={selectedJob.id}
          job={selectedJob}
          resume={currentResume}
          onUpdateResume={setCurrentResume}
          inPipeline={pipelineJobIds.has(selectedJob.id)}
          onTogglePipeline={() => togglePipeline(selectedJob.id)}
          onClose={() => setSelectedJob(null)}
          fullPage
          resumeOnly
          autoGenerate={createOnOpen}
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
      id: "home", label: "Home", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
          <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
          <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
          <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
        </svg>
      )
    },
    {
      section: "Discover", id: "find-jobs", label: "Find Jobs", badge: hasResume ? highMatchCount : totalJobsCount, icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
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
      section: "Apply", label: "Applied To", id: "my-applications", badge: pipelineCount > 0 ? pipelineCount : undefined, icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M9 11l3 3L22 4"></path>
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
        </svg>
      )
    },
    {
      id: "resume", label: "My Resumes", hasDot: hasResume, icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
        </svg>
      )
    },
    {
      id: "files", label: "My Files", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
        </svg>
      )
    },
    {
      section: "Follow Up", id: "follow-ups", label: "Email Agent", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
      )
    },
    {
      section: "Other", id: "insights", label: "Analytics", icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="18" y1="20" x2="18" y2="10"></line>
          <line x1="12" y1="20" x2="12" y2="4"></line>
          <line x1="6" y1="20" x2="6" y2="14"></line>
        </svg>
      )
    },
    {
      section: "Settings", id: "settings", label: "Account", icon: (
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
          <img src={logo} alt="" />
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

      <SidebarAccount />
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
      title: "Employment permit employer · Ireland",
      detail: total
        ? `Issued ${total.toLocaleString()} Irish employment permit${total === 1 ? "" : "s"} in ${years.join("–")}.`
        : "Listed in Ireland's employment permit data.",
      note: "Ireland has no sponsor licence register. Confirm sponsorship for this role with the employer.",
    };
  }
  if (job.visa_sponsored) {
    const legalName = job.visa_sponsor_registered_names?.[0];
    return {
      tone: "ok",
      title: "Licensed UK visa sponsor",
      detail: `Listed on the Home Office Register of Licensed Sponsors${legalName ? ` as ${legalName}` : ""}. UK-based role.`,
      note: "A sponsor licence doesn't guarantee this role offers sponsorship. Check the advert or ask the recruiter.",
    };
  }
  if (inIreland) {
    return job.visa_sponsor_registered
      ? {
        tone: "warn",
        title: "Sponsorship not confirmed",
        detail: "The employer is a UK sponsor but isn't in Ireland's employment permit data for this Ireland-based role.",
      }
      : {
        tone: "none",
        title: "No sponsorship record",
        detail: "The employer isn't in Ireland's employment permit data or the UK sponsor register.",
      };
  }
  if (job.visa_sponsor_registered) {
    return {
      tone: "warn",
      title: "Licensed sponsor · location unconfirmed",
      detail: job.visa_sponsor_location_status === "NON_UK"
        ? "The employer holds a UK sponsor licence, but this role is based outside the UK."
        : "The employer holds a UK sponsor licence, but this role's UK location isn't confirmed.",
    };
  }
  return {
    tone: "none",
    title: "Not on the sponsor register",
    detail: "This employer isn't on the Home Office Register of Licensed Sponsors, so it can't sponsor a Skilled Worker visa.",
  };
}

function matchTone(score) {
  return score >= 85 ? "high" : score >= 70 ? "mid" : "low";
}

// Turns a posting's HTML into plain blocks (heading / paragraph / bullet) so it can be shown without injecting HTML.
// Older Workday imports stored "Position: <title> at <company>. Location: <place>." instead of a description.
const PLACEHOLDER_DESCRIPTION = /^\s*Position:\s.+\sat\s.+?\.(\s*Location:\s.+\.)?\s*$/;

function parseJobDescription(raw) {
  if (!raw || PLACEHOLDER_DESCRIPTION.test(raw)) return [];
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

// Memoised: selecting a job or saving one re-renders only the rows whose props changed.
const JobListItem = React.memo(function JobListItem({ job, selected, inPipeline, onSelect, onTogglePipeline }) {
  const postingAge = formatJobAge(job.posted_at || job.created_at);
  const score = Number(job.match_score);
  const hasMatchScore = job.match_score !== null && job.match_score !== undefined && Number.isFinite(score);
  const level = EXPERIENCE_LEVELS.find(([value]) => value === getExperienceLevel(job));
  return (
    <li className={`jd-item ${selected ? "selected" : ""}`}>
      <div
        className="jd-item-main"
        role="button"
        tabIndex={0}
        aria-pressed={selected}
        onClick={() => onSelect(job.id)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(job.id); } }}
      >
        <div className="jd-item-body">
          <div className="jd-item-company">
            <span className="jd-logo"><CompanyBrandLogo company={job.company} /></span>
            <span>{job.company || "Company not listed"}</span>
            {postingAge && <span className="jd-item-age"><Clock size={11} aria-hidden="true" /> {postingAge}</span>}
          </div>
          <div className="jd-item-top">
            <h3>{job.title}</h3>
            {hasMatchScore && <span className={`jd-match ${matchTone(score)}`} title="Job match based on your saved profile">{Math.round(score)}% Match</span>}
          </div>
          <div className="jd-item-tags">
            {job.employment_type && <span>{job.employment_type}</span>}
            {level && <span>{level[1]}</span>}
            {job.location && <span>{job.location}</span>}
            {job.visa_sponsored && <span className="visa">Visa Sponsorship</span>}
          </div>
        </div>
      </div>
      <button
        type="button"
        className={`jd-bookmark jd-item-bookmark ${inPipeline ? "saved" : ""}`}
        onClick={() => onTogglePipeline(job.id)}
        aria-label={inPipeline ? `Remove ${job.title} from pipeline` : `Save ${job.title} to pipeline`}
        aria-pressed={inPipeline}
      >
        <Bookmark size={17} fill={inPipeline ? "currentColor" : "none"} aria-hidden="true" />
      </button>
    </li>
  );
});

function JobDetailPane({ job, onCreateResume }) {
  const [tab, setTab] = useState("about");
  const [company, setCompany] = useState({ jobId: null, data: null, error: "" });
  useEffect(() => { setTab("about"); }, [job?.id]);
  // Company research is fetched the first time the Company Info tab is opened for a job.
  useEffect(() => {
    if (tab !== "about" || !job?.id || company.jobId === job.id) return undefined;
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
  const hasMatchScore = job.match_score !== null && job.match_score !== undefined && Number.isFinite(score);
  const level = EXPERIENCE_LEVELS.find(([value]) => value === getExperienceLevel(job));
  const salary = formatSalaryRange(job);
  const mode = getJobWorkMode(job);
  const visa = getVisaState(job);
  const co = company.jobId === job.id ? company.data : null;
  const companyLoading = tab === "about" && company.jobId === job.id && !co && !company.error;
  const companyRows = [
    ["Industry", co?.industry || job.industry],
    ["Headquarters", co?.headquarters || job.company_headquarters],
    ["Company size", co?.company_size || job.company_size],
    ["Careers page", co?.career_page],
    ["UK hiring locations", co?.operating_locations?.length ? co.operating_locations.join(" · ") : ""],
  ].filter(([, value]) => value);
  const companyOverview = co?.overview || (job.company_description ? sanitizeDisplayText(job.company_description) : "");
  const companyWebsite = co?.official_website || job.company_website || job.website;
  const companyLinkedIn = co?.linkedin_url || job.company_linkedin || job.linkedin_url;
  const applyUrl = job.url;

  return (
    <section className="jd-detail" aria-label={`${job.title} at ${job.company}`}>
      <header className="jd-detail-head">
        <div className="jd-detail-title">
          <h2>{job.title}</h2>
          {job.industry && <p className="jd-detail-category">{job.industry}</p>}
          <div className="jd-detail-company">
            <span className="jd-logo"><CompanyBrandLogo company={job.company} /></span>
            <span>{job.company || "Company not listed"}</span>
            {job.location && <><span className="jd-dot">•</span><MapPin size={14} aria-hidden="true" /><span>{job.location}</span></>}
          </div>
        </div>
        {hasMatchScore && <span className={`jd-match big ${matchTone(score)}`} title="Job match based on your saved profile">{Math.round(score)}% Job Match</span>}
      </header>

      <div className="jd-tabs" role="tablist">
        {[["about", "Company details"], ["job-info", "Job info"], ["intelligence", "Job Intelligence"]].map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{label}</button>
        ))}
        <button type="button" className="jd-tailor-btn" onClick={onCreateResume}>
          <FileText size={15} aria-hidden="true" /> Create resume
        </button>
      </div>

      <div className="jd-tab-body">
        {tab === "about" && (
          <>
            <div className={`jd-sponsor-callout ${visa.tone}`} role="note" aria-label="Visa sponsorship">
              <strong>{visa.title}</strong>
              <span>{visa.detail}</span>
              {visa.note && <small>{visa.note}</small>}
            </div>
            <h3 className="jd-about-company">{job.company || "About this employer"}</h3>
            {(companyWebsite || companyLinkedIn) && (
              <div className="jd-company-links">
                {companyWebsite && <a href={companyWebsite} target="_blank" rel="noopener noreferrer"><Globe size={14} aria-hidden="true" /> Website <ExternalLink size={12} aria-hidden="true" /></a>}
                {companyLinkedIn && <a href={companyLinkedIn} target="_blank" rel="noopener noreferrer"><Linkedin size={14} aria-hidden="true" /> LinkedIn <ExternalLink size={12} aria-hidden="true" /></a>}
              </div>
            )}
            {companyLoading && <p className="jd-muted"><Loader2 size={14} className="doc-spin" aria-hidden="true" /> Researching {job.company}…</p>}
            {company.error && <p className="jd-muted">{company.error}</p>}
            {companyOverview && <p>{companyOverview}</p>}
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
          </>
        )}

        {tab === "job-info" && (
          <>
              <div className="jd-detail-chips">
                {job.employment_type && <span>{job.employment_type}</span>}
                {level && <span>{level[1]}</span>}
                {mode && <span>{mode}</span>}
                {salary && <span>{salary}</span>}
                {postingAge && <span className="muted"><Clock size={13} aria-hidden="true" /> Posted {postingAge}</span>}
              </div>
              {blocks.length === 0 && (
                <p className="jd-muted">
                  The full description is on the employer's site.
                  {applyUrl && <> <a href={applyUrl} target="_blank" rel="noopener noreferrer">Read the full job advert <ExternalLink size={12} aria-hidden="true" /></a></>}
                </p>
              )}
              {blocks.map((b, i) => (
                b.type === "h" ? <h4 key={i}>{b.text}</h4>
                  : b.type === "li" ? <p key={i} className="jd-li"><CheckCircle2 size={15} aria-hidden="true" /><span>{b.text}</span></p>
                    : <p key={i}>{b.text}</p>
              ))}
          </>
        )}

        {tab === "intelligence" && <JobIntelligence key={job.id} job={job} />}
      </div>

      {applyUrl && (
        <div className="jd-detail-footer">
          <a className="jd-apply-btn" href={applyUrl} target="_blank" rel="noopener noreferrer">
            Apply now <ExternalLink size={15} aria-hidden="true" />
          </a>
        </div>
      )}
    </section>
  );
}

export function normalizeClientResume(raw, masterResume, job) {
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
        entries = entries.split(/\r?\n/).filter(Boolean);
      }
    }
    if (!Array.isArray(entries)) return [];
    return entries
      .map((entry) => {
        if (typeof entry === "string") {
          const text = entry.trim();
          return text ? { title: text, name: text, description: "", bullets: [], organization: "", dates: "", location: "" } : null;
        }
        if (!entry || typeof entry !== "object") return null;
        const title = String(entry.title || entry.role || entry.name || entry.degree || "").trim();
        const org = String(
          entry.organization || entry.company || entry.institution || entry.school ||
          entry.venue || entry.publisher || entry.conference || entry.issuer || ""
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

  // The summary is kept whole; length is a matter for the writer, not something to cut silently.
  const finalSummary = [
    raw.professional_summary,
    raw.summary,
    masterResume?.professional_summary,
    masterResume?.summary,
  ]
    .map((summary) => String(summary || "").trim())
    .find(Boolean) || "";

  // A saved tailored resume's own sections win, even when empty (the user removed them);
  // only a section the saved copy does not have at all falls back to the master profile.
  const entriesFrom = (key) => {
    const saved = raw[key];
    if (Array.isArray(saved)) return saved;
    if (saved) return saved;
    return masterResume?.[key] || [];
  };

  // Every entry and bullet is kept: no count limits and no merging of internships into work
  // experience. A long resume runs onto a second page. Repeated records are merged once.
  const internships = dedupeEntries(parseEntries(entriesFrom("internships"), "internships"), "internships");
  const exps = dedupeEntries(parseEntries(entriesFrom("experience"), "experience"), "experience")
    .filter((e) => !internships.some((intern) => sameRecord(intern, e, "internships")));
  const projs = dedupeEntries(parseEntries(entriesFrom("projects"), "projects"), "projects");
  const publications = dedupeEntries(parseEntries(entriesFrom("publications"), "publications"), "publications");
  const achievements = dedupeEntries(parseEntries(entriesFrom("achievements"), "achievements"), "achievements");
  const edus = dedupeEntries(parseEntries(entriesFrom("education"), "education"), "education");
  const certs = dedupeEntries(parseEntries(entriesFrom("certifications"), "certifications"), "certifications");
  const skillsList = rawSkills.length || Array.isArray(raw.skills) ? rawSkills : masterSkills;

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
    internships,
    projects: projs,
    publications,
    achievements,
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
          {/* Sections, order and entry lines are shared with the PDF, DOCX and LaTeX exports.
              UK template: a rule before every section; "Organisation | dates" then the bold role. */}
          {renderSections(resume).map((section) => (
            <div className="paper-section" key={section.key}>
              <hr className="paper-section-hr" />
              <div className="paper-section-title">{section.title}</div>
              {section.kind === "text" && (
                <p className="paper-summary" style={{ textAlign: "justify" }}>{section.text}</p>
              )}
              {section.kind === "skills" && (
                <ul className="paper-skill-columns">
                  {section.skills.map((skill, i) => <li key={i}>{skill}</li>)}
                </ul>
              )}
              {section.kind === "entries" && section.entries.map((entry, idx) => (
                <div className="paper-entry" key={`${section.key}-${idx}`} style={{ marginBottom: 10 }}>
                  {entry.meta && <div className="paper-entry-org">{entry.meta}</div>}
                  {entry.heading && <div className="paper-entry-role">{entry.heading}</div>}
                  {entry.description && <p className="paper-summary"><LinkifiedText text={entry.description} /></p>}
                  {entry.bullets.length > 0 && (
                    <ul className="paper-bullets">
                      {entry.bullets.map((b, bIdx) => (
                        <li key={`${section.key}-${idx}-b-${bIdx}`}><LinkifiedText text={b} /></li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          ))}
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

function GenerationScoresBanner({ scores }) {
  if (!scores || scores.job_match_score === undefined) return null;
  const items = [
    { label: "Job Match", score: scores.job_match_score, tip: scores.explanations?.job_match },
    { label: "Skills Match", score: scores.skills_match_score, tip: scores.explanations?.skills_match },
    { label: "ATS Readiness", score: scores.ats_score, tip: scores.explanations?.ats },
    { label: "Content Quality", score: scores.content_quality_score, tip: scores.explanations?.content_quality },
  ].filter(item => item.score !== undefined && item.score !== null);

  const color = (s) => s >= 75 ? "#059669" : s >= 50 ? "#d97706" : "#dc2626";
  const bg    = (s) => s >= 75 ? "#ecfdf5" : s >= 50 ? "#fffbeb" : "#fef2f2";
  const border= (s) => s >= 75 ? "#a7f3d0" : s >= 50 ? "#fde68a" : "#fecaca";

  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${items.length}, 1fr)`, gap: 8, marginBottom: 14 }}>
      {items.map(({ label, score, tip }) => (
        <div
          key={label}
          title={tip || ""}
          style={{
            background: bg(score), border: `1px solid ${border(score)}`,
            borderRadius: 10, padding: "10px 12px", textAlign: "center", cursor: tip ? "help" : "default",
          }}
        >
          <div style={{ fontSize: "1.25rem", fontWeight: 800, color: color(score), lineHeight: 1 }}>{score}%</div>
          <div style={{ fontSize: "0.68rem", fontWeight: 700, color: color(score), marginTop: 3, textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</div>
        </div>
      ))}
    </div>
  );
}

function JobDetailModal({ job, onClose, resume, onUpdateResume, onTogglePipeline, inPipeline, fullPage = false, resumeOnly = false, autoGenerate = false }) {
  const [activeTab, setActiveTab] = useState("application");
  const [workspaceTab, setWorkspaceTab] = useState("editor");
  const drawerBodyRef = useRef(null);
  // Resume-only mode starts on the Tailor screen; a saved resume for this job (or a fresh
  // generation) opens the editor. "Regenerate" returns to the Tailor screen.
  const [editorOpen, setEditorOpen] = useState(!resumeOnly);
  // True once we know whether this job already has a saved tailored resume.
  const [savedChecked, setSavedChecked] = useState(false);
  const autoStarted = useRef(false);
  const [isGeneratingResume, setIsGeneratingResume] = useState(false);
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [isRewriting, setIsRewriting] = useState(false);
  const [resumeError, setResumeError] = useState("");
  const [resumeReady, setResumeReady] = useState(false);
  const [applicationStatus, setApplicationStatus] = useState("Not started");
  const [draftSaved, setDraftSaved] = useState(false);
  const [generatedOutput, setGeneratedOutput] = useState(null);
  // Start downloading the PDF renderer now, so the preview is ready when the editor opens.
  useEffect(() => {
    if (resumeOnly) import("./PdfPreview.jsx").catch(() => {});
  }, [resumeOnly]);
  const [tailoredResume, setTailoredResume] = useState(() => normalizeClientResume({}, resume, job));
  // Last generated/saved version, used by the editor's Reset button.
  const [savedSnapshot, setSavedSnapshot] = useState(null);
  // Outcome of the last full "Rewrite with AI": lines kept unchanged + skills to consider adding.
  const [rewriteResult, setRewriteResult] = useState(null);
  // Scores returned by the last generation run.
  const [generationScores, setGenerationScores] = useState(null);
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
    resumeReady && workspaceTab !== "scenarios" ? job.id : null,
    editorProfile,
    600,
    tailorJobDescription
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
            setEditorOpen(true);
            setApplicationStatus("Tailored resume ready");
          }
        }
      } catch (e) {
        // Fall back to clean initial state
      } finally {
        if (!isCancelled) setSavedChecked(true);
      }
    }
    loadSavedResume();
    return () => {
      isCancelled = true;
    };
  }, [job?.id]);

  const handleGenerateResume = async () => {
    if (!resume) {
      setResumeError("Upload a résumé on the Home page before creating a tailored version.");
      return;
    }
    if (isGeneratingResume) return;

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
      setGenerationScores(data.generation_scores || null);
      setTailoredResume(normalized);
      setSavedSnapshot(normalized);
      setResumeReady(true);
      setApplicationStatus("Tailored resume ready");
      setDraftSaved(false);
      // Go straight to the editor — no section-by-section approval step.
      setActiveTab("application");
      setWorkspaceTab("editor");
      setEditorOpen(true);
      drawerBodyRef.current?.scrollTo?.({ top: 0 });
    } catch (error) {
      setResumeError(error.message || "Resume generation failed. Please retry.");
      setApplicationStatus("Generation failed");
    } finally {
      setIsGeneratingResume(false);
    }
  };

  // "Create resume" opens this screen and starts generating straight away, unless this job
  // already has a saved tailored resume (then the editor opens with it instead).
  useEffect(() => {
    if (!autoGenerate || !savedChecked || resumeReady || autoStarted.current) return;
    autoStarted.current = true;
    handleGenerateResume();
  }, [autoGenerate, savedChecked, resumeReady]); // eslint-disable-line react-hooks/exhaustive-deps

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
      const data = await resp.json().catch(() => ({}));
      if (resp.ok) {
        // Keep the editor's own copy: the server's normalised copy would reset the caret mid-edit.
        const { resume: _serverCopy, ...urls } = data;
        setGeneratedOutput((prev) => ({ ...prev, ...urls }));
        setSavedSnapshot(tailoredResume);
        setDraftSaved(true);
        setResumeError("");
        setApplicationStatus("Draft saved");
        setTimeout(() => setDraftSaved(false), 3000);
      } else {
        setResumeError(typeof data.detail === "string" ? data.detail : `Could not save your changes (${resp.status}).`);
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
      } else if (sectionKey === "education" && itemIndex !== null) {
        const education = tailoredResume.education[itemIndex] || {};
        content = education.description || [
          education.degree || education.title,
          education.institution || education.organization,
          education.dates,
          education.location,
        ].filter(Boolean).join(" — ");
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
          improvement_goals: (editorScoring.analysis?.suggestions || [])
            .filter((item) => {
              const section = sectionKey === "professional_summary" ? "summary" : sectionKey;
              return item.section === section;
            })
            .map((item) => item.text)
            .filter(Boolean)
            .slice(0, 8),
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
        } else if (sectionKey === "education" && itemIndex !== null) {
          setTailoredResume((prev) => {
            const list = [...(prev.education || [])];
            list[itemIndex] = { ...list[itemIndex], description: data.rewritten };
            return { ...prev, education: list };
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
      if (result.status === 422) return; // no résumé stored yet, so there is nothing to apply with
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
  const showWorkspace = resumeReady && editorOpen;
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
        {/* Compact workspace header matching the resume editor reference. */}
        <div className="drawer-header workspace-compact-header">
          <div className="workspace-compact-breadcrumb">
            <span className="workspace-compact-icon" aria-hidden="true">▣</span>
            <span>/ Resumes /</span>
            <strong>{resume?.personal_info?.name || resume?.candidate_name || "Resume"}</strong>
            <span>— {job.title}</span>
            {showWorkspace && <span className="workspace-compact-status"><Check size={12} aria-hidden="true" /> Autosaved</span>}
          </div>
          <div className="workspace-compact-context">
            {job.location && <span><MapPin size={12} aria-hidden="true" /> {job.location}</span>}
            {job.visa_sponsored && <span className="badge-visa-sponsored"><Check size={12} aria-hidden="true" /> Visa Sponsored</span>}
            {job.match_score > 0 && <span className="badge-match-pill"><Check size={12} aria-hidden="true" /> {job.match_score}% match</span>}
          </div>
          <div className="workspace-header-actions" style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {resumeOnly && showWorkspace && (
                <button type="button" className="btn-job-details-toggle" onClick={() => setEditorOpen(false)}>
                  <RefreshCw size={15} aria-hidden="true" /> Regenerate
                </button>
              )}
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

        <div className="modal-body modal-body-tabs drawer-body" ref={drawerBodyRef}>
          {/* TAB 1: OVERVIEW */}
          {activeTab === "overview" && (
            <div className="job-detail-panel">
              {job.match_score !== null && job.match_score !== undefined && Number.isFinite(Number(job.match_score)) && (
                <div className="job-match-banner">
                  <div className="job-match-banner-top">
                    <strong>Job Match: {Math.round(Number(job.match_score))}%</strong>
                    <span>Based on your saved profile and this job description</span>
                  </div>
                  <p>
                    <strong>Matching skills:</strong> {(job.matched_skills || []).join(", ") || "No overlapping skills listed"}
                  </p>
                  {job.missing_skills && job.missing_skills.length > 0 && (
                    <p>
                      <strong>Skills to highlight:</strong> {job.missing_skills.join(", ")}
                    </p>
                  )}
                  <MatchBreakdown breakdown={job.match_breakdown} />
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
              {resumeOnly && !showWorkspace && (
                <TailorResumeScreen
                  job={job}
                  resume={resume}
                  tailorJobDescription={tailorJobDescription}
                  setTailorJobDescription={setTailorJobDescription}
                  additionalInstructions={additionalInstructions}
                  setAdditionalInstructions={setAdditionalInstructions}
                  isGenerating={isGeneratingResume}
                  onGenerate={handleGenerateResume}
                  error={resumeError}
                  hasExisting={resumeReady}
                  onBackToEditor={resumeReady ? () => setEditorOpen(true) : undefined}
                />
              )}
              {!resumeOnly && !showWorkspace && <div className="application-job-context">
                <div>
                  <span className="application-context-label">Selected job</span>
                  <h3>{job.title}</h3>
                  <p>{job.company || "Company not listed"} · {job.location || "Location not listed"}</p>
                </div>
                <div className="application-context-description">
                  <span className="application-context-label">Job description</span>
                  <p>{summaryText}</p>
                </div>
              </div>}
              {/* Background tailoring status banner (resume generation handled on backend) */}
              {!resumeOnly && isGeneratingResume && (
                <div className="pipeline-generating-banner">
                  <span className="pipeline-spinner" />
                  <span>Tailoring resume in background…</span>
                </div>
              )}

              {/* Step 1: review the job, then generate. The editor opens only after this. */}
              {!resumeOnly && !showWorkspace && !isGeneratingResume && (
                <div>
                  {resume ? (
                    <ApplicationAnalysis
                      job={job}
                      resume={resume}
                      onResumeUpdated={onUpdateResume}
                      onViewDetails={() => setActiveTab("requirements")}
                    />
                  ) : (
                    <div className="pipeline-card">
                      <p className="pipeline-desc">Upload a résumé to see your profile analysis for this job.</p>
                    </div>
                  )}
                  {resumeError && <div className="pipeline-error" style={{ marginTop: 16 }}>{resumeError}</div>}
                  <div className="aa-generate-row">
                    <span style={{ display: "flex", gap: 8 }}>
                      <button
                        type="button"
                        className="pipeline-btn-primary"
                        onClick={handleGenerateResume}
                        disabled={isGeneratingResume}
                      >
                        {resumeReady ? "Regenerate Tailored Resume" : "Generate Tailored Resume"}
                      </button>
                    </span>
                  </div>
                </div>
              )}

              {/* After generation: Resume Editor / Preview / ATS workspace */}
              {showWorkspace && (
                <div>
                  {resumeError && <div className="pipeline-error" style={{ marginBottom: 12 }}>{resumeError}</div>}

                  {/* Generation scores banner */}
                  {generationScores && generationScores.job_match_score !== undefined && (
                    <GenerationScoresBanner scores={generationScores} />
                  )}

                  {/* The editor owns its workspace tabs so switching views preserves the live draft. */}
                  {workspaceTab !== "scenarios" && (
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
                      workspaceTab={workspaceTab}
                      onWorkspaceTab={setWorkspaceTab}
                      onApply={job.url || job.apply_url || job.application_url ? handleOpenCareerPortal : undefined}
                      scoring={editorScoring}
                      recommendedSkills={recommendedSkills}
                    />
                  )}

                  {/* SUBTAB: SUGGESTIONS */}
                  {workspaceTab === "ats" && (
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

function isUkCountryTerm(value) {
  return /^(?:u\.?k\.?|united kingdom|great britain|britain|england|scotland|wales|northern ireland)$/i
    .test(value.trim());
}

// Per-job derived values are cached: filtering and sorting thousands of jobs would otherwise
// re-run these regexes on every keystroke in the filter panel.
const LIST_PAGE_SIZE = 60;
function cachedBy(fn) {
  const cache = new WeakMap();
  return (job) => {
    if (!job || typeof job !== "object") return fn(job);
    if (!cache.has(job)) cache.set(job, fn(job));
    return cache.get(job);
  };
}

const getJobSearchText = cachedBy((job) => {
  return [
    job.title,
    job.company,
    job.location,
    job.department,
    job.description,
    ...(job.extracted_skills || [])
  ].filter(Boolean).join(" ").toLowerCase();
});

const getPostedDate = cachedBy((job) => {
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
});

const getSalaryAmounts = cachedBy((job) => {
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
});

const EXPERIENCE_LEVELS = [
  ["entry", "Entry level"],
  ["graduate", "Graduate scheme"],
  ["junior", "Junior"],
  ["mid", "Mid-level"],
  ["senior", "Senior"],
];

// Level comes from the job title first (the strongest signal), then from the years of experience asked for.
const getExperienceLevel = cachedBy((job) => {
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
});

function DirectoryView({
  jobs = [],
  matchedJobs = [],
  resume,
  platforms = [],
  pipelineJobIds = new Set(),
  onTogglePipeline,
  onAddAllToPipeline,
  onSelectJob,
  onRefresh,
  onRemoveResume = () => {}
}) {
  const [jobFilters, setJobFilters] = useState(EMPTY_JOB_FILTERS);
  const [sortBy, setSortBy] = useState("newest");
  const [activeJobId, setActiveJobId] = useState(null);

  // With a resume, show the backend's skill-ranked matches (it applies the score threshold).
  const sourcePool = useMemo(() => (resume ? matchedJobs || [] : jobs), [resume, matchedJobs, jobs]);

  // Salary distribution (mid-point of each job's listed pay) in the chosen currency.
  const salaryStats = useMemo(() => {
    const values = [];
    sourcePool.forEach((j) => {
      const amounts = getSalaryAmounts(j)
        .filter((s) => s.currency === jobFilters.currency && s.amount >= 1000)
        .map((s) => s.amount);
      if (amounts.length) values.push((Math.min(...amounts) + Math.max(...amounts)) / 2);
    });
    values.sort((a, b) => a - b);
    if (!values.length) return { values, bins: [] };
    // Trim the outer 5% so a single outlier does not flatten the chart.
    const lo = values[Math.floor(values.length * 0.05)];
    const hi = values[Math.min(values.length - 1, Math.ceil(values.length * 0.95) - 1)];
    const count = 8;
    const width = Math.max(1000, (hi - lo) / count);
    const bins = Array.from({ length: count }, (_, i) => ({ start: lo + i * width, end: lo + (i + 1) * width, count: 0 }));
    values.forEach((v) => {
      const idx = Math.min(count - 1, Math.max(0, Math.floor((v - lo) / width)));
      bins[idx].count += 1;
    });
    return { values, bins };
  }, [sourcePool, jobFilters.currency]);

  // Suggested skills: the résumé's own skills first, then the most common skills in the listings.
  const skillSuggestions = useMemo(() => {
    const counts = new Map();
    sourcePool.forEach((j) => (j.extracted_skills || []).forEach((s) => {
      const key = String(s).trim();
      if (key) counts.set(key, (counts.get(key) || 0) + 1);
    }));
    const popular = [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([s]) => s);
    const seen = new Set();
    return [...(resume?.skills || []), ...popular].filter((s) => {
      const k = String(s).toLowerCase();
      if (!s || seen.has(k)) return false;
      seen.add(k);
      return true;
    }).slice(0, 12);
  }, [sourcePool, resume]);

  const filtered = useMemo(() => {
    const f = jobFilters;
    const roles = f.roles.map((r) => r.toLowerCase());
    const levels = LEVEL_BANDS.filter((band) => f.levels.includes(band.id)).flatMap((band) => band.levels);
    const tech = f.tech.map((t) => t.toLowerCase());
    const exclude = f.excludeTech.map((t) => t.toLowerCase());
    const salaryMin = f.salaryMin === "" ? null : Number(f.salaryMin);
    const salaryMax = f.salaryMax === "" || (salaryMin !== null && Number(f.salaryMax) < salaryMin) ? null : Number(f.salaryMax);
    const postedAfter = f.postedWithin === "0" ? null : Date.now() - Number(f.postedWithin) * 24 * 60 * 60 * 1000;

    return sourcePool.filter((j) => {
      const jobText = getJobSearchText(j);
      if (roles.length && !roles.some((role) => (j.title || "").toLowerCase().includes(role))) return false;
      if (f.location.trim()) {
        const location = f.location.trim().toLowerCase();
        const locationMatches = isUkCountryTerm(location)
          ? Boolean(j.is_uk_location)
          : getJobSearchText(j).includes(location);
        if (!locationMatches) return false;
      }
      if (levels.length && !levels.includes(getExperienceLevel(j))) return false;
      if (postedAfter !== null) {
        const postedAt = getPostedDate(j);
        if (!postedAt || postedAt.getTime() < postedAfter) return false;
      }

      if (salaryMin !== null || salaryMax !== null) {
        const amounts = getSalaryAmounts(j).filter((s) => s.currency === f.currency).map((s) => s.amount);
        if (!amounts.length) return false;
        if (salaryMin !== null && Math.max(...amounts) < salaryMin) return false;
        if (salaryMax !== null && Math.min(...amounts) > salaryMax) return false;
      }
      if (f.workModes?.length && !f.workModes.includes(getJobWorkMode(j).toLowerCase())) return false;
      if (f.jobTypes?.length && !f.jobTypes.includes(getEmploymentType(j))) return false;

      if (tech.length) {
        const ok = f.techMode === "and"
          ? tech.every((term) => jobText.includes(term))
          : tech.some((term) => jobText.includes(term));
        if (!ok) return false;
      }
      if (exclude.length && exclude.some((term) => jobText.includes(term))) return false;
      return true;
    });
  }, [sourcePool, jobFilters]);

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

  const activeJob = useMemo(
    () => visibleJobs.find((j) => j.id === activeJobId) || visibleJobs[0] || null,
    [visibleJobs, activeJobId]
  );

  // Thousands of rows are slow to mount, so the list renders a page at a time and grows as
  // the last row scrolls into view.
  const [renderLimit, setRenderLimit] = useState(LIST_PAGE_SIZE);
  useEffect(() => { setRenderLimit(LIST_PAGE_SIZE); }, [filtered, sortBy]);
  const moreRef = useRef(null);
  useEffect(() => {
    const el = moreRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return undefined;
    // The list scrolls inside its own pane on desktop and with the page on narrow screens.
    const list = el.parentElement;
    const root = list && list.scrollHeight > list.clientHeight ? list : null;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) setRenderLimit((n) => n + LIST_PAGE_SIZE);
    }, { root, rootMargin: "600px 0px" });
    observer.observe(el);
    return () => observer.disconnect();
  }, [renderLimit, visibleJobs.length]);

  const allVisibleInPipeline = useMemo(() => {
    if (filtered.length === 0) return false;
    return filtered.every((j) => pipelineJobIds.has(j.id));
  }, [filtered, pipelineJobIds]);

  return (
    <div className="content-container job-browser-page">
      <h1 className="jd-visually-hidden">{resume ? "Job Discovery" : "Find jobs"}</h1>
      <div className="jd-browser">
        <JobFilterPanel
          filters={jobFilters}
          onChange={setJobFilters}
          onReset={() => setJobFilters((current) => ({ ...EMPTY_JOB_FILTERS, currency: current.currency }))}
          matchCount={filtered.length}
          salaryStats={salaryStats}
          skillSuggestions={skillSuggestions}
        />

        <div className="jd-split">
          <div className="jd-list-pane">
            {resume && <p className="jd-preferences-note">You’re seeing jobs matched to your résumé and preferences.</p>}
            <div className="jd-list-head">
              <h2>{visibleJobs.length.toLocaleString()} active {visibleJobs.length === 1 ? "job" : "jobs"}</h2>
              <div className="jd-list-tools">
                <select aria-label="Sort by" value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
                  <option value="newest">Newest first</option>
                  {resume && <option value="best">Best match</option>}
                  <option value="company">Company A–Z</option>
                </select>
                {resume && (
                  <button type="button" className="jd-search-utility" onClick={onRefresh} aria-label="Refresh jobs" title="Refresh jobs">
                    <RefreshCw size={14} aria-hidden="true" />
                  </button>
                )}
                <button
                  type="button"
                  className="jd-addall"
                  onClick={() => onAddAllToPipeline(visibleJobs)}
                  disabled={visibleJobs.length === 0 || allVisibleInPipeline}
                >
                  {allVisibleInPipeline ? "All saved" : "Save all"}
                </button>
                {resume && (
                  <button type="button" className="jd-remove-resume" onClick={onRemoveResume} title="Remove your résumé and go back to all jobs">
                    <X size={14} aria-hidden="true" /> Remove résumé
                  </button>
                )}
              </div>
            </div>
            {visibleJobs.length === 0 ? (
              <div className="empty-results-box">
                <h4>No roles match your filter criteria</h4>
                <p>Try widening your posting date or removing another filter.</p>
              </div>
            ) : (
              <ul className="jd-list">
                {visibleJobs.slice(0, renderLimit).map((job) => (
                  <JobListItem
                    key={job.id}
                    job={job}
                    selected={activeJob?.id === job.id}
                    inPipeline={pipelineJobIds.has(job.id)}
                    onSelect={setActiveJobId}
                    onTogglePipeline={onTogglePipeline}
                  />
                ))}
                {renderLimit < visibleJobs.length && <li ref={moreRef} className="jd-list-more" aria-hidden="true" />}
              </ul>
            )}
          </div>
          {activeJob && (
            <JobDetailPane
              job={activeJob}
              onCreateResume={() => onSelectJob(activeJob)}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export function CompaniesView({ platforms, onOpenAdd, onScrapePlatform }) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const visiblePlatforms = platforms.filter((platform) =>
    [platform.name, platform.id, ...(platform.companies || [])]
      .some((value) => String(value || "").toLowerCase().includes(normalizedQuery))
  );
  const companyCount = platforms.reduce(
    (total, platform) => total + (platform.companies_count ?? platform.companies?.length ?? 0),
    0
  );
  const storedJobsCount = platforms.reduce((total, platform) => total + (platform.stored_jobs_count ?? 0), 0);

  return (
    <div className="content-container companies-page">
      <div className="section-page-header">
        <div className="companies-page-heading">
          <span className="hero-tag">ATS CONNECTOR CATALOG</span>
          <h1 className="page-title">Companies & platforms</h1>
          <p className="page-subtitle">Manage the career sites we scan and see the jobs collected from each source.</p>
        </div>
        <button type="button" className="btn-choose-resume companies-add-button" onClick={onOpenAdd}>
          <span>+ Add Company to Scrape</span>
        </button>
      </div>

      <div className="companies-metrics" aria-label="Company scraping totals">
        <article className="companies-metric-card">
          <span className="companies-metric-icon"><Building2 size={18} aria-hidden="true" /></span>
          <div><strong>{platforms.length}</strong><span>ATS platforms</span></div>
        </article>
        <article className="companies-metric-card">
          <span className="companies-metric-icon"><Globe size={18} aria-hidden="true" /></span>
          <div><strong>{companyCount.toLocaleString()}</strong><span>Configured companies</span></div>
        </article>
        <article className="companies-metric-card">
          <span className="companies-metric-icon"><Briefcase size={18} aria-hidden="true" /></span>
          <div><strong>{storedJobsCount.toLocaleString()}</strong><span>Active jobs stored</span></div>
        </article>
      </div>

      <label className="companies-search">
        <Search size={17} aria-hidden="true" />
        <span className="sr-only">Search companies and platforms</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search companies or ATS platforms"
          aria-label="Search companies and platforms"
        />
        {query && <button type="button" onClick={() => setQuery("")} aria-label="Clear company search"><X size={15} /></button>}
      </label>

      {visiblePlatforms.length ? (
        <div className="platforms-grid">
          {visiblePlatforms.map((p) => {
            const companies = p.companies || [];
            const companiesCount = p.companies_count ?? companies.length;
            const status = !p.status || p.status === "never_run" ? "Never run" : String(p.status).replace(/_/g, " ");
            return (
              <article key={p.id} className="platform-card">
                <div className="platform-card-header">
                  <div className="platform-brand">
                    <span className="platform-brand-mark" style={{ "--platform-color": p.color || "var(--primary-blue)" }}>
                      <Building2 size={19} aria-hidden="true" />
                    </span>
                    <div>
                      <span className="platform-title">{p.name}</span>
                      <span className="platform-id">{p.id}</span>
                    </div>
                  </div>
                  <span className={`platform-status ${p.status === "success" ? "is-success" : ""}`}>
                    <span aria-hidden="true" />{status}
                  </span>
                </div>

                <div className="platform-stats">
                  <div><strong>{companiesCount.toLocaleString()}</strong><span>Companies</span></div>
                  <div><strong>{(p.stored_jobs_count ?? 0).toLocaleString()}</strong><span>Active jobs</span></div>
                </div>

                <div className="platform-companies">
                  <div className="platform-companies-heading">
                    <strong>Configured companies</strong>
                    <span>{companiesCount.toLocaleString()}</span>
                  </div>
                  {companies.length ? (
                    <ul className="platform-companies-list">
                      {companies.map((company, index) => (
                        <li key={`${p.id}-${company}-${index}`} className="company-pill">{company}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="platform-companies-empty">No companies configured yet.</p>
                  )}
                </div>

                <div className="platform-footer">
                  <span className="platform-last-run">
                    {p.last_run ? `Last run ${new Date(p.last_run).toLocaleString()}` : "No scrape run recorded"}
                  </span>
                  <button
                    type="button"
                    className="btn-scrape-platform"
                    onClick={() => onScrapePlatform(p.id)}
                  >
                    <RefreshCw size={14} aria-hidden="true" /> Scrape {p.name}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="companies-empty-state">
          <Building2 size={24} aria-hidden="true" />
          <strong>{normalizedQuery ? "No matching companies or platforms" : "No ATS platforms configured"}</strong>
          <span>{normalizedQuery ? "Try a different search term." : "Add a company to start collecting jobs."}</span>
        </div>
      )}
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

const INSIGHT_SKILL_GROUPS = {
  "Tech & Data": /\b(software|programming|developer|development|data|analytics|sql|python|java|javascript|typescript|react|node|cloud|aws|azure|gcp|machine learning|ai|artificial intelligence|devops|cyber|database|api|engineering|technology|technical|computer|linux|kubernetes|docker|excel|power bi|tableau)\b/i,
};

function platformLabel(platform) {
  return String(platform || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatRunDuration(seconds) {
  const duration = Number(seconds) || 0;
  if (duration < 60) return `${duration.toFixed(1)}s`;
  const minutes = Math.floor(duration / 60);
  const remainingSeconds = Math.round(duration % 60);
  return remainingSeconds ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
}

export function InsightsView({ platforms = [] }) {
  const [stats, setStats] = useState(null);
  const [platformSnapshot, setPlatformSnapshot] = useState(platforms);
  const [error, setError] = useState("");
  const [skillGroup, setSkillGroup] = useState("All Skills");
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  const [exporting, setExporting] = useState(false);

  const loadStats = useCallback(async () => {
    const [statsResponse, platformsResponse] = await Promise.all([
      fetch(`${API_BASE}/api/stats`),
      fetch(`${API_BASE}/api/platforms`),
    ]);
    if (!statsResponse.ok) throw new Error(`Could not load statistics (${statsResponse.status})`);
    if (!platformsResponse.ok) throw new Error(`Could not load platform statistics (${platformsResponse.status})`);
    const [nextStats, nextPlatforms] = await Promise.all([statsResponse.json(), platformsResponse.json()]);
    setStats(nextStats);
    setPlatformSnapshot(nextPlatforms.platforms || []);
    setError("");
  }, []);

  useEffect(() => {
    loadStats().catch((err) => setError(err.message || "Could not load statistics."));
  }, [loadStats]);

  useEffect(() => setPlatformSnapshot(platforms), [platforms]);

  const activePlatforms = platformSnapshot.filter((platform) => (platform.stored_jobs_count || 0) > 0);
  const byPlatform = stats?.by_platform || {};
  const platformRows = platformSnapshot.map((platform) => ({
    id: platform.id,
    name: platform.name || platformLabel(platform.id),
    count: byPlatform[platform.id] ?? platform.stored_jobs_count ?? 0,
    color: platform.color || "#2563eb",
  })).sort((a, b) => b.count - a.count);
  const maxPlatformJobs = Math.max(...platformRows.map((platform) => platform.count), 1);
  const allSkills = stats?.top_skills || [];
  const skills = allSkills.filter(({ skill }) => skillGroup === "All Skills" || INSIGHT_SKILL_GROUPS[skillGroup].test(skill));
  const topSkill = allSkills[0];
  const maxSkillMentions = Math.max(...skills.map((item) => item.count), 1);
  const latestRun = stats?.recent_runs?.[0];

  const syncCrawlers = async () => {
    setSyncing(true);
    setSyncMessage("");
    try {
      const response = await fetch(`${API_BASE}/api/scrape?platform=all`, { method: "POST" });
      if (!response.ok) throw new Error(`Could not start crawler sync (${response.status})`);
      const result = await response.json();
      setSyncMessage(result.message || "Crawler sync started. Analytics will update as listings are collected.");
      window.setTimeout(() => {
        loadStats().catch((err) => setError(err.message || "Could not refresh statistics."));
      }, 3000);
    } catch (err) {
      setSyncMessage(err.message || "Could not start crawler sync.");
    } finally {
      setSyncing(false);
    }
  };

  const exportInsights = () => {
    if (!stats) return;
    setExporting(true);
    try {
      const rows = [
        ["Cafy Agent — Job Market & Skill Insights"],
        ["Generated", new Date().toLocaleString()],
        ["Active job listings", stats.total_active_jobs || 0],
        ["Active platforms", `${activePlatforms.length}/${platformSnapshot.length}`],
        [],
        ["Platform", "Stored jobs", "Share of listings"],
        ...platformRows.map(({ name, count }) => [name, count, `${stats.total_active_jobs ? Math.round((count / stats.total_active_jobs) * 100) : 0}%`]),
        [],
        ["Rank", "Skill", "Job mentions", "Share of listings"],
        ...allSkills.map((item, index) => [
          index + 1,
          item.skill,
          item.count,
          `${stats.total_active_jobs ? Math.round((item.count / stats.total_active_jobs) * 100) : 0}%`,
        ]),
      ];
      const csv = rows.map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n");
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "cafy-job-market-insights.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="content-container analytics-page">
      <header className="analytics-header">
        <div>
          <div className="analytics-breadcrumb">Enterprise Workspace <span>›</span> Analytics &amp; Intelligence</div>
          <div className="analytics-title-row">
            <h1 className="page-title">Job Market &amp; Skill Insights</h1>
            <span className="analytics-live"><span /> Live Sync: Local DB Active</span>
          </div>
        </div>
        <div className="analytics-header-actions">
          <button type="button" className="analytics-button" onClick={exportInsights} disabled={!stats || exporting}>
            <Download size={14} /> {exporting ? "Exporting…" : "Export Intel"}
          </button>
          <button type="button" className="analytics-button analytics-button-primary" onClick={syncCrawlers} disabled={syncing}>
            <RefreshCw size={14} className={syncing ? "analytics-spin" : ""} /> {syncing ? "Syncing…" : "Sync All Crawlers"}
          </button>
        </div>
      </header>

      <div className="analytics-intro">
        <p>Continuous telemetry aggregated across live ATS job listings stored in your local database.</p>
        <span>{latestRun?.finished_at ? `Last crawler run · ${new Date(latestRun.finished_at).toLocaleString()}` : "Analytics reflect the latest stored snapshot."}</span>
      </div>

      {error && <div className="pipeline-error" role="alert">{error}</div>}
      {syncMessage && <div className={`analytics-message ${syncMessage.startsWith("Could not") ? "is-error" : ""}`} role="status">{syncMessage}</div>}
      {!stats ? (
        <div className="analytics-loading">Loading live market insights…</div>
      ) : (
        <>
          <section className="analytics-metrics" aria-label="Market summary">
            <article className="analytics-metric">
              <div className="analytics-metric-label"><span>Total stored<br />live jobs</span><span className="analytics-tag analytics-tag-green">Live</span></div>
              <div className="analytics-metric-value">{(stats.total_active_jobs || 0).toLocaleString()} <span>active roles</span></div>
              <div className="analytics-metric-note"><Check size={12} /> Stored in local database</div>
              <div className="analytics-meter"><span style={{ width: stats.total_active_jobs ? "100%" : "0%" }} /></div>
            </article>
            <article className="analytics-metric">
              <div className="analytics-metric-label"><span>Active<br />platforms</span><span className="analytics-tag analytics-tag-blue">{activePlatforms.length} Online</span></div>
              <div className="analytics-metric-value">{activePlatforms.length} <span>/ {platformSnapshot.length} connectors</span></div>
              <div className="analytics-metric-note">{activePlatforms.length ? activePlatforms.map((platform) => platform.name || platformLabel(platform.id)).join(", ") : "No active listing sources yet."}</div>
              <div className="analytics-meter"><span style={{ width: `${platformSnapshot.length ? Math.min((activePlatforms.length / platformSnapshot.length) * 100, 100) : 0}%` }} /></div>
            </article>
            <article className="analytics-metric">
              <div className="analytics-metric-label"><span>Latest scrape<br />results</span><span className="analytics-tag analytics-tag-purple">{latestRun?.status ? platformLabel(latestRun.status) : "Awaiting run"}</span></div>
              <div className="analytics-metric-value">+{(latestRun?.jobs_found || 0).toLocaleString()} <span>jobs in latest run</span></div>
              <div className="analytics-metric-note">{latestRun ? `${platformLabel(latestRun.platform)} · ${formatRunDuration(latestRun.duration_seconds)}` : "Sync crawlers to collect new listings."}</div>
              <div className="analytics-meter analytics-meter-purple"><span style={{ width: `${Math.min(((latestRun?.jobs_found || 0) / Math.max(stats.total_active_jobs || 1, 1)) * 100, 100)}%` }} /></div>
            </article>
            <article className="analytics-metric">
              <div className="analytics-metric-label"><span>Top frequency<br />skill</span><span className="analytics-tag analytics-tag-amber">{topSkill ? "#1 Ranked" : "No data"}</span></div>
              <div className="analytics-metric-value analytics-top-skill">{topSkill?.skill || "No skills yet"} <span>{topSkill ? `${topSkill.count.toLocaleString()} mentions` : "—"}</span></div>
              <div className="analytics-metric-note">{topSkill && stats.total_active_jobs ? `Found in ${((topSkill.count / stats.total_active_jobs) * 100).toFixed(1)}% of stored listings.` : "Skills appear when active jobs include parsed skill data."}</div>
              <div className="analytics-meter analytics-meter-amber"><span style={{ width: `${topSkill ? Math.min((topSkill.count / Math.max(stats.total_active_jobs || 1, 1)) * 100, 100) : 0}%` }} /></div>
            </article>
          </section>

          <section className="analytics-details">
            <article className="analytics-panel analytics-skills-panel">
              <div className="analytics-panel-heading">
                <div>
                  <h2>Most In-Demand Skills Across Stored Jobs</h2>
                  <p>Ranked frequency index extracted from stored job listings.</p>
                </div>
                <div className="analytics-filter" role="group" aria-label="Filter skills">
                  {["All Skills", "Tech & Data"].map((group) => (
                    <button type="button" key={group} className={skillGroup === group ? "is-active" : ""} aria-pressed={skillGroup === group} onClick={() => setSkillGroup(group)}>{group}</button>
                  ))}
                </div>
              </div>
              <div className="analytics-skill-list">
                {skills.length ? skills.map((item, index) => {
                  const share = stats.total_active_jobs ? (item.count / stats.total_active_jobs) * 100 : 0;
                  return (
                    <div className="analytics-skill-row" key={item.skill}>
                      <span className={`analytics-rank ${index === 0 ? "is-top" : ""}`}>#{index + 1}</span>
                      <div className="analytics-skill-name"><strong>{item.skill}</strong><span>{INSIGHT_SKILL_GROUPS["Tech & Data"].test(item.skill) ? "Technology & data" : "Business & operations"}</span></div>
                      <div className="analytics-skill-penetration"><span>Penetration</span><div className="analytics-meter"><span style={{ width: `${Math.min((item.count / maxSkillMentions) * 100, 100)}%` }} /></div></div>
                      <span className="analytics-skill-share">{share.toFixed(1)}%</span>
                      <span className="analytics-skill-growth">{index === 0 ? "Top" : `#${index + 1}`}</span>
                      <span className="analytics-mentions">{item.count.toLocaleString()} mentions</span>
                    </div>
                  );
                }) : <div className="analytics-empty">No skills in this category yet.</div>}
              </div>
            </article>

            <article className="analytics-panel analytics-platform-panel">
              <div className="analytics-panel-heading">
                <div><h2>Platform Distribution</h2><p>{platformRows.length} ATS nodes</p></div>
              </div>
              <div className="analytics-platform-list">
                {platformRows.length ? platformRows.map((platform) => {
                  const share = stats.total_active_jobs ? Math.round((platform.count / stats.total_active_jobs) * 100) : 0;
                  return (
                    <div className="analytics-platform-row" key={platform.id}>
                      <div><span className="analytics-platform-name"><i style={{ background: platform.color }} />{platform.name}</span><span className="analytics-platform-count">{platform.count.toLocaleString()} jobs <b>({share}%)</b></span></div>
                      <div className="analytics-meter"><span style={{ width: `${(platform.count / maxPlatformJobs) * 100}%`, background: platform.color }} /></div>
                    </div>
                  );
                }) : <div className="analytics-empty">No ATS platforms are configured.</div>}
              </div>
            </article>
          </section>
        </>
      )}
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
              <option value="smartrecruiters">SmartRecruiters (jobs.smartrecruiters.com)</option>
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

// Closes a modal on Escape while it is open.
function useEscapeToClose(onClose) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
}

function JobDescriptionBlocks({ job }) {
  const blocks = useMemo(() => parseJobDescription(job?.description), [job?.id, job?.description]);
  if (!blocks.length) {
    return (
      <p className="jd-muted">
        The full description is on the employer's site.
        {job?.url && <> <a href={job.url} target="_blank" rel="noopener noreferrer">Read the full job advert <ExternalLink size={12} aria-hidden="true" /></a></>}
      </p>
    );
  }
  return blocks.map((b, i) => (
    b.type === "h" ? <h4 key={i}>{b.text}</h4>
      : b.type === "li" ? <p key={i} className="jd-li"><CheckCircle2 size={15} aria-hidden="true" /><span>{b.text}</span></p>
        : <p key={i}>{b.text}</p>
  ));
}

// The four headline facts shown on both application modals.
function getJobFacts(job) {
  const salary = formatSalaryRange(job);
  const visa = getVisaState(job);
  const posted = formatJobAge(job.posted_at || job.created_at);
  return [
    { icon: CalendarDays, label: "Posted", value: posted || "Not listed", sub: job.employment_type || "" },
    { icon: Clock, label: "Work mode", value: getJobWorkMode(job) || "Not listed", sub: job.location || "" },
    { icon: Banknote, label: "Compensation", value: salary || "Not listed", sub: salary ? "Advertised range" : "See employer site", tone: salary ? "ok" : "" },
    { icon: Globe, label: "Work visa", value: visa?.title || "Not listed", sub: visa?.detail || "", tone: visa?.tone === "ok" ? "ok" : "" },
  ];
}

function ApplicationReviewModal({ job, status, statusOptions, onStatusChange, onClose, onEditResume, onViewPosting, masterResume }) {
  useEscapeToClose(onClose);
  const [saved, setSaved] = useState({ loading: true, data: null, error: "" });
  const [draftStatus, setDraftStatus] = useState(status);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSaved({ loading: true, data: null, error: "" });
    fetch(`${API_BASE}/api/resumes/job/${encodeURIComponent(job.id)}`)
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Could not load the resume (${res.status}).`);
        if (!cancelled) setSaved({ loading: false, data: body.status === "found" ? body : null, error: "" });
      })
      .catch((err) => { if (!cancelled) setSaved({ loading: false, data: null, error: err.message }); });
    return () => { cancelled = true; };
  }, [job.id]);

  const tailored = useMemo(
    () => (saved.data?.tailored_resume ? normalizeClientResume(saved.data.tailored_resume, masterResume, job) : null),
    [saved.data, masterResume, job]
  );
  const score = Number(job.match_score);
  const hasScore = job.match_score !== null && job.match_score !== undefined && Number.isFinite(score);
  const downloadPath = saved.data?.pdf_url || saved.data?.docx_url;
  const downloadLabel = saved.data?.pdf_url ? "Download Tailored Resume (PDF)" : "Download Tailored Resume (DOCX)";
  const facts = getJobFacts(job).slice(1);
  const mode = getJobWorkMode(job);
  const updated = saved.data?.updated_at ? formatJobAge(saved.data.updated_at) : "";

  const copyText = async () => {
    const node = document.getElementById("resume-printable-doc");
    if (!node) return;
    try {
      await navigator.clipboard.writeText(node.innerText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard blocked */ }
  };

  return (
    <div className="app-modal-overlay" onClick={onClose} role="presentation">
      <div className="app-modal app-review-modal" role="dialog" aria-modal="true" aria-label={`Application: ${job.title}`} onClick={(e) => e.stopPropagation()}>
        <header className="app-modal-head">
          <div className="app-modal-logo">{(job.company || "?").charAt(0).toUpperCase()}</div>
          <div className="app-modal-titles">
            <div className="app-modal-titleline">
              <h2>{job.title}</h2>
              <span className="app-chip blue">● {status}</span>
            </div>
            <p>
              <strong>{job.company || "Company not listed"}</strong>
              {job.location && <> · <MapPin size={12} aria-hidden="true" /> {job.location}</>}
              {mode && <> · {mode}</>}
              <> · <span className="app-link-text">ATS: {job.ats_platform || "Cafy"}</span></>
            </p>
          </div>
          <div className="app-modal-actions">
            <button type="button" className="app-btn secondary" onClick={onEditResume}><PenLine size={14} aria-hidden="true" /> {tailored ? "Edit Resume" : "Create Resume"}</button>
            {downloadPath && (
              <button type="button" className="app-btn primary" onClick={() => window.open(withToken(`${API_BASE}${downloadPath}`), "_blank", "noopener")}>
                <Download size={14} aria-hidden="true" /> {downloadLabel}
              </button>
            )}
            {job.url && (
              <a className="app-icon-btn" href={job.url} target="_blank" rel="noopener noreferrer" aria-label="Open job advert"><ExternalLink size={15} /></a>
            )}
            <button type="button" className="app-icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
          </div>
        </header>

        <div className="app-review-split">
          <section className="app-review-pane">
            <div className="app-pane-head">
              <span><FileText size={15} aria-hidden="true" /> <strong>Tailored Resume</strong></span>
              {updated && <span className="app-muted">Updated {updated}</span>}
              {hasScore && <span className="app-chip green"><CheckCircle2 size={12} aria-hidden="true" /> {Math.round(score)}% ATS Match</span>}
              {masterResume?.candidate_name && <span className="app-muted">Profile: <strong>{masterResume.candidate_name}</strong></span>}
            </div>
            <div className="app-pane-body app-resume-scroll">
              {saved.loading ? (
                <div className="applications-empty">Loading tailored resume…</div>
              ) : saved.error ? (
                <div className="applications-empty">{saved.error}</div>
              ) : tailored ? (
                <ResumeDocumentPreview resume={tailored} job={job} resumeReady isGeneratingResume={false} />
              ) : (
                <div className="app-empty-resume">
                  <Sparkles size={26} aria-hidden="true" />
                  <strong>No tailored resume yet</strong>
                  <p>Create a version of your resume targeted at this role.</p>
                  <button type="button" className="app-btn primary" onClick={onEditResume}>Create Resume</button>
                </div>
              )}
            </div>
            {tailored && (
              <div className="app-pane-foot">
                <button type="button" className="app-link-btn" onClick={copyText}><ScrollText size={13} aria-hidden="true" /> {copied ? "Copied" : "Copy full text"}</button>
              </div>
            )}
          </section>

          <section className="app-review-pane">
            <div className="app-pane-head">
              <span><Briefcase size={15} aria-hidden="true" /> <strong>Job Description &amp; Specification</strong></span>
              <button type="button" className="app-link-btn" onClick={onViewPosting}>View full posting</button>
            </div>
            <div className="app-pane-body">
              <div className="app-card">
                <div className="app-card-title"><h3>Role Overview</h3>{job.industry && <span className="app-chip blue">{job.industry}</span>}</div>
                <div className="jd-detail-body app-jd-text"><JobDescriptionBlocks job={job} /></div>
              </div>
              <div className="app-facts three">
                {facts.map(({ icon: Icon, label, value, sub, tone }) => (
                  <div key={label} className="app-fact">
                    <span className="app-fact-label"><Icon size={13} aria-hidden="true" /> {label}</span>
                    <strong className={tone === "ok" ? "ok" : ""}>{value}</strong>
                    {sub && <small>{sub}</small>}
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>

        <footer className="app-modal-foot">
          <label className="app-status-select">
            <span>PIPELINE STATUS:</span>
            <select value={draftStatus} onChange={(e) => setDraftStatus(e.target.value)}>
              {statusOptions.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <div className="app-foot-actions">
            <button type="button" className="app-btn ghost" onClick={onClose}>Close</button>
            <button type="button" className="app-btn primary" onClick={() => { onStatusChange(draftStatus); onClose(); }}>
              <Save size={14} aria-hidden="true" /> Update Status
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

function JobPostingModal({ job, onClose, onCustomizeResume, onReviewApplication }) {
  useEscapeToClose(onClose);
  const facts = getJobFacts(job);
  const mode = getJobWorkMode(job);
  const level = EXPERIENCE_LEVELS.find(([value]) => value === getExperienceLevel(job));
  const initials = (job.company || "?").split(/\s+/).filter(Boolean).slice(0, 3).map((w) => w[0]).join("").toUpperCase();

  return (
    <div className="app-modal-overlay" onClick={onClose} role="presentation">
      <div className="app-modal app-posting-modal" role="dialog" aria-modal="true" aria-label={`Job posting: ${job.title}`} onClick={(e) => e.stopPropagation()}>
        <header className="app-modal-head">
          <div className="app-modal-logo large">{initials}</div>
          <div className="app-modal-titles">
            <div className="app-chip-row">
              <span className="app-chip blue">ATS: {job.ats_platform || "Cafy"}</span>
              {job.employment_type && <span className="app-chip grey">{job.employment_type}</span>}
              {level && <span className="app-chip green">{level[1]}</span>}
            </div>
            <h2>{job.title}</h2>
            <p>
              <strong>{job.company || "Company not listed"}</strong>
              {job.location && <> · <MapPin size={12} aria-hidden="true" /> {job.location}{mode ? ` (${mode})` : ""}</>}
            </p>
          </div>
          <div className="app-modal-actions">
            {job.url && (
              <a className="app-icon-btn" href={job.url} target="_blank" rel="noopener noreferrer" aria-label="Open job advert"><ExternalLink size={15} /></a>
            )}
            <button type="button" className="app-icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
          </div>
        </header>

        <div className="app-pane-body app-posting-body">
          <div className="app-facts four">
            {facts.map(({ label, value, sub, tone }) => (
              <div key={label} className="app-fact">
                <span className="app-fact-label upper">{label}</span>
                <strong className={tone === "ok" ? "ok" : ""}>{value}</strong>
                {sub && <small>{sub}</small>}
              </div>
            ))}
          </div>

          {(job.company_description) && (
            <div className="app-card">
              <div className="app-card-title"><h3><Building2 size={16} aria-hidden="true" /> About {job.company}</h3></div>
              <p className="app-jd-text">{sanitizeDisplayText(job.company_description)}</p>
            </div>
          )}

          <div className="app-card">
            <div className="app-card-title"><h3><Briefcase size={16} aria-hidden="true" /> What You Will Work On</h3></div>
            <div className="jd-detail-body app-jd-text"><JobDescriptionBlocks job={job} /></div>
          </div>
        </div>

        <footer className="app-modal-foot">
          <button type="button" className="app-btn ghost" onClick={onClose}>Close</button>
          <div className="app-foot-actions">
            <button type="button" className="app-btn soft" onClick={onCustomizeResume}><Sparkles size={14} aria-hidden="true" /> Customize Resume for this Job</button>
            <button type="button" className="app-btn primary" onClick={onReviewApplication}>Review Application <ArrowRight size={14} aria-hidden="true" /></button>
          </div>
        </footer>
      </div>
    </div>
  );
}

function ApplicationTrackingView({
  pipelineJobIds,
  allJobs,
  onSelectJob,
  onCustomizeResume,
  resume,
}) {
  const [filter, setFilter] = useState("all");
  // Which application modal is open: { kind: "review" | "posting", job }.
  const [modal, setModal] = useState(null);
  const closeModal = useCallback(() => setModal(null), []);
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
  const stagedJobs = pipelineJobs.slice(0, 3);

  return (
    <div className="content-container applications-workspace">
      <div className="applications-heading">
        <div>
          <div className="applications-kicker">MY APPLICATIONS <span>{stagedJobs.length} staged for review</span></div>
          <h1>My Applications</h1>
          <p>Applications generated and staged through Cafy. Review match scores and customized resumes before continuing.</p>
        </div>
        <div className="applications-heading-actions">
          <span className="autopilot-pill">● Auto-Pilot: Ready</span>
          <button type="button" className="applications-refresh" onClick={() => setStatusMap({})}>↻</button>
        </div>
      </div>

      <section className="applications-panel staged-panel">
        <div className="applications-panel-heading">
          <div>
            <h2><span className="panel-accent blue" /> Staged Approvals</h2>
            <span>Manual Review Required</span>
          </div>
          <div className="application-filters">
            <input placeholder="⌕  Filter by company, role..." aria-label="Filter by company or role" />
            <select aria-label="Application date"><option>Date: Summer 2027 Run</option></select>
            <select aria-label="ATS source"><option>ATS: All Sources</option></select>
          </div>
        </div>
        {stagedJobs.length === 0 ? (
          <div className="applications-empty">No staged applications. Add jobs to your pipeline from Find Jobs.</div>
        ) : stagedJobs.map((job) => (
          <div key={job.id} className="approval-card">
            <div className="approval-card-top">
              <div className="company-mark">{(job.company || "?").charAt(0).toUpperCase()}</div>
              <div className="approval-role">
                <h3>{job.title} <span>· Summer 2027</span></h3>
                <p>{job.company || "Company not listed"} · <MapPin size={11} /> {job.location || "Location not listed"} · ATS: {job.ats_platform || "Cafy"}</p>
              </div>
              <span className="approval-status">Draft / Pending Review</span>
              <div className="approval-score">ATS MATCH SCORE <strong>{Math.round(Number(job.match_score) || 0)}%</strong><small>/ 100</small></div>
            </div>
            <div className="approval-card-actions">
              <span className="approval-document">▣ Customized resume ready</span>
              <span className="approval-document">◎ Targeted for {job.title}</span>
              <button type="button" className="applications-secondary" onClick={() => setModal({ kind: "posting", job })}>View Posting</button>
              <button type="button" className="applications-primary" onClick={() => setModal({ kind: "review", job })}>Review Application</button>
            </div>
          </div>
        ))}
        <div className="applications-notice">ⓘ Review each staged application before continuing. Cafy does not submit applications automatically.</div>
      </section>

      <section className="applications-panel tracking-panel">
        <div className="applications-panel-heading">
          <div>
            <h2><span className="panel-accent green" /> Application Tracking</h2>
            <span>Jobs you added to your pipeline. Click a status to update progress.</span>
          </div>
          <button type="button" className="applications-secondary">＋ Add Job Manually</button>
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
                      <strong>{job.title} <span className="tracking-type">{job.employment_type || "On-site"}</span></strong>
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
                    <button type="button" className="btn-tracking-view" onClick={() => setModal({ kind: "review", job })}>
                      View
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
        <div className="applications-footer">Tracking {filteredJobs.length} of {pipelineJobs.length} active job opportunities <span>Last synchronized just now</span></div>
      </section>

      {modal?.kind === "review" && (
        <ApplicationReviewModal
          key={modal.job.id}
          job={modal.job}
          masterResume={resume}
          status={getStatus(modal.job)}
          statusOptions={STATUS_FLOW}
          onStatusChange={(next) => setStatusMap((prev) => ({ ...prev, [modal.job.id]: next }))}
          onClose={closeModal}
          onEditResume={() => { const job = modal.job; setModal(null); onSelectJob(job); }}
          onViewPosting={() => setModal({ kind: "posting", job: modal.job })}
        />
      )}
      {modal?.kind === "posting" && (
        <JobPostingModal
          key={modal.job.id}
          job={modal.job}
          onClose={closeModal}
          onCustomizeResume={() => { const job = modal.job; setModal(null); (onCustomizeResume || onSelectJob)(job); }}
          onReviewApplication={() => setModal({ kind: "review", job: modal.job })}
        />
      )}
    </div>
  );
}

export { DirectoryView, JobDetailModal, ApplicationTrackingView, ProfileStrengthMeter, ResumeProfileView };
export default App;

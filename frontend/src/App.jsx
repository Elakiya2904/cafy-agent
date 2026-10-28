// ==========================================================================
// CAFY AGENT • REACT APPLICATION
// ==========================================================================

const { useState, useEffect, useCallback, useMemo, useRef } = React;

const API_BASE = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") && window.location.port && window.location.port !== "8000"
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
      setAssistantOpen(true);
      showToast(`Analyzed résumé! Found ${data.matched_jobs?.length || 0} top roles (≥85% match).`);
      
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

  // Handle Demo Profiles
  const handleSampleProfile = async (sampleKey) => {
    setIsProcessing(true);
    setCurrentStep(2);
    showToast(`Loading demo candidate profile (${sampleKey})...`);

    try {
      const formData = new FormData();
      formData.append("sample_key", sampleKey);

      const res = await fetch(`${API_BASE}/api/resume/sample`, {
        method: "POST",
        body: formData
      });

      if (!res.ok) throw new Error("Failed to load demo profile");

      const data = await res.json();
      setCurrentResume(data.resume);
      setMatchedJobs(data.matched_jobs || []);
      setCurrentStep(3);
      setAssistantOpen(true);
      showToast(`Analyzed profile! Found ${data.matched_jobs?.length || 0} top roles (≥85% match).`);

      // Auto-redirect to Find Jobs tab
      setTimeout(() => {
        setActiveTab("find-jobs");
      }, 700);
    } catch (err) {
      console.error(err);
      showToast(`Error: ${err.message}`);
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
        setActiveTab={setActiveTab}
        totalJobsCount={totalJobsCount}
        hasResume={!!currentResume}
        highMatchCount={matchedJobs.length}
        pipelineCount={pipelineJobIds.size}
      />

      {/* MAIN CONTENT AREA */}
      <main className="main-content">
        <header className="main-top-bar">
          <div className="top-bar-left">
            <span style={{ fontSize: "0.82rem", color: "#64748B", fontWeight: 500 }}>
              ATS Scraper & Intelligence • 8 Connected Platforms
            </span>
          </div>
          <div className="top-bar-right">
            <button
              type="button"
              className="top-bar-assistant-btn"
              onClick={() => setAssistantOpen(true)}
              title="Open Cafy Agent Chatbot"
            >
              <BirdLogo size={19} />
              <span>Cafy Agent</span>
            </button>
            {currentResume && (
              <div className="user-profile-badge">
                <span className="user-avatar-circle">
                  {currentResume.candidate_name.charAt(0).toUpperCase()}
                </span>
                <span className="user-name">
                  {currentResume.candidate_name}
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
                onSampleSelected={handleSampleProfile}
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
            />
          </div>
        )}

        {/* TAB: FIND JOBS (Browse all stored jobs & >=85% matched jobs) */}
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
              showToast(`Scraping ${pId}...`);
              await fetch(`${API_BASE}/api/scrape`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ platform: pId })
              });
              setTimeout(loadPlatformsAndJobs, 3000);
            }}
          />
        )}

        {/* TAB: RESUME DETAILS */}
        {activeTab === "resume" && (
          <ResumeProfileView
            resume={currentResume}
            onUploadNew={() => {
              setActiveTab("home");
              if (fileInputRef.current) fileInputRef.current.click();
            }}
          />
        )}

        {/* TAB: INSIGHTS */}
        {activeTab === "insights" && <InsightsView />}

        {/* TAB: MY APPLICATIONS */}
        {activeTab === "my-applications" && (
          <div className="content-container">
            <h1 className="page-title">My Pipeline ({pipelineJobIds.size})</h1>
            <p className="page-subtitle">Roles you have added to your active application pipeline.</p>
            {pipelineJobIds.size === 0 ? (
              <div className="empty-state-card">
                <p>You haven't tracked any applications yet. Click <strong>+ Add to pipeline</strong> on any role in Find Jobs to log your progress!</p>
              </div>
            ) : (
              <div className="jobs-grid-3col" style={{ marginTop: 24 }}>
                {allJobs.filter((j) => pipelineJobIds.has(j.id)).map((job) => (
                  <JobCard
                    key={job.id}
                    job={job}
                    inPipeline={true}
                    onTogglePipeline={() => togglePipeline(job.id)}
                    onViewDetails={() => setSelectedJob(job)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB: JOB ALERTS */}
        {activeTab === "job-alerts" && (
          <div className="content-container">
            <h1 className="page-title">Job Alerts</h1>
            <p className="page-subtitle">Get automatic notifications when new roles matching your skills are scraped.</p>
            <div className="empty-state-card">
              <p>No active alerts. When new postings match your résumé skills on Greenhouse, Ashby, Workday, or Lever, they will appear here automatically.</p>
            </div>
          </div>
        )}

        {/* TAB: FOLLOW-UPS */}
        {activeTab === "follow-ups" && (
          <div className="content-container">
            <h1 className="page-title">Follow-ups</h1>
            <p className="page-subtitle">Keep track of recruiter outreach and interview stages.</p>
            <div className="empty-state-card">
              <p>No pending follow-ups. Apply to roles to set reminder check-ins and schedule interview milestones.</p>
            </div>
          </div>
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
                  <p>Extracted {currentResume.total_skills} skills • {currentResume.seniority_level} • {currentResume.candidate_name}</p>
                </div>
              ) : (
                <p>No files uploaded yet. Upload a résumé on the Home tab to see your document breakdown here.</p>
              )}
            </div>
          </div>
        )}

        {/* TAB: SETTINGS */}
        {activeTab === "settings" && (
          <div className="content-container">
            <h1 className="page-title">Settings</h1>
            <p className="page-subtitle">Configure Cafy Agent scraping intervals, minimum tolerances, and ATS connections.</p>
            <div className="settings-card">
              <div className="setting-item">
                <div>
                  <strong>Background Scraper Service</strong>
                  <p>Automatic periodic updates across all 8 ATS networks (every 6 hours).</p>
                </div>
                <input type="checkbox" defaultChecked />
              </div>
              <div className="setting-item">
                <div>
                  <strong>Strict Zero-Mock Data Policy</strong>
                  <p>Never generate synthetic vacancies when an external career board is offline.</p>
                </div>
                <span className="badge-pill" style={{ background: "#ECFDF5", color: "#059669" }}>Enforced</span>
              </div>
            </div>
          </div>
        )}
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
          onClose={() => setSelectedJob(null)}
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
        <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z"/>
        <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24z"/>
        <path fill="#FBBC05" d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.98 0 12s.45 3.82 1.25 5.42l4.03-3.15z"/>
        <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.93 6.72-4.93z"/>
      </svg>
    );
  }
  if (c.includes("microsoft")) {
    return (
      <svg width="20" height="20" viewBox="0 0 23 23" style={{ flexShrink: 0 }}>
        <path fill="#f35325" d="M1 1h10v10H1z"/>
        <path fill="#81bc06" d="M12 1h10v10H12z"/>
        <path fill="#05a6f0" d="M1 12h10v10H1z"/>
        <path fill="#ffba08" d="M12 12h10v10H12z"/>
      </svg>
    );
  }
  if (c.includes("amazon")) {
    return (
      <div style={{ width: "24px", height: "24px", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <text x="3" y="16" fontFamily="Inter, system-ui, sans-serif" fontWeight="900" fontSize="17" fill="#0F172A">a</text>
          <path d="M4 18.5c4 2.2 10.5 2.2 14.5 0" stroke="#FF9900" strokeWidth="2.2" strokeLinecap="round"/>
        </svg>
      </div>
    );
  }
  if (c.includes("databricks")) {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }} aria-hidden="true">
        <path d="M12 2L2 7l10 5 10-5-10-5z" fill="#FF3621"/>
        <path d="M2 12l10 5 10-5-10-5-10 5z" fill="#FF3621" opacity="0.85"/>
        <path d="M2 17l10 5 10-5-10-5-10 5z" fill="#FF3621" opacity="0.7"/>
      </svg>
    );
  }
  if (c.includes("stripe")) {
    return (
      <div style={{ width: "22px", height: "22px", borderRadius: "5px", background: "#635BFF", display: "grid", placeItems: "center", flexShrink: 0 }} aria-hidden="true">
        <svg width="12" height="14" viewBox="0 0 12 14" fill="#FFFFFF">
          <path d="M4.8 5.4c0-.6.5-.9 1.4-.9 1.2 0 2.8.4 4 .9V1.7C8.9 1.3 7.5 1.1 6.2 1.1 2.8 1.1.9 2.9.9 5.6c0 4.2 5.8 3.5 5.8 5.3 0 .7-.6 1-1.6 1-1.5 0-3.4-.6-4.9-1.4v3.8c1.6.7 3.3 1 4.9 1 3.6 0 5.8-1.7 5.8-4.6-.1-4.4-6.1-3.7-6.1-5.3z"/>
        </svg>
      </div>
    );
  }
  if (c.includes("linear")) {
    return (
      <div style={{ width: "22px", height: "22px", borderRadius: "5px", background: "#5E6AD2", display: "grid", placeItems: "center", flexShrink: 0 }} aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.5">
          <line x1="4" y1="20" x2="20" y2="4" strokeLinecap="round"/>
        </svg>
      </div>
    );
  }
  if (c.includes("figma")) {
    return (
      <svg width="16" height="22" viewBox="0 0 38 57" style={{ flexShrink: 0 }} aria-hidden="true">
        <path fill="#1abcfe" d="M19 28.5a9.5 9.5 0 1 1 19 0 9.5 9.5 0 0 1-19 0z"/>
        <path fill="#0acf83" d="M0 47.5A9.5 9.5 0 0 1 9.5 38H19v9.5a9.5 9.5 0 1 1-19 0z"/>
        <path fill="#ff7262" d="M19 0v19h9.5a9.5 9.5 0 1 0 0-19H19z"/>
        <path fill="#f24e1e" d="M0 9.5A9.5 9.5 0 0 0 9.5 19H19V0H9.5A9.5 9.5 0 0 0 0 9.5z"/>
        <path fill="#a259ff" d="M0 28.5A9.5 9.5 0 0 0 9.5 38H19V19H9.5A9.5 9.5 0 0 0 0 28.5z"/>
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
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
      </svg>
    )
  },
  {
    id: "explain",
    label: "Explain a job match",
    prompt: "Explain why I match this job",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0066FF" strokeWidth="2.2">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><circle cx="12" cy="11" r="3"/>
      </svg>
    )
  },
  {
    id: "search",
    label: "Find new jobs",
    prompt: "Find new jobs",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0066FF" strokeWidth="2.4" strokeLinecap="round">
        <circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.5" y2="16.5"/>
      </svg>
    )
  },
  {
    id: "skills",
    label: "Skill gap analysis",
    prompt: "Skill gap analysis",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="#0066FF">
        <rect x="3" y="12" width="4" height="9" rx="1"/><rect x="10" y="7" width="4" height="14" rx="1"/><rect x="17" y="3" width="4" height="18" rx="1"/>
      </svg>
    )
  },
  {
    id: "strategy",
    label: "Application strategy",
    prompt: "Which jobs should I prioritise this week?",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="#0066FF">
        <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" fill="none" stroke="#0066FF" strokeWidth="2"/>
      </svg>
    )
  },
  {
    id: "progress",
    label: "Show my progress",
    prompt: "Show my progress",
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0066FF" strokeWidth="2.2" strokeLinecap="round">
        <circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>
      </svg>
    )
  },
];

function renderCareerAnswer(content) {
  const lines = String(content || "")
    .replace(/\u00a0/g, " ")
    .replace(/\u200b/g, "")
    .replace(/\r/g, "")
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

  const isTableRow = (line) => /^[\s\u00a0]*\|.*\|\s*$/.test(line);
  const parseTableRow = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
  const isTableDivider = (line) => isTableRow(line) && parseTableRow(line).every((cell) => /^:?-{3,}:?$/.test(cell));
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
      content: "Hi! 👋\nI can help you explore current job listings and application strategies. Upload your resume to get evidence-based match scores, skill comparisons, and personalized recommendations.\n\nWhat would you like to do?",
      showQuickActions: true,
      job_cards: [],
    },
  ];

  const [messages, setMessages] = useState(createInitialMessages);
  const threadRef = useRef(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
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
          followUp: cards.length > 0 ? "Would you like me to explain the match in more detail or suggest a learning plan to improve your chances?" : null,
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
                                  View job →
                                </a>
                              </div>
                            )}
                          </article>
                        );
                      })}
                    </div>
                  )}

                  {/* Follow-up question bubble */}
                  {message.followUp && (
                    <div className="career-chat-bubble assistant follow-up" style={{ marginTop: "12px" }}>
                      <p style={{ margin: 0 }}>{message.followUp}</p>
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
                  <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3Z"/>
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
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
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

function Sidebar({ activeTab, setActiveTab, totalJobsCount, hasResume, highMatchCount = 0, pipelineCount = 0 }) {
  const navItems = [
    { id: "home", label: "Home", icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="3" width="7" height="7" rx="1.5"></rect>
        <rect x="14" y="3" width="7" height="7" rx="1.5"></rect>
        <rect x="14" y="14" width="7" height="7" rx="1.5"></rect>
        <rect x="3" y="14" width="7" height="7" rx="1.5"></rect>
      </svg>
    )},
    { id: "find-jobs", label: "Find jobs", badge: hasResume ? highMatchCount : totalJobsCount, icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
    )},
    { id: "job-alerts", label: "Job alerts", icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
        <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
      </svg>
    )},
    { id: "my-applications", label: "My applications", badge: pipelineCount > 0 ? pipelineCount : undefined, icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M9 11l3 3L22 4"></path>
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
      </svg>
    )},
    { id: "follow-ups", label: "Follow-ups", icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <line x1="22" y1="2" x2="11" y2="13"></line>
        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
      </svg>
    )},
    { id: "companies", label: "Companies", tag: "8 ATS", icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="4" y="2" width="16" height="20" rx="2" ry="2"></rect>
        <line x1="9" y1="22" x2="9" y2="22.01"></line>
        <line x1="15" y1="22" x2="15" y2="22.01"></line>
        <line x1="9" y1="18" x2="9" y2="18.01"></line>
        <line x1="15" y1="18" x2="15" y2="18.01"></line>
        <line x1="9" y1="14" x2="9" y2="14.01"></line>
        <line x1="15" y1="14" x2="15" y2="14.01"></line>
      </svg>
    )},
    { id: "insights", label: "Insights", icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <line x1="18" y1="20" x2="18" y2="10"></line>
        <line x1="12" y1="20" x2="12" y2="4"></line>
        <line x1="6" y1="20" x2="6" y2="14"></line>
      </svg>
    )},
    { id: "resume", label: "Résumé", hasDot: hasResume, icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
        <line x1="16" y1="13" x2="8" y2="13"></line>
        <line x1="16" y1="17" x2="8" y2="17"></line>
      </svg>
    )},
    { id: "files", label: "Files", icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
      </svg>
    )},
    { id: "settings", label: "Settings", icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="3"></circle>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
      </svg>
    )}
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
          <a
            key={item.id}
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
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="ats-indicator">
          <span className="pulse-dot"></span>
          <span>8 ATS Live Connectors</span>
        </div>
      </div>
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

function UploadDropzone({ onFileSelected, onSampleSelected, isProcessing, fileInputRef }) {
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
        <div className="step-node-circle">{currentStep > 1 ? "✓" : "1"}</div>
        <div className="step-text-group">
          <span className="step-heading">Upload résumé</span>
          <span className="step-subheading">Add your latest résumé</span>
        </div>
      </div>

      <div className="step-connector connector-1-2" style={{ background: currentStep >= 2 ? "#10B981" : "#2563EB" }}></div>

      <div className={`step-item ${currentStep === 2 ? "active" : currentStep > 2 ? "completed" : ""}`}>
        <div className="step-node-circle">{currentStep > 2 ? "✓" : "2"}</div>
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
        <div className="step-node-circle">{currentStep >= 3 ? "✓" : "3"}</div>
        <div className="step-text-group">
          <span className="step-heading">Find matching jobs</span>
          <span className="step-subheading">Discover roles tailored to you</span>
        </div>
      </div>
    </div>
  );
}

function NextStepsSection({ resume, matchedCount, onViewJobs, onChangeResume }) {
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
                <span className="active-badge">✓ Active Profile</span>
                <span className="file-name-label">{resume.filename}</span>
              </div>
              <h3 className="candidate-name">{resume.candidate_name}</h3>
              <p className="candidate-meta">
                {(resume.target_roles && resume.target_roles[0]) || "Software Engineer"} •{" "}
                {resume.years_of_experience > 0 ? `${resume.years_of_experience}+ yrs` : resume.seniority_level}
              </p>
              <div className="candidate-quick-skills">
                {resume.skills.slice(0, 5).map((s, i) => (
                  <span key={i} className="quick-skill-tag">
                    {s}
                  </span>
                ))}
                {resume.skills.length > 5 && (
                  <span className="quick-skill-tag">+{resume.skills.length - 5} more</span>
                )}
              </div>
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

function formatJobAge(dateStr) {
  if (!dateStr) return "2d ago";
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return "2d ago";
    const diffDays = Math.floor((new Date() - d) / (1000 * 60 * 60 * 24));
    if (diffDays <= 0) return "today";
    if (diffDays === 1) return "1d ago";
    if (diffDays < 7) return `${diffDays}d ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
    return `${diffDays}d ago`;
  } catch {
    return "2d ago";
  }
}

function JobCard({ job, inPipeline, onTogglePipeline, onViewDetails }) {
  const plat = (job.platform || "ATS").toLowerCase();

  // Matched keyword for display (e.g. "devops", "kubernetes", "python", "aws")
  let matchedKeyword = "devops";
  if (job.matched_skills && job.matched_skills.length > 0) {
    matchedKeyword = job.matched_skills[0].toLowerCase();
  } else if (job.extracted_skills && job.extracted_skills.length > 0) {
    matchedKeyword = job.extracted_skills[0].toLowerCase();
  } else if (job.title) {
    const lower = job.title.toLowerCase();
    if (lower.includes("devops") || lower.includes("sre")) matchedKeyword = "devops";
    else if (lower.includes("security")) matchedKeyword = "devops";
    else if (lower.includes("cloud")) matchedKeyword = "cloud";
    else if (lower.includes("react") || lower.includes("frontend")) matchedKeyword = "react";
    else if (lower.includes("python") || lower.includes("backend")) matchedKeyword = "python";
    else matchedKeyword = "skills";
  }

  const postingAge = formatJobAge(job.posted_at || job.created_at);

  return (
    <div className="job-card-uploaded-style">
      {/* Header Row: Circular Avatar + Title with Link + Subtitle */}
      <div className="card-header-row">
        <div className="company-avatar-circle" title={job.company || "Company"}>
          <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
            <path d="M14 3C8.48 3 4 7.48 4 13C4 17.2 6.58 20.8 10.25 22.3C9.45 20.1 9 17.6 9 15C9 9.5 12.8 4.9 18 3.5C16.7 3.2 15.4 3 14 3Z" fill="#10B981" />
            <path d="M14 27C19.52 27 24 22.52 24 17C24 12.8 21.42 9.2 17.75 7.7C18.55 9.9 19 12.4 19 15C19 20.5 15.2 25.1 10 26.5C11.3 26.8 12.6 27 14 27Z" fill="#06B6D4" />
          </svg>
        </div>

        <div className="card-title-block">
          <div className="title-and-link">
            <h3 className="job-card-title" title={job.title}>{job.title}</h3>
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="external-link-icon"
              title="Open original job posting"
              onClick={(e) => e.stopPropagation()}
            >
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                <polyline points="15 3 21 3 21 9"></polyline>
                <line x1="10" y1="14" x2="21" y2="3"></line>
              </svg>
            </a>
          </div>
          <div className="job-card-subtitle">
            {job.company || "jobgether"} · {job.location || "Remote"}
          </div>
          {job.visa_sponsored && (
            <span
              className="visa-sponsored-badge"
              title={`Employer legal name matches the official UK Sponsor Register as ${job.visa_sponsor_registered_names?.join(", ") || "a listed organisation"}, and the role location is confirmed UK. This does not guarantee sponsorship for this vacancy.`}
            >
              UK Sponsor Listed
            </span>
          )}
          {job.visa_sponsored && job.visa_sponsor_registered_names?.length > 0 && (
            <span className="visa-sponsor-match-name">
              UK register: {job.visa_sponsor_registered_names.join(", ")}
            </span>
          )}
        </div>
      </div>

      {/* Meta Row: [Lever] 2d ago · matched devops */}
      <div className="card-meta-row">
        <span className="platform-tag-pill">{plat}</span>
        <span className="meta-age-text">{postingAge}</span>
        <span className="matched-skill-text">
          · matched <span className="matched-skill-highlight">{matchedKeyword}</span>
        </span>
      </div>

      {/* Action Row: + Add to pipeline / In pipeline & Evaluate button */}
      <div className="card-action-row">
        <button
          type="button"
          className={`btn-pipeline ${inPipeline ? "in-pipeline" : ""}`}
          onClick={onTogglePipeline}
        >
          {inPipeline ? (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
              <span>In pipeline</span>
            </>
          ) : (
            <>
              <span>+ Add to pipeline</span>
            </>
          )}
        </button>

        <button
          type="button"
          className="btn-evaluate"
          onClick={onViewDetails}
        >
          <span>Evaluate</span>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
          </svg>
        </button>
      </div>
    </div>
  );
}

function JobDetailModal({ job, onClose }) {
  const plat = (job.platform || "ATS").toLowerCase();

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-company-info">
            <span className={`modal-ats-badge ${plat}`}>{plat.toUpperCase()}</span>
            <h2 className="modal-title">{job.title}</h2>
            <p className="modal-subtitle">
              {job.company} • {job.location || "Remote"} • {job.employment_type || "Full-time"}
            </p>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="modal-body">
          {job.match_score && (
            <div style={{ background: "#ECFDF5", border: "1px solid #A7F3D0", padding: "14px", borderRadius: "12px", marginBottom: "18px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                <strong style={{ color: "#065F46", fontSize: "0.95rem" }}>
                  Match Score: {job.match_score}% ({job.fit_level})
                </strong>
                <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#047857" }}>Based on your Résumé</span>
              </div>
              <p style={{ fontSize: "0.82rem", color: "#065F46", marginBottom: "6px" }}>
                <strong>Matching Skills:</strong> {(job.matched_skills || []).join(", ") || "General role match"}
              </p>
              {job.missing_skills && job.missing_skills.length > 0 && (
                <p style={{ fontSize: "0.82rem", color: "#4B5563" }}>
                  <strong>Skills to Highlight:</strong> {job.missing_skills.join(", ")}
                </p>
              )}
            </div>
          )}

          <h4 className="modal-section-heading">Job Description</h4>
          <div className="modal-job-description">
            {job.description || "No full description text available."}
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close
          </button>
          <a href={job.url} target="_blank" rel="noopener noreferrer" className="btn-primary-apply">
            <span>Apply on {job.company} Career Portal</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
          </a>
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

const JOB_SECTORS = [
  { value: "technology", label: "IT & Technology", pattern: /\b(software|information technology|technology|tech|cloud computing|cyber[\s-]?security|data science|machine learning|artificial intelligence|saas|developer|programming|telecommunications)\b/i },
  { value: "healthcare", label: "Healthcare & Life Sciences", pattern: /\b(healthcare|health care|clinical|hospital|nurs(?:e|ing)|medical|pharma(?:ceutical)?|biotech|life sciences|patient care|medicine)\b/i },
  { value: "manufacturing", label: "Manufacturing & Industrial", pattern: /\b(manufactur(?:e|er|ers|ing)|factory|factories|industrial|assembly line|production operator|production engineer|plant operations|machinist|fabrication)\b/i },
  { value: "finance", label: "Finance & Banking", pattern: /\b(finance|financial services|banking|bank|accounting|investment|insurance|fintech|payments|audit|actuarial)\b/i },
  { value: "retail", label: "Retail & E-commerce", pattern: /\b(retail|e[\s-]?commerce|store operations|merchandising|point of sale|consumer goods)\b/i },
  { value: "education", label: "Education", pattern: /\b(education|educational|school|university|teaching|teacher|academic|curriculum|student services)\b/i },
  { value: "energy", label: "Energy & Utilities", pattern: /\b(energy|utilities|utility|renewable|solar|wind power|oil and gas|power generation|electric grid)\b/i },
  { value: "media", label: "Media & Entertainment", pattern: /\b(media|entertainment|broadcast|journalism|publishing|film|music industry|gaming|video production)\b/i },
  { value: "transport", label: "Transport & Logistics", pattern: /\b(transportation|logistics|supply chain|freight|shipping|warehousing|aviation|airline|fleet|delivery operations)\b/i },
  { value: "hospitality", label: "Hospitality & Tourism", pattern: /\b(hospitality|tourism|hotel|restaurant|food service|travel industry|guest services)\b/i },
  { value: "government", label: "Government & Public Sector", pattern: /\b(government|public sector|civil service|municipal|public administration|defen[cs]e)\b/i },
  { value: "construction", label: "Construction & Real Estate", pattern: /\b(construction|real estate|property development|architecture|building trades|civil engineering)\b/i },
  { value: "professional-services", label: "Professional Services & Consulting", pattern: /\b(consulting|consultancy|professional services|legal services|law firm|management advisory|business services)\b/i }
];

function jobMatchesSector(job, sectorValue) {
  if (sectorValue === "all") return true;
  const sector = JOB_SECTORS.find((item) => item.value === sectorValue);
  if (!sector) return true;

  const listingText = [job.title, job.department, job.company, job.description]
    .filter(Boolean)
    .join(" ");
  return sector.pattern.test(listingText);
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
  if (!job.posted_at) return null;

  const relativeDate = job.posted_at.match(/posted\s+(\d+)\s+(day|days|hour|hours|week|weeks)\s+ago/i);
  if (relativeDate) {
    const [, countText, unit] = relativeDate;
    const count = Number(countText);
    const multiplier = unit.toLowerCase().startsWith("hour") ? 1 / 24
      : unit.toLowerCase().startsWith("week") ? 7 : 1;
    return new Date(Date.now() - count * multiplier * 24 * 60 * 60 * 1000);
  }

  const parsed = new Date(job.posted_at);
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
  const [selectedPlatform, setSelectedPlatform] = useState("all");
  const [selectedLocation, setSelectedLocation] = useState("");
  const [selectedEmploymentType, setSelectedEmploymentType] = useState("all");
  const [selectedWorkMode, setSelectedWorkMode] = useState("all");
  const [selectedSector, setSelectedSector] = useState("all");
  const [visaSponsoredOnly, setVisaSponsoredOnly] = useState(false);
  const [freshOnly, setFreshOnly] = useState(true);
  const [discoverySubmitted, setDiscoverySubmitted] = useState(false);
  const [salaryError, setSalaryError] = useState("");
  const [discoveryFilters, setDiscoveryFilters] = useState({
    roles: "",
    location: "",
    postedWithin: "7",
    sources: ["greenhouse", "lever", "ashby", "workday", "workable", "oracle_cloud", "breezyhr", "pinpoint"],
    workModes: [],
    employmentType: "all",
    sector: "all",
    visaSponsoredOnly: false,
    relocationAssistance: false,
    salaryMin: "",
    salaryMax: "",
    salaryCurrency: "USD",
    techStack: "",
    seniority: "",
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
    requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  // When a resume is present, strictly show jobs matching >= 85%
  const sourcePool = useMemo(() => {
    if (resume) {
      return (matchedJobs || []).filter((j) => (j.match_score || 0) >= 85);
    }
    return jobs;
  }, [resume, matchedJobs, jobs]);

  // Extract unique companies from sourcePool
  const companiesList = useMemo(() => {
    const set = new Set();
    sourcePool.forEach((j) => {
      if (j.company) set.add(j.company);
    });
    return Array.from(set).sort();
  }, [sourcePool]);

  const employmentTypesList = useMemo(() => {
    const types = new Set();
    sourcePool.forEach((job) => {
      if (job.employment_type) types.add(job.employment_type.trim());
    });
    return Array.from(types).filter(Boolean).sort((a, b) => a.localeCompare(b));
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
          if (ageInDays < 0 || ageInDays > Number(discoveryFilters.postedWithin)) {
            return false;
          }
        }

        if (!discoveryFilters.sources.includes((j.platform || "").toLowerCase())) {
          return false;
        }

        if (
          discoveryFilters.employmentType !== "all"
          && (j.employment_type || "").toLowerCase() !== discoveryFilters.employmentType.toLowerCase()
        ) {
          return false;
        }

        if (!jobMatchesSector(j, discoveryFilters.sector)) {
          return false;
        }

        if (discoveryFilters.visaSponsoredOnly && !j.visa_sponsored) {
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

        if (
          discoveryFilters.seniority
          && !new RegExp(`\\b${discoveryFilters.seniority}\\b`, "i").test(jobText)
        ) {
          return false;
        }

        const keywords = splitFilterTerms(discoveryFilters.keywords);
        if (keywords.length && !keywords.every((term) => jobText.includes(term))) {
          return false;
        }
      }

      if (resume) {
        const jobText = getJobSearchText(j);
        if (!jobMatchesSector(j, selectedSector)) {
          return false;
        }

        const locationQuery = selectedLocation.trim().toLowerCase();
        if (
          locationQuery
          && !(j.location || "").toLowerCase().includes(locationQuery)
          && !(locationQuery === "remote" && j.is_remote)
        ) {
          return false;
        }

        if (
          selectedEmploymentType !== "all"
          && (j.employment_type || "").toLowerCase() !== selectedEmploymentType.toLowerCase()
        ) {
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

        if (visaSponsoredOnly && !j.visa_sponsored) {
          return false;
        }
      }

      // Platform filter
      if (selectedPlatform !== "all" && (j.platform || "").toLowerCase() !== selectedPlatform.toLowerCase()) {
        return false;
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
    selectedPlatform,
    selectedCompany,
    selectedLocation,
    selectedEmploymentType,
    selectedWorkMode,
    selectedSector,
    visaSponsoredOnly,
    filterQuery,
    resume,
    discoveryFilters
  ]);

  const allVisibleInPipeline = useMemo(() => {
    if (filtered.length === 0) return false;
    return filtered.every((j) => pipelineJobIds.has(j.id));
  }, [filtered, pipelineJobIds]);

  return (
    <div className="content-container">
      {/* High Match Banner if resume uploaded */}
      {resume && (
        <div className="high-match-banner">
          <div className="high-match-banner-content">
            <div className="high-match-badge-circle">85%+</div>
            <div className="high-match-text">
              High-compatibility roles detected for <strong>{resume.candidate_name || resume.filename}</strong>. Showing <strong>{filtered.length}</strong> verified job postings matching <strong>≥85%</strong> of your extracted skills.
            </div>
          </div>
          <button
            type="button"
            className="pill-filter-btn"
            style={{ background: "#FFFFFF", color: "var(--slate-700)" }}
            onClick={onRefresh}
          >
            🔄 Refresh ATS Feed
          </button>
        </div>
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
                placeholder="Software Engineer, Data Analyst..."
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
                <label htmlFor="discovery-seniority">Level / Seniority</label>
                <select
                  id="discovery-seniority"
                  value={discoveryFilters.seniority}
                  onChange={(event) => updateDiscoveryFilter("seniority", event.target.value)}
                >
                  <option value="">Any level</option>
                  {["Intern", "Junior", "Entry", "Mid", "Senior", "Lead", "Principal", "Director"].map((level) => (
                    <option key={level} value={level.toLowerCase()}>{level}</option>
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

            <div className="discovery-row">
              <div className="discovery-field">
                <label htmlFor="discovery-employment-type">Employment type</label>
                <select
                  id="discovery-employment-type"
                  value={discoveryFilters.employmentType}
                  onChange={(event) => updateDiscoveryFilter("employmentType", event.target.value)}
                >
                  <option value="all">Any employment type</option>
                  {employmentTypesList.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>

              <div className="discovery-field">
                <label htmlFor="discovery-sector">Sector</label>
                <select
                  id="discovery-sector"
                  value={discoveryFilters.sector}
                  onChange={(event) => updateDiscoveryFilter("sector", event.target.value)}
                >
                  <option value="all">Any sector</option>
                  {JOB_SECTORS.map((sector) => (
                    <option key={sector.value} value={sector.value}>{sector.label}</option>
                  ))}
                </select>
                <span className="discovery-hint">Inferred from the job title, department, employer, and listing text.</span>
              </div>

              <fieldset className="discovery-field discovery-choice-group">
                <legend>Visa sponsor country: United Kingdom</legend>
                <label className="discovery-checkbox">
                  <input
                    type="checkbox"
                    checked={discoveryFilters.visaSponsoredOnly}
                    onChange={(event) => updateDiscoveryFilter("visaSponsoredOnly", event.target.checked)}
                  />
                  <span>Only jobs matching the employer and UK location</span>
                </label>
                <span className="discovery-hint">Checks the UK Worker and Temporary Worker register and the job location. Unspecified or ambiguous locations are excluded. A listed employer is not a guarantee that a specific role offers sponsorship.</span>
              </fieldset>
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
      {/* Top Filter Bar for résumé-matched listings */}
      <div className="find-jobs-topbar">
        {/* Search input with search icon: Filter results... */}
        <div className="filter-input-wrapper">
          <span className="filter-search-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
          </span>
          <input
            type="text"
            className="filter-results-input"
            placeholder="Filter results..."
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
          />
        </div>

        <div className="filter-input-wrapper">
          <input
            type="text"
            className="filter-results-input"
            placeholder="Location..."
            aria-label="Filter by location"
            value={selectedLocation}
            onChange={(event) => setSelectedLocation(event.target.value)}
          />
        </div>

        {/* Fresh pill button */}
        <button
          type="button"
          className={`pill-filter-btn ${freshOnly ? "active" : ""}`}
          onClick={() => setFreshOnly(!freshOnly)}
          title="Toggle recently posted roles"
        >
          <span>Fresh</span>
        </button>

        {/* Company filter dropdown */}
        <div className="pill-select-wrapper">
          <select
            className="pill-select"
            value={selectedCompany}
            onChange={(e) => setSelectedCompany(e.target.value)}
          >
            <option value="all">Company</option>
            {companiesList.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        <div className="pill-select-wrapper">
          <select
            className="pill-select"
            aria-label="Filter by employment type"
            value={selectedEmploymentType}
            onChange={(event) => setSelectedEmploymentType(event.target.value)}
          >
            <option value="all">Employment type</option>
            {employmentTypesList.map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>

        <div className="pill-select-wrapper">
          <select
            className="pill-select"
            aria-label="Filter by sector"
            value={selectedSector}
            onChange={(event) => setSelectedSector(event.target.value)}
          >
            <option value="all">Sector</option>
            {JOB_SECTORS.map((sector) => (
              <option key={sector.value} value={sector.value}>{sector.label}</option>
            ))}
          </select>
        </div>

        <div className="pill-select-wrapper">
          <select
            className="pill-select"
            aria-label="Filter by work mode"
            value={selectedWorkMode}
            onChange={(event) => setSelectedWorkMode(event.target.value)}
          >
            <option value="all">Work mode</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="on-site">On-site</option>
          </select>
        </div>

        <button
          type="button"
          className={`pill-filter-btn ${visaSponsoredOnly ? "active" : ""}`}
          aria-pressed={visaSponsoredOnly}
          onClick={() => setVisaSponsoredOnly((current) => !current)}
          title="Show jobs matching both an employer on the United Kingdom Worker and Temporary Worker register and a UK job location."
        >
          <span>UK Sponsor Listed</span>
        </button>

        {/* Platform filter dropdown */}
        <div className="pill-select-wrapper">
          <select
            className="pill-select"
            value={selectedPlatform}
            onChange={(e) => setSelectedPlatform(e.target.value)}
          >
            <option value="all">All ATS</option>
            {platforms.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        {/* + Add all {count} pill button */}
        <button
          type="button"
          className={`btn-add-all ${allVisibleInPipeline ? "all-added" : ""}`}
          onClick={() => onAddAllToPipeline(filtered)}
        >
          {allVisibleInPipeline ? (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
              <span>In pipeline</span>
            </>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
              <span>+ Add all {filtered.length}</span>
            </>
          )}
        </button>
      </div>
      </>
      )}

      {/* 3-Column Jobs Grid */}
      {(resume || discoverySubmitted) && (
      <div className="jobs-grid-3col" ref={resultsRef}>
        {filtered.length === 0 ? (
          <div className="empty-results-box" style={{ gridColumn: "1 / -1" }}>
            <h4>No roles match your filter criteria</h4>
            <p>Try clearing search keywords or selecting "All ATS".</p>
          </div>
        ) : (
          filtered.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              inPipeline={pipelineJobIds.has(job.id)}
              onTogglePipeline={() => onTogglePipeline(job.id)}
              onViewDetails={() => onSelectJob(job)}
            />
          ))
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
          <p className="page-subtitle">Live public APIs and feed connectors across all 8 major applicant tracking systems.</p>
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
                Status: {p.status || "ready"}
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

function ResumeProfileView({ resume, onUploadNew }) {
  if (!resume) {
    return (
      <div className="content-container">
        <div style={{ background: "#FFFFFF", borderRadius: "16px", border: "1px dashed #CBD5E1", padding: "48px", textAlign: "center" }}>
          <h3 style={{ fontSize: "1.15rem", color: "#1E293B", marginBottom: "8px" }}>No résumé uploaded yet</h3>
          <p style={{ fontSize: "0.88rem", color: "#64748B", marginBottom: "18px" }}>
            Upload your résumé on the Home tab to see your extracted skill breakdown.
          </p>
          <button type="button" className="btn-choose-resume" onClick={onUploadNew}>
            Upload Résumé Now
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="content-container">
      <div className="section-page-header">
        <div>
          <span className="hero-tag">PARSED PROFILE</span>
          <h1 className="page-title">Candidate Résumé Insights</h1>
          <p className="page-subtitle">Extracted candidate entities and skills taxonomy.</p>
        </div>
        <button type="button" className="btn-choose-resume" onClick={onUploadNew}>
          <span>Upload New Résumé</span>
        </button>
      </div>

      <div className="profile-card">
        <div className="profile-header-grid">
          <div className="profile-avatar-circle">
            {(resume.candidate_name || "U").charAt(0)}
          </div>
          <div>
            <h2 style={{ fontSize: "1.6rem", fontWeight: 800, color: "#0F172A", marginBottom: "4px" }}>
              {resume.candidate_name}
            </h2>
            <p style={{ fontSize: "0.95rem", color: "#475569", marginBottom: "10px" }}>
              {(resume.target_roles || []).join(" • ")} •{" "}
              {resume.years_of_experience > 0 ? `${resume.years_of_experience}+ years experience` : resume.seniority_level}
            </p>
            <div style={{ display: "flex", gap: "16px", fontSize: "0.84rem", color: "#64748B", flexWrap: "wrap" }}>
              <span>📧 {resume.email}</span>
              <span>📞 {resume.phone}</span>
              {resume.linkedin && <span>🔗 {resume.linkedin}</span>}
              {resume.github && <span>🐙 {resume.github}</span>}
            </div>
          </div>
        </div>

        <div style={{ borderTop: "1px solid #E2E8F0", paddingTop: "24px" }}>
          <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#0F172A", marginBottom: "16px" }}>
            Skills Taxonomy ({resume.total_skills} skills extracted)
          </h3>
          {Object.entries(resume.categorized_skills || {}).map(([cat, sks]) => (
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
          ))}
        </div>
      </div>
    </div>
  );
}

function InsightsView() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/stats`)
      .then((r) => r.json())
      .then(setStats)
      .catch(console.error);
  }, []);

  if (!stats) return <div className="content-container">Loading analytics...</div>;

  return (
    <div className="content-container">
      <h1 className="page-title">Job Market & Skill Insights</h1>
      <p className="page-subtitle">Real-time stats from SQLite storage across all 8 ATS networks.</p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "20px", margin: "24px 0" }}>
        <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: "16px", padding: "24px" }}>
          <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#64748B" }}>TOTAL STORED LIVE JOBS</span>
          <h2 style={{ fontSize: "2.2rem", fontWeight: 800, color: "#2563EB", marginTop: "6px" }}>
            {stats.total_active_jobs}
          </h2>
          <p style={{ fontSize: "0.78rem", color: "#10B981", marginTop: "4px" }}>✓ Stored in local database</p>
        </div>

        <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: "16px", padding: "24px" }}>
          <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#64748B" }}>ACTIVE PLATFORMS</span>
          <h2 style={{ fontSize: "2.2rem", fontWeight: 800, color: "#0F172A", marginTop: "6px" }}>8 / 8</h2>
          <p style={{ fontSize: "0.78rem", color: "#64748B", marginTop: "4px" }}>
            Greenhouse, Ashby, Workday, Lever, Workable, Oracle Cloud, Breezy, Pinpoint
          </p>
        </div>
      </div>

      <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: "16px", padding: "24px" }}>
        <h3 style={{ fontSize: "1.1rem", fontWeight: 800, color: "#0F172A", marginBottom: "16px" }}>
          Most In-Demand Skills Across Verified Jobs
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

// Render React App
const rootElement = document.getElementById("root");
if (rootElement) {
  const root = ReactDOM.createRoot(rootElement);
  root.render(<App />);
}

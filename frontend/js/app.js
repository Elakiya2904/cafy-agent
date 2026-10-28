// ==========================================================================
// CAFY AGENT • FRONTEND APPLICATION LOGIC
// ==========================================================================

const API_BASE = window.location.origin;

// Application State
const state = {
  currentResume: null,
  allJobs: [],
  matchedJobs: [],
  activePlatformFilter: 'all',
  minScoreFilter: 0,
  searchQuery: '',
  remoteOnly: false,
  platforms: []
};

// DOM Elements
const elements = {
  // Navigation
  navItems: document.querySelectorAll('.sidebar-nav .nav-item'),
  tabPanes: document.querySelectorAll('.tab-pane'),
  sidebarJobCount: document.getElementById('sidebar-job-count'),
  sidebarResumeDot: document.getElementById('sidebar-resume-dot'),

  // Upload & Stepper
  dropzone: document.getElementById('dropzone'),
  fileInput: document.getElementById('resume-file-input'),
  btnBrowse: document.getElementById('btn-browse-file'),
  step1: document.getElementById('step-node-1'),
  step2: document.getElementById('step-node-2'),
  step3: document.getElementById('step-node-3'),
  connector1: document.getElementById('connector-1'),
  connector2: document.getElementById('connector-2'),
  sampleChips: document.querySelectorAll('.btn-sample-chip'),

  // Resume Status Card
  emptyResumeState: document.getElementById('empty-resume-state'),
  activeResumeState: document.getElementById('active-resume-state'),
  statusFilename: document.getElementById('status-filename'),
  statusCandidateName: document.getElementById('status-candidate-name'),
  statusCandidateMeta: document.getElementById('status-candidate-meta'),
  statusQuickSkills: document.getElementById('status-quick-skills'),
  statusMatchesCount: document.getElementById('status-matches-count'),
  btnJumpMatches: document.getElementById('btn-jump-matches'),
  btnChangeResume: document.getElementById('btn-change-resume'),

  // Matched Section
  homeMatchedSection: document.getElementById('home-matched-section'),
  bannerSkillsCount: document.getElementById('banner-skills-count'),
  bannerSkillsChips: document.getElementById('banner-skills-chips'),
  atsFilterTabs: document.getElementById('ats-filter-tabs'),
  matchSearchInput: document.getElementById('match-search-input'),
  scoreFilterSelect: document.getElementById('score-filter-select'),
  remoteFilterToggle: document.getElementById('remote-filter-toggle'),
  matchedJobsContainer: document.getElementById('matched-jobs-container'),
  btnTriggerScraper: document.getElementById('btn-trigger-scraper'),

  // Directory / Find Jobs Tab
  allJobsContainer: document.getElementById('all-jobs-container'),
  dirSearchInput: document.getElementById('dir-search-input'),
  dirPlatformSelect: document.getElementById('dir-platform-select'),
  btnRefreshAllJobs: document.getElementById('btn-refresh-all-jobs'),

  // Companies Tab
  platformsCatalogGrid: document.getElementById('platforms-catalog-grid'),
  btnOpenAddCompany: document.getElementById('btn-open-add-company'),
  addCompanyModal: document.getElementById('add-company-modal'),
  closeAddCompanyBtn: document.getElementById('close-add-company-btn'),
  cancelAddCompanyBtn: document.getElementById('cancel-add-company-btn'),
  addCompanyForm: document.getElementById('add-company-form'),
  newCompanyPlatform: document.getElementById('new-company-platform'),
  workdayExtraFields: document.getElementById('workday-extra-fields'),

  // Modal Detail
  jobDetailModal: document.getElementById('job-detail-modal'),
  modalCloseBtn: document.getElementById('modal-close-btn'),
  modalBtnDismiss: document.getElementById('modal-btn-dismiss'),
  modalPlatformBadge: document.getElementById('modal-platform-badge'),
  modalJobTitle: document.getElementById('modal-job-title'),
  modalJobCompany: document.getElementById('modal-job-company'),
  modalMatchBox: document.getElementById('modal-match-box'),
  modalJobDesc: document.getElementById('modal-job-desc'),
  modalBtnApply: document.getElementById('modal-btn-apply'),

  // Resume Tab
  resumeProfileDetails: document.getElementById('resume-profile-details'),
  btnReuploadProfile: document.getElementById('btn-reupload-profile'),

  // Insights Tab
  insightsMetricsContainer: document.getElementById('insights-metrics-container'),

  // Toasts
  toastContainer: document.getElementById('toast-container')
};

// ==========================================================================
// INITIALIZATION
// ==========================================================================
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupUploadDropzone();
  setupSampleResumes();
  setupFilters();
  setupModals();

  // Load platforms and initial jobs
  await loadPlatforms();
  await loadInitialJobs();
  await checkCurrentSession();
});

// Toast Notifications
function showToast(message, duration = 3500) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Navigation Tab Handler
function setupNavigation() {
  elements.navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const tabId = item.getAttribute('data-tab');
      switchTab(tabId);
    });
  });

  if (elements.btnJumpMatches) {
    elements.btnJumpMatches.addEventListener('click', () => {
      elements.homeMatchedSection.scrollIntoView({ behavior: 'smooth' });
    });
  }

  if (elements.btnReuploadProfile) {
    elements.btnReuploadProfile.addEventListener('click', () => {
      switchTab('home');
      elements.fileInput.click();
    });
  }
}

function switchTab(tabId) {
  elements.navItems.forEach(nav => {
    if (nav.getAttribute('data-tab') === tabId) {
      nav.classList.add('active');
    } else {
      nav.classList.remove('active');
    }
  });

  elements.tabPanes.forEach(pane => {
    if (pane.id === `tab-${tabId}`) {
      pane.classList.add('active');
    } else {
      pane.classList.remove('active');
    }
  });

  if (tabId === 'find-jobs') {
    renderDirectoryJobs();
  } else if (tabId === 'companies') {
    renderPlatformsCatalog();
  } else if (tabId === 'resume') {
    renderResumeProfileView();
  } else if (tabId === 'insights') {
    loadInsights();
  }
}

// ==========================================================================
// UPLOAD & RESUME PARSING
// ==========================================================================
function setupUploadDropzone() {
  const dropzone = elements.dropzone;
  const fileInput = elements.fileInput;
  const btnBrowse = elements.btnBrowse;

  btnBrowse.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  dropzone.addEventListener('click', () => {
    fileInput.click();
  });

  fileInput.addEventListener('change', async (e) => {
    if (e.target.files && e.target.files[0]) {
      await handleFileUpload(e.target.files[0]);
    }
  });

  // Drag and Drop
  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('drag-active');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('drag-active');
    }, false);
  });

  dropzone.addEventListener('drop', async (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length > 0) {
      await handleFileUpload(files[0]);
    }
  });

  if (elements.btnChangeResume) {
    elements.btnChangeResume.addEventListener('click', () => {
      fileInput.click();
    });
  }
}

function setupSampleResumes() {
  elements.sampleChips.forEach(chip => {
    chip.addEventListener('click', async (e) => {
      e.stopPropagation();
      const sampleKey = chip.getAttribute('data-sample');
      await handleSampleResume(sampleKey);
    });
  });
}

// Stepper Progress Transitions
function updateStepper(step) {
  if (step === 1) {
    elements.step1.className = 'step-item step-1 active';
    elements.step2.className = 'step-item step-2';
    elements.step3.className = 'step-item step-3';
    elements.connector1.className = 'step-connector connector-1-2';
    elements.connector2.className = 'step-connector connector-2-3';
  } else if (step === 2) {
    elements.step1.className = 'step-item step-1 completed';
    elements.step1.querySelector('.step-node-circle').textContent = '✓';
    elements.step2.className = 'step-item step-2 active';
    elements.step3.className = 'step-item step-3';
    elements.connector1.style.background = '#10B981';
    elements.connector2.style.borderTop = '2px solid #2563EB';
  } else if (step === 3) {
    elements.step1.className = 'step-item step-1 completed';
    elements.step1.querySelector('.step-node-circle').textContent = '✓';
    elements.step2.className = 'step-item step-2 completed';
    elements.step2.querySelector('.step-node-circle').textContent = '✓';
    elements.step3.className = 'step-item step-3 completed';
    elements.step3.querySelector('.step-node-circle').textContent = '✓';
    elements.connector1.style.background = '#10B981';
    elements.connector2.style.borderTop = '2px solid #10B981';
  }
}

async function handleFileUpload(file) {
  try {
    updateStepper(2);
    showToast(`Analyzing ${file.name}... Extracting skills...`);

    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(`${API_BASE}/api/resume/upload`, {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      throw new Error(`Upload failed with status ${res.status}`);
    }

    const data = await res.json();
    onCandidateDataLoaded(data);
  } catch (err) {
    console.error(err);
    showToast(`Error processing file: ${err.message}`);
    updateStepper(1);
  }
}

async function handleSampleResume(sampleKey) {
  try {
    updateStepper(2);
    showToast(`Loading demo profile (${sampleKey})...`);

    const formData = new FormData();
    formData.append('sample_key', sampleKey);

    const res = await fetch(`${API_BASE}/api/resume/sample`, {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      throw new Error(`Failed to load sample resume.`);
    }

    const data = await res.json();
    onCandidateDataLoaded(data);
  } catch (err) {
    console.error(err);
    showToast(`Error loading sample: ${err.message}`);
    updateStepper(1);
  }
}

function onCandidateDataLoaded(data) {
  state.currentResume = data.resume;
  state.matchedJobs = data.matched_jobs;
  
  updateStepper(3);
  showToast(`Found ${data.matched_jobs.length} tailored roles across 8 ATS platforms!`);

  // Activate Status Card on Home
  elements.emptyResumeState.classList.add('hidden');
  elements.activeResumeState.classList.remove('hidden');

  elements.statusFilename.textContent = data.resume.filename;
  elements.statusCandidateName.textContent = data.resume.candidate_name;
  elements.statusCandidateMeta.textContent = `${data.resume.target_roles[0] || 'Software Engineer'} • ${data.resume.years_of_experience > 0 ? data.resume.years_of_experience + '+ yrs' : data.resume.seniority_level}`;
  elements.statusMatchesCount.textContent = data.matched_jobs.length;

  // Render top quick skill pills on status card
  elements.statusQuickSkills.innerHTML = '';
  data.resume.skills.slice(0, 5).forEach(sk => {
    const pill = document.createElement('span');
    pill.className = 'quick-skill-tag';
    pill.textContent = sk;
    elements.statusQuickSkills.appendChild(pill);
  });
  if (data.resume.skills.length > 5) {
    const morePill = document.createElement('span');
    morePill.className = 'quick-skill-tag';
    morePill.textContent = `+${data.resume.skills.length - 5} more`;
    elements.statusQuickSkills.appendChild(morePill);
  }

  // Sidebar indicator
  elements.sidebarResumeDot.classList.add('active');

  // Populate banner skills
  elements.bannerSkillsCount.textContent = data.resume.total_skills;
  elements.bannerSkillsChips.innerHTML = '';
  data.resume.skills.forEach(sk => {
    const chip = document.createElement('span');
    chip.className = 'skill-chip';
    chip.textContent = sk;
    elements.bannerSkillsChips.appendChild(chip);
  });

  // Reveal Matched section & render cards
  elements.homeMatchedSection.classList.remove('hidden');
  updatePlatformTabCounts();
  renderMatchedJobs();

  // Smooth scroll down to matches
  setTimeout(() => {
    elements.homeMatchedSection.scrollIntoView({ behavior: 'smooth' });
  }, 350);
}

async function checkCurrentSession() {
  try {
    const res = await fetch(`${API_BASE}/api/resume/current`);
    const data = await res.json();
    if (data.resume) {
      onCandidateDataLoaded({
        resume: data.resume,
        matched_jobs: data.matched_jobs
      });
    }
  } catch (e) {
    console.log("No existing session.");
  }
}

// ==========================================================================
// PLATFORMS & INITIAL JOBS
// ==========================================================================
async function loadPlatforms() {
  try {
    const res = await fetch(`${API_BASE}/api/platforms`);
    const data = await res.json();
    state.platforms = data.platforms;
  } catch (e) {
    console.error("Failed to load platforms", e);
  }
}

async function loadInitialJobs() {
  try {
    const res = await fetch(`${API_BASE}/api/jobs`);
    const data = await res.json();
    state.allJobs = data.jobs;
    elements.sidebarJobCount.textContent = data.count;
    document.getElementById('count-all').textContent = data.count;
  } catch (e) {
    console.error("Failed to fetch initial jobs", e);
  }
}

function updatePlatformTabCounts() {
  const jobs = state.matchedJobs.length > 0 ? state.matchedJobs : state.allJobs;
  
  const counts = { all: jobs.length };
  state.platforms.forEach(p => { counts[p.id] = 0; });

  jobs.forEach(j => {
    const plat = (j.platform || '').toLowerCase();
    if (counts[plat] !== undefined) {
      counts[plat]++;
    }
  });

  for (const [plat, count] of Object.entries(counts)) {
    const countEl = document.getElementById(`count-${plat}`);
    if (countEl) countEl.textContent = count;
  }
}

// ==========================================================================
// FILTERS & JOB CARD RENDERING
// ==========================================================================
function setupFilters() {
  // ATS Platform Tabs
  const tabButtons = elements.atsFilterTabs.querySelectorAll('.ats-tab-btn');
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.activePlatformFilter = btn.getAttribute('data-platform');
      renderMatchedJobs();
    });
  });

  // Keyword Search
  elements.matchSearchInput.addEventListener('input', (e) => {
    state.searchQuery = e.target.value.toLowerCase().trim();
    renderMatchedJobs();
  });

  // Score threshold
  elements.scoreFilterSelect.addEventListener('change', (e) => {
    state.minScoreFilter = parseInt(e.target.value, 10) || 0;
    renderMatchedJobs();
  });

  // Remote toggle
  elements.remoteFilterToggle.addEventListener('change', (e) => {
    state.remoteOnly = e.target.checked;
    renderMatchedJobs();
  });

  // Scraper Refresh Trigger Button
  elements.btnTriggerScraper.addEventListener('click', async () => {
    elements.btnTriggerScraper.disabled = true;
    const icon = elements.btnTriggerScraper.querySelector('.spin-icon');
    if (icon) icon.style.animation = 'spin 1s linear infinite';
    showToast('Triggering parallel scrape across all 8 ATS boards...');

    try {
      const res = await fetch(`${API_BASE}/api/scrapers/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform: 'all' })
      });
      const data = await res.json();
      showToast(data.message);

      // Re-fetch jobs after brief delay
      setTimeout(async () => {
        await loadInitialJobs();
        if (state.currentResume) {
          const mRes = await fetch(`${API_BASE}/api/jobs/match`, { method: 'POST' });
          const mData = await mRes.json();
          state.matchedJobs = mData.matched_jobs;
          renderMatchedJobs();
        }
        elements.btnTriggerScraper.disabled = false;
        if (icon) icon.style.animation = '';
        showToast('Indexed latest roles from Greenhouse, Ashby, Lever, Workday, etc.');
      }, 4000);
    } catch (e) {
      console.error(e);
      elements.btnTriggerScraper.disabled = false;
      if (icon) icon.style.animation = '';
    }
  });

  // Directory filter handlers
  elements.dirSearchInput.addEventListener('input', renderDirectoryJobs);
  elements.dirPlatformSelect.addEventListener('change', renderDirectoryJobs);
  elements.btnRefreshAllJobs.addEventListener('click', async () => {
    showToast('Refreshing live directory feeds...');
    await loadInitialJobs();
    renderDirectoryJobs();
  });
}

function renderMatchedJobs() {
  const container = elements.matchedJobsContainer;
  container.innerHTML = '';

  let list = state.matchedJobs.length > 0 ? state.matchedJobs : state.allJobs;

  // Filter by platform
  if (state.activePlatformFilter !== 'all') {
    list = list.filter(j => (j.platform || '').toLowerCase() === state.activePlatformFilter);
  }

  // Filter by min score
  if (state.minScoreFilter > 0) {
    list = list.filter(j => (j.match_score || 0) >= state.minScoreFilter);
  }

  // Filter by remote
  if (state.remoteOnly) {
    list = list.filter(j => j.is_remote);
  }

  // Filter by search query
  if (state.searchQuery) {
    list = list.filter(j => {
      const titleMatch = (j.title || '').toLowerCase().includes(state.searchQuery);
      const compMatch = (j.company || '').toLowerCase().includes(state.searchQuery);
      const skillMatch = (j.extracted_skills || []).some(s => s.toLowerCase().includes(state.searchQuery));
      return titleMatch || compMatch || skillMatch;
    });
  }

  if (list.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 48px 20px; background: #FFFFFF; border-radius: 16px; border: 1px dashed #CBD5E1;">
        <h4 style="font-size: 1.1rem; color: #1E293B; margin-bottom: 6px;">No roles match the selected criteria</h4>
        <p style="font-size: 0.85rem; color: #64748B;">Try selecting "All Platforms" or adjusting your search filters.</p>
      </div>
    `;
    return;
  }

  list.forEach(job => {
    const card = createJobCard(job, true);
    container.appendChild(card);
  });
}

function renderDirectoryJobs() {
  const container = elements.allJobsContainer;
  container.innerHTML = '';

  const q = elements.dirSearchInput.value.toLowerCase().trim();
  const plat = elements.dirPlatformSelect.value;

  let list = state.allJobs;

  if (plat !== 'all') {
    list = list.filter(j => (j.platform || '').toLowerCase() === plat);
  }

  if (q) {
    list = list.filter(j => {
      return (j.title || '').toLowerCase().includes(q) ||
             (j.company || '').toLowerCase().includes(q) ||
             (j.description || '').toLowerCase().includes(q);
    });
  }

  if (list.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 48px; background: #FFFFFF; border-radius: 16px; border: 1px dashed #CBD5E1;">
        <h4>No jobs found</h4>
      </div>
    `;
    return;
  }

  list.forEach(job => {
    const card = createJobCard(job, false);
    container.appendChild(card);
  });
}

function createJobCard(job, showMatchDetails) {
  const card = document.createElement('div');
  card.className = 'job-card';

  const plat = (job.platform || 'ats').toLowerCase();
  const score = job.match_score || 0;
  const scoreClass = score >= 80 ? 'high' : (score >= 60 ? 'med' : 'low');

  // Matched Skills Tags
  let skillsHtml = '';
  if (showMatchDetails && job.matched_skills && job.matched_skills.length > 0) {
    const matchedBadges = job.matched_skills.slice(0, 4).map(s => `<span class="tag-match">✓ ${s}</span>`).join('');
    const missingBadges = (job.missing_skills || []).slice(0, 2).map(s => `<span class="tag-missing">${s}</span>`).join('');
    skillsHtml = `
      <div class="matched-skills-box">
        <span class="box-label">Skill Alignment</span>
        <div class="skills-wrap">${matchedBadges} ${missingBadges}</div>
      </div>
    `;
  } else if (job.extracted_skills && job.extracted_skills.length > 0) {
    const badges = job.extracted_skills.slice(0, 5).map(s => `<span class="tag-missing">${s}</span>`).join('');
    skillsHtml = `
      <div class="matched-skills-box">
        <span class="box-label">Required Skills</span>
        <div class="skills-wrap">${badges}</div>
      </div>
    `;
  }

  // Match reasons
  let reasonsHtml = '';
  if (showMatchDetails && job.match_reasons && job.match_reasons.length > 0) {
    reasonsHtml = `<div class="job-reasons">💡 ${job.match_reasons[0]}</div>`;
  }

  // UK Sponsor badge: only shown when employer is on the register AND location is
  // explicitly UK-eligible. Never shown for overseas or ambiguous/remote locations.
  const ukSponsorBadge = job.visa_sponsored === true
    ? `<span class="uk-sponsor-badge" title="${escapeHtml(job.visa_sponsor_disclaimer || '')}">🇬🇧 UK Sponsor Listed</span>`
    : '';

  card.innerHTML = `
    <div class="job-card-top">
      <span class="ats-badge ${plat}">${plat}</span>
      ${showMatchDetails && score > 0 ? `
        <span class="match-score-badge ${scoreClass}">
          <strong>${score}%</strong> Match
        </span>
      ` : ''}
      ${ukSponsorBadge}
    </div>

    <h3 class="job-title">${escapeHtml(job.title)}</h3>
    <p class="job-company">${escapeHtml(job.company)}</p>

    <div class="job-meta-row">
      <span class="job-meta-item">📍 ${escapeHtml(job.location || 'Remote')}</span>
      ${job.is_remote ? `<span class="job-meta-item">🌐 Remote</span>` : ''}
      <span class="job-meta-item">💼 ${escapeHtml(job.employment_type || 'Full-time')}</span>
    </div>

    ${skillsHtml}
    ${reasonsHtml}

    <div class="job-card-actions">
      <button type="button" class="btn-details" data-id="${job.id}">View Details</button>
      <a href="${job.url}" target="_blank" rel="noopener noreferrer" class="btn-apply-direct">
        <span>Apply</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
      </a>
    </div>
  `;

  card.querySelector('.btn-details').addEventListener('click', () => {
    openJobModal(job);
  });

  return card;
}

// ==========================================================================
// MODALS
// ==========================================================================
function setupModals() {
  // Detail Modal
  const closeDetail = () => elements.jobDetailModal.classList.add('hidden');
  elements.modalCloseBtn.addEventListener('click', closeDetail);
  elements.modalBtnDismiss.addEventListener('click', closeDetail);

  // Add Company Modal
  elements.btnOpenAddCompany.addEventListener('click', () => {
    elements.addCompanyModal.classList.remove('hidden');
  });
  const closeAddComp = () => elements.addCompanyModal.classList.add('hidden');
  elements.closeAddCompanyBtn.addEventListener('click', closeAddComp);
  elements.cancelAddCompanyBtn.addEventListener('click', closeAddComp);

  elements.newCompanyPlatform.addEventListener('change', (e) => {
    if (e.target.value === 'workday') {
      elements.workdayExtraFields.classList.remove('hidden');
    } else {
      elements.workdayExtraFields.classList.add('hidden');
    }
  });

  elements.addCompanyForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const plat = elements.newCompanyPlatform.value;
    const name = document.getElementById('new-company-name').value;
    const token = document.getElementById('new-company-token').value;
    const host = document.getElementById('new-workday-host').value;
    const site = document.getElementById('new-workday-site').value;

    showToast(`Adding ${name} to ${plat} scraper...`);
    closeAddComp();

    try {
      const formData = new FormData();
      formData.append('platform', plat);
      formData.append('token', token);
      formData.append('name', name);
      formData.append('host', host);
      formData.append('site', site);

      const res = await fetch(`${API_BASE}/api/companies`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      showToast(data.message);
      await loadInitialJobs();
      renderPlatformsCatalog();
    } catch (err) {
      showToast(`Error adding company: ${err.message}`);
    }
  });
}

function openJobModal(job) {
  const plat = (job.platform || 'ATS').toLowerCase();
  elements.modalPlatformBadge.textContent = plat.toUpperCase();
  elements.modalPlatformBadge.className = `modal-ats-badge ${plat}`;
  elements.modalJobTitle.textContent = job.title;
  const locationStatus = job.visa_sponsor_location_status || '';
  const ukBadgeHtml = job.visa_sponsored === true
    ? `<span class="uk-sponsor-badge" title="${escapeHtml(job.visa_sponsor_disclaimer || '')}">🇬🇧 UK Sponsor Listed</span>`
    : (locationStatus === 'NON_UK' ? '' : (locationStatus === 'LOCATION_UNVERIFIED' ? '' : ''));
  elements.modalJobCompany.innerHTML = `${escapeHtml(job.company)} &bull; ${escapeHtml(job.location || 'Remote')} &bull; ${escapeHtml(job.employment_type || 'Full-time')} ${ukBadgeHtml}`;
  elements.modalBtnApply.href = job.url;

  if (job.match_score) {
    elements.modalMatchBox.innerHTML = `
      <div style="background: #ECFDF5; border: 1px solid #A7F3D0; padding: 14px; border-radius: 12px; margin-bottom: 18px;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
          <strong style="color: #065F46; font-size: 0.95rem;">Match Score: ${job.match_score}% (${job.fit_level})</strong>
          <span style="font-size: 0.78rem; font-weight: 700; color: #047857;">Based on your Résumé</span>
        </div>
        <p style="font-size: 0.8rem; color: #065F46; margin-bottom: 6px;">
          <strong>Matching Skills:</strong> ${(job.matched_skills || []).join(', ') || 'General domain match'}
        </p>
        ${job.missing_skills && job.missing_skills.length > 0 ? `
          <p style="font-size: 0.8rem; color: #4B5563;">
            <strong>Skills to Highlight:</strong> ${job.missing_skills.join(', ')}
          </p>
        ` : ''}
      </div>
    `;
  } else {
    elements.modalMatchBox.innerHTML = '';
  }

  elements.modalJobDesc.textContent = job.description || 'No detailed description provided.';
  elements.jobDetailModal.classList.remove('hidden');
}

// ==========================================================================
// PLATFORMS CATALOG TAB
// ==========================================================================
function renderPlatformsCatalog() {
  const grid = elements.platformsCatalogGrid;
  grid.innerHTML = '';

  state.platforms.forEach(p => {
    const card = document.createElement('div');
    card.className = 'platform-card';
    card.innerHTML = `
      <div class="platform-card-header">
        <span class="platform-title" style="color: ${p.color};">${p.name}</span>
        <span class="badge-pill">${p.job_count || 0} Jobs Scraped</span>
      </div>
      <p class="platform-desc">${p.description}</p>
      <div class="platform-companies-list">
        ${p.companies.map(c => `<span class="company-pill">${c}</span>`).join('')}
      </div>
      <div class="platform-footer">
        <span style="font-size: 0.76rem; color: #64748B;">Supported: REST API / Scraping</span>
        <button type="button" class="btn-scrape-platform" data-plat="${p.id}">Scrape ${p.name}</button>
      </div>
    `;

    card.querySelector('.btn-scrape-platform').addEventListener('click', async () => {
      showToast(`Scraping latest jobs from ${p.name}...`);
      await fetch(`${API_BASE}/api/scrapers/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform: p.id })
      });
      setTimeout(async () => {
        await loadInitialJobs();
        showToast(`Scrape completed for ${p.name}`);
      }, 3000);
    });

    grid.appendChild(card);
  });
}

// ==========================================================================
// RESUME PROFILE TAB
// ==========================================================================
function renderResumeProfileView() {
  const container = elements.resumeProfileDetails;
  const resume = state.currentResume;

  if (!resume) {
    container.innerHTML = `
      <div style="background: #FFFFFF; border-radius: 16px; border: 1px dashed #CBD5E1; padding: 48px; text-align: center;">
        <h3 style="font-size: 1.15rem; color: #1E293B; margin-bottom: 8px;">No résumé uploaded yet</h3>
        <p style="font-size: 0.88rem; color: #64748B; margin-bottom: 18px;">Please upload your résumé on the Home tab to view the extracted skills breakdown.</p>
        <button type="button" class="btn-choose-resume" onclick="switchTab('home')">Go to Home Upload</button>
      </div>
    `;
    return;
  }

  let categoriesHtml = '';
  for (const [cat, skills] of Object.entries(resume.categorized_skills || {})) {
    categoriesHtml += `
      <div class="skill-category-block">
        <h4 class="category-name">${cat} (${skills.length})</h4>
        <div style="display: flex; flex-wrap: wrap; gap: 6px;">
          ${skills.map(s => `<span class="skill-chip">${s}</span>`).join('')}
        </div>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="profile-card">
      <div class="profile-header-grid">
        <div class="profile-avatar-circle">
          ${(resume.candidate_name || 'U').charAt(0)}
        </div>
        <div>
          <h2 style="font-size: 1.6rem; font-weight: 800; color: #0F172A; margin-bottom: 4px;">${escapeHtml(resume.candidate_name)}</h2>
          <p style="font-size: 0.95rem; color: #475569; margin-bottom: 10px;">
            ${escapeHtml(resume.target_roles.join(' • '))} • ${resume.years_of_experience > 0 ? resume.years_of_experience + '+ years experience' : resume.seniority_level}
          </p>
          <div style="display: flex; gap: 16px; font-size: 0.84rem; color: #64748B; flex-wrap: wrap;">
            <span>📧 ${escapeHtml(resume.email)}</span>
            <span>📞 ${escapeHtml(resume.phone)}</span>
            ${resume.linkedin ? `<span>🔗 ${escapeHtml(resume.linkedin)}</span>` : ''}
            ${resume.github ? `<span>🐙 ${escapeHtml(resume.github)}</span>` : ''}
          </div>
        </div>
      </div>

      <div style="border-top: 1px solid #E2E8F0; padding-top: 24px;">
        <h3 style="font-size: 1.1rem; font-weight: 700; color: #0F172A; margin-bottom: 16px;">
          Skills Taxonomy (${resume.total_skills} skills found)
        </h3>
        ${categoriesHtml}
      </div>

      <div style="border-top: 1px solid #E2E8F0; padding-top: 20px; margin-top: 20px;">
        <h4 style="font-size: 0.9rem; font-weight: 700; color: #334155; margin-bottom: 8px;">Executive Summary</h4>
        <p style="font-size: 0.85rem; color: #64748B; line-height: 1.6;">${escapeHtml(resume.summary)}</p>
      </div>
    </div>
  `;
}

// ==========================================================================
// INSIGHTS TAB
// ==========================================================================
async function loadInsights() {
  const container = elements.insightsMetricsContainer;
  try {
    const res = await fetch(`${API_BASE}/api/stats`);
    const data = await res.json();

    let skillsListHtml = '';
    data.top_skills.forEach((item, idx) => {
      skillsListHtml += `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #F1F5F9;">
          <span style="font-weight: 600; font-size: 0.88rem; color: #1E293B;">#${idx + 1} ${item.skill}</span>
          <span class="badge-pill">${item.count} job mentions</span>
        </div>
      `;
    });

    container.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 28px;">
        <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px; padding: 24px;">
          <span style="font-size: 0.8rem; font-weight: 700; color: #64748B;">TOTAL INDEXED JOBS</span>
          <h2 style="font-size: 2.2rem; font-weight: 800; color: #2563EB; margin-top: 6px;">${data.total_jobs}</h2>
          <p style="font-size: 0.78rem; color: #10B981; margin-top: 4px;">✓ Across 8 major ATS networks</p>
        </div>
        <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px; padding: 24px;">
          <span style="font-size: 0.8rem; font-weight: 700; color: #64748B;">ACTIVE ATS CONNECTIONS</span>
          <h2 style="font-size: 2.2rem; font-weight: 800; color: #0F172A; margin-top: 6px;">8 / 8</h2>
          <p style="font-size: 0.78rem; color: #64748B; margin-top: 4px;">Greenhouse, Ashby, Lever, Workday, Workable, Oracle Cloud, Breezy, Pinpoint</p>
        </div>
      </div>

      <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 16px; padding: 24px;">
        <h3 style="font-size: 1.1rem; font-weight: 800; color: #0F172A; margin-bottom: 16px;">
          Most In-Demand Tech Skills Across ATS Boards
        </h3>
        ${skillsListHtml}
      </div>
    `;
  } catch (e) {
    console.error(e);
  }
}

// Utility: Escape HTML
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

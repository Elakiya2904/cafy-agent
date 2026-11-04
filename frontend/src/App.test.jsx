import React from 'react';
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
// The PDF engine needs a real browser; the editor falls back to its HTML preview when it fails.
vi.mock('./PdfPreview.jsx', () => ({ default: () => null }));
import App, { ApplicationTrackingView, DirectoryView, JobDetailModal, normalizeClientResume } from './App.jsx';

const job = {
  id: 'job-1',
  title: 'Senior Software Engineer',
  company: 'Google',
  location: 'London, UK',
  platform: 'greenhouse',
  employment_type: 'Full-time',
  description: 'Build product features and work across teams using React, Node, and Python.',
  match_score: 92,
  matched_skills: ['Python', 'React', 'AWS'],
  missing_skills: ['Kubernetes'],
  url: 'https://example.com/apply',
};

const resume = {
  candidate_name: 'Alex Morgan',
  email: 'alex@example.com',
  filename: 'resume.pdf',
  skills: ['Python', 'React', 'AWS', 'SQL'],
  location: 'London, UK',
};

describe('normalizeClientResume', () => {
  it('keeps projects, publications, internships, and achievements in separate fields', () => {
    const normalized = normalizeClientResume(
      {
        professional_summary: '',
        projects: [
          { title: 'Project A', description: 'Built a service.' },
          { title: 'Project B', description: 'Built a dashboard.' },
        ],
        publications: [{ title: 'Paper A', organization: 'Research Journal', dates: '2024' }],
        achievements: ['Finalist, Data Challenge'],
      },
      {
        summary: 'Experienced engineer.',
        internships: [{ title: 'Research Intern', organization: 'Lab' }],
        publications: [{ title: 'Older Paper', organization: 'Journal' }],
      },
      job
    );

    expect(normalized.professional_summary).toBe('Experienced engineer.');
    expect(normalized.projects.map((entry) => entry.title)).toEqual(['Project A', 'Project B']);
    expect(normalized.publications).toEqual([
      expect.objectContaining({ title: 'Paper A', organization: 'Research Journal', dates: '2024' }),
    ]);
    expect(normalized.internships).toEqual([
      expect.objectContaining({ title: 'Research Intern', organization: 'Lab' }),
    ]);
    expect(normalized.achievements).toEqual([
      expect.objectContaining({ title: 'Finalist, Data Challenge' }),
    ]);
  });

  it('respects explicitly cleared sections when reopening a saved resume', () => {
    const normalized = normalizeClientResume(
      { projects: [], publications: [] },
      {
        projects: [{ title: 'Source Project' }],
        publications: [{ title: 'Source Paper' }],
      },
      job
    );

    expect(normalized.projects).toEqual([]);
    expect(normalized.publications).toEqual([]);
  });
});

describe('Find Jobs resume removal', () => {
  it('offers a remove-resume action when a resume is loaded', () => {
    const onRemoveResume = vi.fn();
    render(
      <DirectoryView
        jobs={[job]}
        matchedJobs={[job]}
        resume={resume}
        platforms={[]}
        pipelineJobIds={new Set()}
        onTogglePipeline={() => {}}
        onAddAllToPipeline={() => {}}
        onSelectJob={() => {}}
        onRefresh={() => {}}
        onRemoveResume={onRemoveResume}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Remove résumé/i }));
    expect(onRemoveResume).toHaveBeenCalledOnce();
  });
});

describe('Find Jobs country location filters', () => {
  it('matches all UK-classified jobs when searching for UK', () => {
    render(
      <DirectoryView
        jobs={[
          { ...job, id: 'london-no-country', location: 'London', is_uk_location: true },
          { ...job, id: 'edinburgh-no-country', location: 'Edinburgh', is_uk_location: true },
          { ...job, id: 'toronto', location: 'Toronto, Canada', is_uk_location: false },
        ]}
        matchedJobs={[]}
        resume={null}
        platforms={[]}
        pipelineJobIds={new Set()}
        onTogglePipeline={() => {}}
        onAddAllToPipeline={() => {}}
        onSelectJob={() => {}}
        onRefresh={() => {}}
      />
    );

    fireEvent.change(screen.getByLabelText('City or Location'), { target: { value: 'UK' } });

    expect(screen.getByRole('button', { name: /Show 2 matching jobs/i })).toBeInTheDocument();
  });
});

describe('Find Jobs browse layout', () => {
  it('shows the job list and About-first detail panel without opening the advanced filters', () => {
    render(
      <DirectoryView
        jobs={[{
          ...job,
          visa_sponsored: true,
          visa_sponsor_country: 'UK',
          company_description: 'A growing technology company.',
          company_website: 'https://example.com',
        }]}
        matchedJobs={[]}
        resume={null}
        platforms={[]}
        pipelineJobIds={new Set()}
        onTogglePipeline={() => {}}
        onAddAllToPipeline={() => {}}
        onSelectJob={() => {}}
        onRefresh={() => {}}
      />
    );

    expect(screen.getByRole('searchbox', { name: 'Job role' })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: 'Company or location' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '1 active job' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Company details' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Job info' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tab', { name: 'Job Intelligence' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Why This Job?' })).not.toBeInTheDocument();
    expect(screen.getByText('LICENSED UK VISA SPONSOR')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Apply with autofill/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Apply now/i })).toHaveAttribute('target', '_blank');

  });
});

beforeEach(() => {
  document.body.innerHTML = '<div id="root"></div>';
  window.sessionStorage.clear();
  window.open = vi.fn();
  global.fetch = vi.fn().mockImplementation((url, opts) => {
    const body = opts?.body ? JSON.parse(opts.body) : {};
    if (url.includes('/api/job-applications/start')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ application: { id: 'app_1' }, resumed: false }) });
    }
    if (url.includes('/api/resumes/job/')) {
      return Promise.resolve({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ status: "not_found" }),
      });
    }
    if (url.includes('/api/resumes/pre-analysis')) {
      const section = (name, score) => ({ name, score, weight: 10, status: "partial", missing: [], suggestions: [] });
      // An AI-improved summary scores higher, so tests can see the score move.
      const improved = String(body.resume_data?.summary || "").includes("AI-improved");
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          job_match_score: improved ? 80 : 72,
          match_tier: improved ? "Strong Match" : "Good Match",
          matched_skills: ["Python", "AWS"],
          missing_skills: ["Kubernetes"],
          missing_information: [],
          gaps: [
            { type: "missing_from_profile", section: "skills", title: "Kubernetes", detail: "Skill not found in your profile", skill: "Kubernetes" },
            { type: "missing_qualification", section: "experience", title: "5+ years experience", detail: "Your profile shows 2 years" },
          ],
          suggestions: [],
          sections: {
            summary: section("Professional Summary", improved ? 95 : 60),
            skills: section("Skills", 67),
            experience: section("Work Experience", 80),
            education: section("Education", 90),
            projects: section("Projects", 70),
            certifications: section("Certifications", 80),
          },
          profile_completeness: { overall_score: 64, strength_tier: "Competitive", sections: {} },
        }),
      });
    }
    if (url.includes('/api/resume/update')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ resume: { ...resume, ...body } }) });
    }
    if (url.includes('/api/resumes/rewrite-full')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          status: "rewritten",
          resume_id: "res-rewrite-1",
          rejected_lines: 1,
          recommended_skills: ["Kubernetes"],
          resume: { ...body.resume, professional_summary: "Rewritten summary using only existing facts." },
        }),
      });
    }
    if (url.includes('/api/resumes/rewrite-section')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "success", rewritten: "AI-improved summary for React and Python roles." }),
      });
    }
    if (url.includes('/api/resumes/generate')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          status: "success",
          resume_id: "res-test-1",
          pdf_url: "/api/resumes/res-test-1/pdf",
          docx_url: "/api/resumes/res-test-1/docx",
          tex_url: "/api/resumes/res-test-1/latex",
          tailored_resume: {
            personal_info: { name: "Alex Morgan", email: "alex@example.com", phone: "+44 20 7946 0958", location: "London, UK" },
            professional_summary: "Experienced Senior Software Engineer.",
            experience: [{ title: "Software Engineer", organization: "Tech Corp", dates: "2021 - Present", bullets: ["Built scalable systems"] }],
            projects: [{ title: "Cloud Platform", organization: "Open Source", dates: "2023", bullets: ["Engineered distributed apps"] }],
            education: [{ degree: "BSc Computer Science", institution: "University of London", dates: "2017 - 2020" }],
            skills: ["Python", "React", "AWS", "SQL"]
          }
        }),
      });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    });
  });
});

afterEach(cleanup);

describe('App page reload', () => {
  it('returns to the selected page and restores the saved resume after reload', async () => {
    global.fetch = vi.fn((input) => {
      const url = String(input);
      const data = url.includes('/api/resume/current')
        ? { resume, matched_jobs: [job] }
        : url.includes('/api/platforms')
          ? { platforms: [], total_jobs: 1 }
          : url.includes('/api/jobs')
            ? { jobs: [job], count: 1 }
            : {};
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(data),
      });
    });

    const firstLoad = render(<App />);
    fireEvent.click(screen.getByRole('link', { name: /Find Jobs/i }));
    expect(await screen.findByRole('heading', { name: 'Job Discovery' })).toBeInTheDocument();
    expect(await screen.findByText('Alex Morgan')).toBeInTheDocument();
    expect(window.sessionStorage.getItem('cafy-agent-active-tab')).toBe('find-jobs');

    firstLoad.unmount();
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Job Discovery' })).toBeInTheDocument();
    expect(await screen.findByText('Alex Morgan')).toBeInTheDocument();
    expect(screen.queryByText('Upload your résumé')).not.toBeInTheDocument();
  });
});

describe('Cafy Agent job application drawer', () => {
  it('normalizes HTML job descriptions on the job review screen', async () => {
    const htmlJob = {
      ...job,
      description: '<p><strong>Build products</strong>&nbsp;&amp; lead teams.</p><p>Use React.</p>',
    };

    render(
      <JobDetailModal
        job={htmlJob}
        resume={resume}
        onClose={() => {}}
        onTogglePipeline={() => {}}
        inPipeline={false}
        resumeOnly
      />
    );

    const description = await screen.findByText(/Build products\s+& lead teams/i);
    expect(description.textContent).not.toContain('<p>');
    expect(description.textContent).not.toContain('&nbsp;');
    expect(description.textContent).not.toContain('&amp;');
  });

  it('opens the application drawer and switches tabs', async () => {
    function DrawerHarness() {
      const [selectedJob, setSelectedJob] = React.useState(null);
      return (
        <>
          <DirectoryView
            jobs={[job]}
            matchedJobs={[job]}
            resume={null}
            platforms={[]}
            pipelineJobIds={new Set()}
            onTogglePipeline={() => {}}
            onAddAllToPipeline={() => {}}
            onSelectJob={setSelectedJob}
            onRefresh={() => {}}
          />
          {selectedJob && (
            <JobDetailModal
              job={selectedJob}
              resume={resume}
              onClose={() => setSelectedJob(null)}
              onTogglePipeline={() => {}}
              inPipeline={false}
              resumeOnly
            />
          )}
        </>
      );
    }

    render(<DrawerHarness />);
    screen.debug();
    fireEvent.click(screen.getByRole('button', { name: /Show 1 matching jobs/i }));
    expect(await screen.findAllByText('92% Job Match')).not.toHaveLength(0);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Apply with autofill/i })).toBeInTheDocument();
    });

    // "Apply now" opens the employer posting; "Apply with autofill" opens the tailoring workflow.
    expect(screen.getByRole('link', { name: /Apply now/i })).toHaveAttribute('target', '_blank');
    fireEvent.click(screen.getByRole('button', { name: /Apply with autofill/i }));

    // The selected job and its description come first; nothing is generated until the user asks.
    expect(await screen.findByText('Selected job')).toBeInTheDocument();
    expect(screen.getByText('Job description')).toBeInTheDocument();
    expect(screen.getByText(/Additional instructions/i)).toBeInTheDocument();
    expect(screen.queryByTestId('editor-match-score')).not.toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalledWith(expect.stringContaining('/api/resumes/generate'), expect.anything());

    fireEvent.change(screen.getByPlaceholderText(/Emphasise my Python/i), { target: { value: 'Emphasise Python' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate Tailored Resume/i }));
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/resumes/generate'), expect.anything());
    });
    const call = global.fetch.mock.calls.find(([u]) => u.includes('/api/resumes/generate'));
    expect(JSON.parse(call[1].body).additional_instructions).toBe('Emphasise Python');
    expect(screen.queryByRole('tab', { name: /^Requirements$/i })).not.toBeInTheDocument();
    // Generating lands in the Resume Editor and the job review card goes away.
    expect(await screen.findByRole('navigation', { name: 'Structured editor sections' }, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.queryByText('Selected job')).not.toBeInTheDocument();
  });

  it('generates a tailored resume without the removed output action bar', async () => {
    render(
      <JobDetailModal
        job={job}
        resume={resume}
        onClose={() => {}}
        onTogglePipeline={() => {}}
        inPipeline={false}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Generate Tailored Resume/i }));

    await screen.findByRole('navigation', { name: 'Structured editor sections' }, { timeout: 3000 });
    expect(screen.queryByRole('button', { name: /Download Resume/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Continue to Application/i })).not.toBeInTheDocument();
  });

  it('shows live section scores in the Resume Editor and updates them after Improve with AI', async () => {
    render(
      <JobDetailModal job={job} resume={resume} onClose={() => {}} onTogglePipeline={() => {}} inPipeline={false} />
    );
    // No analysis step before generation: Apply goes straight to Generate Tailored Resume.
    expect(screen.queryByText(/Profile Completeness/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Generate Tailored Resume/i }));

    const scoreBar = await screen.findByTestId('editor-match-score', {}, { timeout: 3000 });
    expect(scoreBar).toHaveTextContent(/72%ATS MATCH READINESS\s*Good Match\s*Optimized for:/);
    expect(scoreBar).toHaveTextContent('Summary60%');
    expect(screen.getAllByTitle('Professional Summary: 60% match for this job').length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole('button', { name: /AI Enhance & Optimize/i })[0]);

    await waitFor(() => {
      expect(screen.getByTestId('editor-match-score')).toHaveTextContent(/80%ATS MATCH READINESS\s*Strong Match\s*Optimized for:/);
    }, { timeout: 3000 });
    expect(screen.getByTestId('editor-match-score')).toHaveTextContent('+8 since last change');
    expect(screen.getAllByTitle('Professional Summary: 95% match for this job').length).toBeGreaterThan(0);
  });

  it('shows completeness, job match, section scores and gap analysis before generating', async () => {
    const onUpdateResume = vi.fn();
    render(
      <JobDetailModal job={job} resume={resume} onUpdateResume={onUpdateResume} onClose={() => {}} onTogglePipeline={() => {}} inPipeline={false} />
    );
    const panel = await screen.findByTestId('application-analysis');
    expect(panel).toHaveTextContent('Profile Completeness');
    expect(panel).toHaveTextContent('64%');
    expect(panel).toHaveTextContent('72%');
    expect(panel).toHaveTextContent('Job Requirement Fit by Section');
    expect(screen.getByRole('tab', { name: 'All (2)' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Missing Qualification (1)' }));
    expect(screen.getByText('5+ years experience')).toBeInTheDocument();
    expect(screen.queryByText('Kubernetes', { selector: 'strong' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Missing from Profile (1)' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add Kubernetes to profile' }));
    await waitFor(() => expect(onUpdateResume).toHaveBeenCalled());
    expect(onUpdateResume.mock.calls[0][0].skills).toContain('Kubernetes');

    // Generate button sits below the analysis; the editor then shows one section at a time.
    fireEvent.click(screen.getByRole('button', { name: /Generate Tailored Resume/i }));
    const nav = await screen.findByRole('navigation', { name: 'Structured editor sections' }, { timeout: 3000 });
    fireEvent.click(within(nav).getByRole('button', { name: /Education/ }));
    expect(screen.getByRole('button', { name: '+ Add Education Entry' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Professional summary')).not.toBeInTheDocument();
  });

  it('tracks only real pipeline jobs, with no demo applications', () => {
    const { rerender } = render(
      <ApplicationTrackingView pipelineJobIds={new Set()} allJobs={[job]} onSelectJob={() => {}} />
    );
    expect(screen.getByText(/No tracked applications yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/Meta|Microsoft|NVIDIA/)).not.toBeInTheDocument();

    rerender(<ApplicationTrackingView pipelineJobIds={new Set(['job-1'])} allJobs={[job]} onSelectJob={() => {}} />);
    expect(screen.getAllByText('Senior Software Engineer').length).toBeGreaterThan(0);
    const status = screen.getByTitle('Click to change status');
    expect(status).toHaveTextContent('In pipeline');
    fireEvent.click(status);
    expect(screen.getByTitle('Click to change status')).toHaveTextContent('Applied');
  });

  it('does not show the removed rewrite action bar', async () => {
    render(<JobDetailModal job={job} resume={resume} onClose={() => {}} onTogglePipeline={() => {}} inPipeline={false} />);
    fireEvent.click(screen.getByRole('button', { name: /Generate Tailored Resume/i }));
    await screen.findByRole('navigation', { name: 'Structured editor sections' }, { timeout: 3000 });
    expect(screen.queryByRole('button', { name: 'Rewrite with AI' })).not.toBeInTheDocument();
  });
});

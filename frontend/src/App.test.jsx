import React from 'react';
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
// The PDF engine needs a real browser; the editor falls back to its HTML preview when it fails.
vi.mock('./PdfPreview.jsx', () => ({ default: () => null }));
import { ApplicationTrackingView, DirectoryView, JobDetailModal } from './App.jsx';

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

beforeEach(() => {
  document.body.innerHTML = '<div id="root"></div>';
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

describe('Cafy Agent job application drawer', () => {
  it('normalizes HTML job descriptions in the tailor textarea', async () => {
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

    const description = await screen.findByDisplayValue(/Build products & lead teams/i);
    expect(description).not.toHaveValue(expect.stringContaining('<p>'));
    expect(description).not.toHaveValue(expect.stringContaining('&nbsp;'));
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

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Tailor with Cafy/i })).toBeInTheDocument();
    });

    // "Apply Now" is a link to the original posting; "Tailor with Cafy" opens the tailor setup first.
    expect(screen.getByRole('link', { name: /Apply Now/i })).toHaveAttribute('target', '_blank');
    fireEvent.click(screen.getByRole('button', { name: /Tailor with Cafy/i }));

    // Inputs and the pre-generation analysis come first; nothing is generated until the user asks.
    expect(await screen.findByText('Tailor your resume')).toBeInTheDocument();
    expect(screen.getByText(/Additional instructions/i)).toBeInTheDocument();
    expect(await screen.findByTestId('application-analysis')).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalledWith(expect.stringContaining('/api/resumes/generate'), expect.anything());

    fireEvent.change(screen.getByPlaceholderText(/Emphasise my Python/i), { target: { value: 'Emphasise Python' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate Tailored Resume/i }));
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/resumes/generate'), expect.anything());
    });
    const call = global.fetch.mock.calls.find(([u]) => u.includes('/api/resumes/generate'));
    expect(JSON.parse(call[1].body).additional_instructions).toBe('Emphasise Python');
    expect(screen.queryByRole('tab', { name: /^Requirements$/i })).not.toBeInTheDocument();
  });

  it('generates a tailored resume, downloads it, and opens the application URL', async () => {
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

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Download/i })).toBeInTheDocument();
    }, { timeout: 3000 });

    fireEvent.click(screen.getByRole('button', { name: /Download Resume/i }));
    expect(window.open).toHaveBeenCalled();

    const continueBtn = screen.getByRole('button', { name: /Continue to Application/i });
    fireEvent.click(continueBtn);
    expect(screen.queryByText(/Supported Form Autofill/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Multi-step Application/i)).not.toBeInTheDocument();
    // The application is registered (duplicate check) before the company page opens.
    await waitFor(() => expect(window.open).toHaveBeenCalledTimes(2));
    expect(window.open).toHaveBeenLastCalledWith('https://example.com/apply', '_blank', 'noopener,noreferrer');
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/job-applications/start'), expect.anything());
  });

  it('shows live section scores in the Resume Editor and updates them after Improve with AI', async () => {
    render(
      <JobDetailModal job={job} resume={resume} onClose={() => {}} onTogglePipeline={() => {}} inPipeline={false} />
    );
    // No analysis step before generation: Apply goes straight to Generate Tailored Resume.
    expect(screen.queryByText(/Profile Completeness/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Generate Tailored Resume/i }));

    const scoreBar = await screen.findByTestId('editor-match-score', {}, { timeout: 3000 });
    expect(scoreBar).toHaveTextContent(/^72%Job Match · Good Match/);
    expect(scoreBar).toHaveTextContent('Professional Summary 60%');
    expect(screen.getAllByTitle('Professional Summary: 60% match for this job').length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole('button', { name: /Improve with AI/i })[0]);

    await waitFor(() => {
      expect(screen.getByTestId('editor-match-score')).toHaveTextContent(/^80%Job Match · Strong Match/);
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
    expect(panel).toHaveTextContent('Profile Section Scores');
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
    fireEvent.click(within(nav).getByRole('button', { name: /Certifications/ }));
    expect(screen.getByRole('button', { name: '+ Add Certification' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Professional summary')).not.toBeInTheDocument();
  });

  it('tracks only real pipeline jobs, with no demo applications', () => {
    const { rerender } = render(
      <ApplicationTrackingView pipelineJobIds={new Set()} allJobs={[job]} onSelectJob={() => {}} />
    );
    expect(screen.getByText(/No tracked applications yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/Meta|Microsoft|NVIDIA/)).not.toBeInTheDocument();

    rerender(<ApplicationTrackingView pipelineJobIds={new Set(['job-1'])} allJobs={[job]} onSelectJob={() => {}} />);
    expect(screen.getByText('Senior Software Engineer')).toBeInTheDocument();
    const status = screen.getByTitle('Click to change status');
    expect(status).toHaveTextContent('In pipeline');
    fireEvent.click(status);
    expect(screen.getByTitle('Click to change status')).toHaveTextContent('Applied');
  });

  it('Rewrite with AI rewrites the whole resume, reports kept lines and only recommends skills', async () => {
    render(<JobDetailModal job={job} resume={resume} onClose={() => {}} onTogglePipeline={() => {}} inPipeline={false} />);
    fireEvent.click(screen.getByRole('button', { name: /Generate Tailored Resume/i }));
    const rewriteBtn = await screen.findByRole('button', { name: 'Rewrite with AI' }, { timeout: 3000 });
    fireEvent.click(rewriteBtn);

    const result = await screen.findByTestId('rewrite-result');
    expect(result).toHaveTextContent('saved as a new version');
    expect(result).toHaveTextContent('1 line was kept as written');
    expect(screen.getByLabelText('Professional summary')).toHaveValue('Rewritten summary using only existing facts.');

    // Recommended skills are not added until the user chooses to.
    const call = global.fetch.mock.calls.find(([u]) => u.includes('/api/resumes/rewrite-full'));
    expect(JSON.parse(call[1].body).resume.skills).not.toContain('Kubernetes');
    const add = within(result).getByRole('button', { name: /Kubernetes/ });
    fireEvent.click(add);
    expect(within(result).getByRole('button', { name: /Kubernetes/ })).toBeDisabled();
  });
});

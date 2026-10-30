// @vitest-environment jsdom
import React from 'react';
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ResumeVersionHistory, { compareResumes } from './ResumeVersionHistory.jsx';
import DataExport from './DataExport.jsx';

const v1 = {
  version_number: 1, resume_id: 'r1', job_id: 'j1', job_title: 'DevOps Engineer', company: 'Google',
  created_at: '2026-10-25T17:20:00Z', updated_at: '2026-10-25T17:20:00Z', is_current: false,
  pdf_url: null, docx_url: '/api/resumes/r1/docx', tex_url: '/api/resumes/r1/latex',
  resume: {
    professional_summary: 'Old summary.', skills: ['Python', 'Docker'],
    experience: [{ title: 'SRE', organization: 'Acme', bullets: ['Ran clusters'] }], projects: [],
  },
};
const v2 = {
  ...v1, version_number: 2, resume_id: 'r2', kind: 'ai_rewrite', based_on: 'r1', based_on_version_number: 1, job_title: 'Sr. IT Site Reliability Software Engineer',
  company: 'Databricks', is_current: true, pdf_url: '/api/resumes/r2/pdf',
  resume: {
    professional_summary: 'New summary.', skills: ['Python', 'Kubernetes'],
    experience: [{ title: 'SRE', organization: 'Acme', bullets: ['Ran clusters', 'Cut costs by 20%'] }], projects: [],
  },
};

afterEach(cleanup);

describe('compareResumes', () => {
  it('reports skill, summary and bullet differences', () => {
    const diff = compareResumes(v1.resume, v2.resume);
    expect(diff.summaryChanged).toBe(true);
    expect(diff.skillsAdded).toEqual(['Kubernetes']);
    expect(diff.skillsRemoved).toEqual(['Docker']);
    expect(diff.experience[0].added).toEqual(['Cut costs by 20%']);
  });
});

describe('ResumeVersionHistory', () => {
  beforeEach(() => {
    window.open = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ count: 2, versions: [v2, v1] }) });
  });

  it('lists versions with current marker, preview, download and compare', async () => {
    const Preview = ({ resume }) => <div data-testid="preview">{resume.professional_summary}</div>;
    render(<ResumeVersionHistory PreviewComponent={Preview} />);

    expect(await screen.findByText('AI rewrite of Version 1 for: Sr. IT Site Reliability Software Engineer (Databricks)')).toBeInTheDocument();
    const rows = screen.getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Version 2Current');
    expect(rows[1]).toHaveTextContent('Version 1');
    expect(rows[1]).not.toHaveTextContent('Current');

    fireEvent.click(within(rows[1]).getByRole('button', { name: /Download/ }));
    expect(window.open).toHaveBeenCalledWith(expect.stringContaining('/api/resumes/r1/docx'), '_blank', 'noopener');

    fireEvent.click(within(rows[0]).getByRole('button', { name: /Preview/ }));
    expect(screen.getByTestId('preview')).toHaveTextContent('New summary.');
    fireEvent.click(screen.getByRole('button', { name: 'Close preview' }));

    fireEvent.click(screen.getByRole('button', { name: /Compare/ }));
    const panel = screen.getByTestId('version-comparison');
    expect(panel).toHaveTextContent('Version 1 vs Version 2');
    // Opens on the side-by-side page view: both resumes rendered as pages.
    const pages = within(panel).getByTestId('compare-pages');
    expect(within(pages).getAllByTestId('preview').map((p) => p.textContent)).toEqual(['Old summary.', 'New summary.']);
    fireEvent.click(within(panel).getByRole('tab', { name: 'Changes' }));
    expect(panel).toHaveTextContent('Kubernetes');
    expect(panel).toHaveTextContent('Cut costs by 20%');
  });

  it('shows the uploaded original file separately from generated versions', async () => {
    global.fetch = vi.fn().mockImplementation((url) => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(url.includes('/api/resume/uploaded')
        ? { uploaded: { filename: 'Elakiya_Resume.pdf', uploaded_at: '2026-10-18T09:45:00Z', resume: { professional_summary: 'Original summary.', skills: ['Python'] }, preview_url: '/api/resume/uploaded/file', download_url: '/api/resume/uploaded/file?download=true' } }
        : { count: 2, versions: [v2, v1] }),
    }));
    render(<ResumeVersionHistory />);

    const uploaded = await screen.findByTestId('uploaded-resume');
    expect(uploaded).toHaveTextContent('Version 1');
    expect(uploaded).toHaveTextContent('Elakiya_Resume.pdf');
    expect(uploaded).toHaveTextContent('Uploaded');
    fireEvent.click(within(uploaded).getByRole('button', { name: /Download/ }));
    expect(window.open).toHaveBeenCalledWith(expect.stringContaining('/api/resume/uploaded/file?download=true'), '_blank', 'noopener');
    expect(await screen.findByText('AI Versions')).toBeInTheDocument();
    expect(screen.getByText('AI rewrite of Version 2 for: Sr. IT Site Reliability Software Engineer (Databricks)')).toBeInTheDocument();

    // The uploaded original can be compared with any generated or edited version.
    fireEvent.change(screen.getByLabelText('First version'), { target: { value: 'uploaded' } });
    fireEvent.click(screen.getByRole('button', { name: /^Compare$/ }));
    const panel = screen.getByTestId('version-comparison');
    expect(panel).toHaveTextContent('Version 1 (uploaded) vs Version 2');
    expect(panel).toHaveTextContent('Original summary.');
    expect(panel).toHaveTextContent('Docker');
  });

  it('shows an empty state with no versions', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ count: 0, versions: [] }) });
    render(<ResumeVersionHistory />);
    expect(await screen.findByText(/No tailored resumes yet/)).toBeInTheDocument();
  });
});

describe('DataExport', () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    // jsdom cannot navigate to blob: URLs
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'attachment; filename="cafy-export-20261030.zip"' },
      blob: () => Promise.resolve(new Blob(['zip'])),
    });
  });

  const jobs = [
    { id: 'j1', title: 'SRE', company: 'Databricks', url: 'https://x/1' },
    { id: 'j2', title: 'Other', company: 'Nope', url: 'https://x/2' },
  ];

  it('sends selected parts and pipeline applications', async () => {
    render(<DataExport pipelineJobIds={new Set(['j1'])} allJobs={jobs} />);
    fireEvent.click(screen.getByLabelText(/Profile Data/));
    fireEvent.click(screen.getByRole('button', { name: /Create Export/ }));

    await screen.findByText(/Export ready: cafy-export-20261030.zip/);
    const body = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(body.include).toEqual(['resumes', 'applications']);
    expect(body.applications).toEqual([
      { job_id: 'j1', title: 'SRE', company: 'Databricks', status: 'In pipeline', url: 'https://x/1' },
    ]);
  });

  it('Complete Data toggles everything and disables export when empty', () => {
    render(<DataExport pipelineJobIds={new Set()} allJobs={[]} />);
    const complete = screen.getByLabelText(/Complete Data/);
    expect(complete).toBeChecked();
    fireEvent.click(complete);
    expect(screen.getByLabelText(/Profile Data/)).not.toBeChecked();
    expect(screen.getByRole('button', { name: /Create Export/ })).toBeDisabled();
  });

  it('shows the server error', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 400, json: () => Promise.resolve({ detail: 'Choose at least one item to export.' }) });
    render(<DataExport pipelineJobIds={new Set()} allJobs={[]} />);
    fireEvent.click(screen.getByRole('button', { name: /Create Export/ }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Choose at least one item to export.'));
  });
});

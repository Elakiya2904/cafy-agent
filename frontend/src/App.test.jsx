import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DirectoryView, JobDetailModal } from './App.jsx';

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
});

describe('Cafy Agent job application drawer', () => {
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
            />
          )}
        </>
      );
    }

    render(<DrawerHarness />);
    screen.debug();
    fireEvent.click(screen.getByRole('button', { name: /Show 1 matching jobs/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Apply/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Apply/i }));

    expect(screen.getByText(/Application workflow/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Requirements/i }));
    expect(screen.getByText(/Required & preferred skills/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Company/i }));
    expect(screen.getByText(/Google/i)).toBeInTheDocument();
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

    fireEvent.click(screen.getByRole('button', { name: /Download/i }));

    const appButton = screen.getByRole('button', { name: /Open application/i });
    fireEvent.click(appButton);
    expect(window.open).toHaveBeenCalled();
  });
});

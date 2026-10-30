// @vitest-environment jsdom
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProfileStrengthMeter } from './App.jsx';

const mockResumeWithStrength = {
  candidate_name: 'Devon Carter',
  email: 'devon@example.com',
  phone: '+1 555-0199',
  linkedin: 'linkedin.com/in/devoncarter',
  github: 'github.com/devoncarter',
  filename: 'devon_resume.pdf',
  skills: ['Python', 'Docker', 'Kubernetes', 'FastAPI', 'PostgreSQL'],
  total_skills: 5,
  seniority_level: 'Mid-Level',
  years_of_experience: 3,
  target_roles: ['DevOps Engineer'],
  summary: 'Experienced DevOps engineer specializing in container orchestration and scalable cloud infrastructure.',
  experience: [
    {
      title: 'DevOps Engineer',
      company: 'ScaleOps',
      dates: '2021 - Present',
      bullets: ['Automated CI/CD pipelines reducing deployment times by 40%']
    }
  ],
  education: [],
  projects: [],
  certifications: [],
  profile_strength: {
    overall_score: 62,
    strength_tier: 'Competitive',
    tier_badge_color: 'amber',
    sections: {
      skills: { name: 'Technical Skills', score: 70, status: 'in_progress', weight: 25, details: '5 skills listed', gaps: ['Add 5 more skills'] },
      experience: { name: 'Work Experience', score: 75, status: 'in_progress', weight: 25, details: '1 role documented', gaps: [] },
      education: { name: 'Education', score: 0, status: 'incomplete', weight: 15, details: 'No education listed', gaps: ['Add degree'] },
      basics: { name: 'Contact & Summary', score: 100, status: 'complete', weight: 15, details: 'Complete (2 links)', gaps: [] },
      projects: { name: 'Projects', score: 0, status: 'incomplete', weight: 10, details: 'No projects added', gaps: ['Add projects'] },
      certifications: { name: 'Certifications', score: 0, status: 'incomplete', weight: 10, details: 'No certifications listed', gaps: ['Add certs'] }
    },
    incomplete_sections: ['education', 'projects', 'certifications'],
    suggestions: [
      {
        id: 'add_education',
        section: 'education',
        priority: 'high',
        impact: '+13%',
        title: 'Add Degree & University Details',
        text: 'Specify your university/college, degree title, and graduation year.'
      },
      {
        id: 'add_projects',
        section: 'projects',
        priority: 'medium',
        impact: '+8%',
        title: 'Add 1-2 Highlight Projects',
        text: 'Showcase technical projects detailing tools and architecture.'
      }
    ]
  }
};

beforeEach(() => {
  document.body.innerHTML = '<div id="root"></div>';
});

describe('Profile Strength Meter Component', () => {
  it('renders overall completeness score, tier badge, and progress', () => {
    render(<ProfileStrengthMeter resume={mockResumeWithStrength} onUpdateResume={vi.fn()} onUploadNew={vi.fn()} />);

    expect(screen.getByText('62%')).toBeInTheDocument();
    expect(screen.getByText('Competitive')).toBeInTheDocument();
  });

  it('evaluates and displays all 6 sections with completion percentages', () => {
    render(<ProfileStrengthMeter resume={mockResumeWithStrength} onUpdateResume={vi.fn()} onUploadNew={vi.fn()} />);

    expect(screen.getByText('Technical Skills')).toBeInTheDocument();
    expect(screen.getByText('Work Experience')).toBeInTheDocument();
    expect(screen.getByText('Education')).toBeInTheDocument();
    expect(screen.getByText('Contact & Summary')).toBeInTheDocument();
    expect(screen.getByText('Projects')).toBeInTheDocument();
    expect(screen.getByText('Certifications')).toBeInTheDocument();

    expect(screen.getByText('70%')).toBeInTheDocument();
    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('highlights incomplete sections banner', () => {
    render(<ProfileStrengthMeter resume={mockResumeWithStrength} onUpdateResume={vi.fn()} onUploadNew={vi.fn()} />);

    expect(screen.getByText(/Incomplete Sections \(3\):/i)).toBeInTheDocument();
    expect(screen.getByText('+ Add Education (0%)')).toBeInTheDocument();
    expect(screen.getByText('+ Add Projects (0%)')).toBeInTheDocument();
    expect(screen.getByText('+ Add Certifications (0%)')).toBeInTheDocument();
  });

  it('suggests what users should add next with impact tags', () => {
    render(<ProfileStrengthMeter resume={mockResumeWithStrength} onUpdateResume={vi.fn()} onUploadNew={vi.fn()} />);

    expect(screen.getByText(/Suggestions to Maximize Profile Strength/i)).toBeInTheDocument();
    expect(screen.getByText('Add Degree & University Details')).toBeInTheDocument();
    expect(screen.getByText('Impact: +13%')).toBeInTheDocument();
    expect(screen.getByText('Add 1-2 Highlight Projects')).toBeInTheDocument();
    expect(screen.getByText('Impact: +8%')).toBeInTheDocument();
  });

  it('opens the profile editor modal when clicking edit button', () => {
    render(<ProfileStrengthMeter resume={mockResumeWithStrength} onUpdateResume={vi.fn()} onUploadNew={vi.fn()} />);

    const editBtn = screen.getByText('Edit & Boost Profile');
    fireEvent.click(editBtn);

    expect(screen.getByText('Edit Profile & Boost Completeness')).toBeInTheDocument();
    expect(screen.getByText(/Technical Skills \(5 listed\)/i)).toBeInTheDocument();
  });
});

"""SQLite schema for Pipeline 4 (AI Job Intelligence & Hiring Process Discovery).

Company intelligence is stored once per company and reused; role-specific hiring
information is stored separately per (company, job).
"""

JOB_INTELLIGENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS company_intelligence (
    company_id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    industry TEXT,
    overview TEXT,
    official_website TEXT,
    career_page TEXT,
    details TEXT NOT NULL DEFAULT '{}',
    last_researched TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_intelligence (
    job_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    description_hash TEXT,
    role_overview TEXT NOT NULL DEFAULT '{}',
    responsibilities TEXT NOT NULL DEFAULT '[]',
    required_skills TEXT NOT NULL DEFAULT '[]',
    experience_requirements TEXT NOT NULL DEFAULT '[]',
    qualifications TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hiring_processes (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    stage_key TEXT NOT NULL,
    stage_order INTEGER NOT NULL,
    hiring_stage TEXT NOT NULL,
    stage_description TEXT,
    assessment_type TEXT,
    interview_format TEXT,
    confidence_status TEXT NOT NULL,
    scope TEXT,
    conflict INTEGER NOT NULL DEFAULT 0,
    researched_at TEXT NOT NULL,
    UNIQUE(company_id, job_id, stage_key)
);

CREATE TABLE IF NOT EXISTS hiring_process_sources (
    id TEXT PRIMARY KEY,
    hiring_process_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_type TEXT NOT NULL,
    is_official INTEGER NOT NULL DEFAULT 0,
    evidence TEXT NOT NULL,
    publication_date TEXT,
    last_verified TEXT NOT NULL,
    link_status TEXT
);

CREATE TABLE IF NOT EXISTS hiring_research_runs (
    company_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    researched_at TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '[]',
    sources_checked TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (company_id, job_id)
);

CREATE TABLE IF NOT EXISTS candidate_preparation (
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    existing_skills TEXT NOT NULL DEFAULT '[]',
    missing_skills TEXT NOT NULL DEFAULT '[]',
    recommended_topics TEXT NOT NULL DEFAULT '[]',
    preparation_plan TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (candidate_id, job_id)
);

CREATE TABLE IF NOT EXISTS intelligence_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    section TEXT NOT NULL,
    stage_key TEXT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

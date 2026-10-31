"""SQLite schema for Pipeline 2 (AI Application Automation).

``user_id`` from the spec is stored as ``candidate_id`` (same scoping as Pipeline 3).
"""

JOB_APPLICATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_applications (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    job_id TEXT,
    company TEXT NOT NULL,
    job_title TEXT NOT NULL,
    location TEXT,
    job_description TEXT,
    application_url TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    blocked_reason TEXT,
    approved_at TEXT,
    applied_at TEXT,
    resume_version_id TEXT,
    ats_platform TEXT,
    external_reference_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_applications_candidate ON job_applications(candidate_id, status);
CREATE INDEX IF NOT EXISTS idx_job_applications_job ON job_applications(candidate_id, job_id);

CREATE TABLE IF NOT EXISTS application_form_data (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    field_key TEXT NOT NULL,
    field_name TEXT NOT NULL,
    field_type TEXT,
    category TEXT,
    required INTEGER NOT NULL DEFAULT 0,
    options TEXT NOT NULL DEFAULT '[]',
    field_value TEXT,
    field_source TEXT NOT NULL DEFAULT 'unknown',
    completion_status TEXT NOT NULL DEFAULT 'needs_input',
    approval_status TEXT NOT NULL DEFAULT 'pending',
    note TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(application_id, field_key)
);

CREATE TABLE IF NOT EXISTS application_submissions (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    result TEXT NOT NULL,
    confirmation_reference TEXT,
    error_details TEXT,
    signals TEXT
);

CREATE TABLE IF NOT EXISTS application_documents (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    field_key TEXT,
    document_type TEXT NOT NULL,
    resume_version TEXT,
    filename TEXT,
    permission_granted INTEGER NOT NULL DEFAULT 0,
    upload_status TEXT NOT NULL DEFAULT 'permission_required',
    detail TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(application_id, document_type, field_key)
);

CREATE TABLE IF NOT EXISTS application_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    detail TEXT
);
"""

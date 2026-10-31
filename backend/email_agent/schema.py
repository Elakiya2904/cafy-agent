"""SQLite schema for Pipeline 3 (Email Agent & Interview Management).

Every row carries ``candidate_id`` so records are always scoped to the
authenticated candidate.
"""

EMAIL_AGENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    job_id TEXT,
    company TEXT NOT NULL,
    job_title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'applied',
    applied_at TEXT NOT NULL,
    recruiter_email TEXT,
    application_ref TEXT,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_candidate_job
    ON applications(candidate_id, job_id) WHERE job_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS connected_email_accounts (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT,
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TEXT,
    scopes TEXT,
    timezone TEXT NOT NULL DEFAULT 'Europe/London',
    status TEXT NOT NULL DEFAULT 'connected',
    last_synced_at TEXT,
    last_error TEXT,
    connected_at TEXT NOT NULL,
    disconnected_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_candidate_provider_email
    ON connected_email_accounts(candidate_id, provider, email);

CREATE TABLE IF NOT EXISTS email_messages (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    thread_id TEXT,
    sender TEXT,
    sender_email TEXT,
    subject TEXT,
    body TEXT,
    direction TEXT NOT NULL DEFAULT 'received',
    received_at TEXT NOT NULL,
    category TEXT,
    application_id TEXT,
    match_status TEXT NOT NULL DEFAULT 'unprocessed',
    processing_status TEXT NOT NULL DEFAULT 'pending',
    dedupe_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_account_msg ON email_messages(account_id, message_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_dedupe ON email_messages(candidate_id, dedupe_hash);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON email_messages(candidate_id, thread_id);

CREATE TABLE IF NOT EXISTS email_classifications (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    message_row_id TEXT NOT NULL,
    category TEXT NOT NULL,
    extracted TEXT NOT NULL,
    confidence REAL NOT NULL,
    application_id TEXT,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interviews (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    application_id TEXT NOT NULL,
    message_row_id TEXT,
    thread_id TEXT,
    company TEXT,
    job_title TEXT,
    interview_date TEXT,
    interview_time TEXT,
    timezone TEXT,
    timezone_assumed INTEGER NOT NULL DEFAULT 0,
    duration_minutes INTEGER,
    interview_type TEXT,
    platform TEXT,
    meeting_link TEXT,
    recruiter_name TEXT,
    recruiter_email TEXT,
    requests_availability INTEGER NOT NULL DEFAULT 0,
    missing_fields TEXT NOT NULL DEFAULT '[]',
    proposed_slots TEXT NOT NULL DEFAULT '[]',
    conflicts TEXT NOT NULL DEFAULT '[]',
    scheduling_status TEXT NOT NULL DEFAULT 'invitation_received',
    calendar_event_id TEXT,
    calendar_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_drafts (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    account_id TEXT,
    kind TEXT NOT NULL DEFAULT 'reply',
    original_message_id TEXT,
    application_id TEXT,
    interview_id TEXT,
    thread_id TEXT,
    to_email TEXT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    send_status TEXT NOT NULL DEFAULT 'unsent',
    send_error TEXT,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS follow_up_records (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    application_id TEXT NOT NULL,
    draft_id TEXT,
    follow_up_date TEXT NOT NULL,
    draft TEXT NOT NULL,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    sent_at TEXT,
    calendar_event_id TEXT,
    calendar_error TEXT,
    reminder_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    entity TEXT,
    status TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS agent_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    application_id TEXT,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

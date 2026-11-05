"""create feature tables previously initialized at runtime

Revision ID: 20261104_02
Revises: 20261104_01
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20261104_02"
down_revision: Union[str, Sequence[str], None] = "20261104_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, source_job_id TEXT NOT NULL, title TEXT NOT NULL,
        company TEXT NOT NULL, platform TEXT NOT NULL, location TEXT,
        is_remote INTEGER DEFAULT 0, url TEXT NOT NULL, description TEXT,
        department TEXT, employment_type TEXT, posted_at TEXT,
        extracted_skills TEXT, first_seen TEXT NOT NULL, last_checked TEXT NOT NULL,
        status TEXT DEFAULT 'active'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scraper_runs (
        id BIGSERIAL PRIMARY KEY, platform TEXT NOT NULL, started_at TEXT NOT NULL,
        finished_at TEXT NOT NULL, duration_seconds DOUBLE PRECISION,
        jobs_found INTEGER DEFAULT 0, new_jobs INTEGER DEFAULT 0,
        updated_jobs INTEGER DEFAULT 0, status TEXT NOT NULL, error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tailored_resumes (
        id TEXT PRIMARY KEY, job_id TEXT NOT NULL, resume_id TEXT NOT NULL,
        structured_data TEXT NOT NULL, updated_at TEXT NOT NULL,
        created_at TEXT NOT NULL, candidate_id TEXT NOT NULL DEFAULT 'local'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tailored_resume_versions (
        id TEXT PRIMARY KEY, resume_id TEXT NOT NULL UNIQUE, job_id TEXT NOT NULL,
        job_title TEXT, company TEXT, structured_data TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'generated', based_on TEXT,
        candidate_id TEXT NOT NULL DEFAULT 'local'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS applications (
        id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, job_id TEXT,
        company TEXT, job_title TEXT, status TEXT, applied_at TEXT,
        recruiter_email TEXT, application_ref TEXT, updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS connected_email_accounts (
        id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, provider TEXT NOT NULL,
        email TEXT, display_name TEXT, access_token TEXT, refresh_token TEXT,
        token_expires_at TEXT, scopes TEXT, timezone TEXT, status TEXT,
        last_synced_at TEXT, last_error TEXT, connected_at TEXT,
        disconnected_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS email_messages (
        id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, account_id TEXT,
        message_id TEXT, thread_id TEXT, sender TEXT, sender_email TEXT,
        subject TEXT, body TEXT, direction TEXT, received_at TEXT,
        category TEXT, application_id TEXT, match_status TEXT,
        processing_status TEXT, dedupe_hash TEXT, created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS email_classifications (
        id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, message_row_id TEXT,
        category TEXT, extracted TEXT, confidence DOUBLE PRECISION,
        application_id TEXT, processed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS interviews (
        id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, application_id TEXT,
        message_row_id TEXT, thread_id TEXT, company TEXT, job_title TEXT,
        interview_date TEXT, interview_time TEXT, timezone TEXT,
        timezone_assumed INTEGER, duration_minutes INTEGER, interview_type TEXT,
        platform TEXT, meeting_link TEXT, recruiter_name TEXT,
        recruiter_email TEXT, requests_availability INTEGER, missing_fields TEXT,
        proposed_slots TEXT, conflicts TEXT, scheduling_status TEXT,
        calendar_event_id TEXT, calendar_error TEXT, created_at TEXT, updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS email_drafts (
        id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, account_id TEXT,
        kind TEXT, original_message_id TEXT, application_id TEXT,
        interview_id TEXT, thread_id TEXT, to_email TEXT, subject TEXT,
        body TEXT, approval_status TEXT, send_status TEXT, send_error TEXT,
        created_at TEXT, approved_at TEXT, sent_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS follow_up_records (
        id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, application_id TEXT,
        draft_id TEXT, follow_up_date TEXT, draft TEXT, approval_status TEXT,
        sent_at TEXT, calendar_event_id TEXT, calendar_error TEXT, reminder_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_logs (
        id BIGSERIAL PRIMARY KEY, candidate_id TEXT NOT NULL, ts TEXT,
        action TEXT, entity TEXT, status TEXT, detail TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_notifications (
        id BIGSERIAL PRIMARY KEY, candidate_id TEXT NOT NULL, kind TEXT,
        message TEXT, application_id TEXT, is_read INTEGER DEFAULT 0,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_applications (
        id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, job_id TEXT,
        company TEXT, job_title TEXT, location TEXT, job_description TEXT,
        application_url TEXT, status TEXT, blocked_reason TEXT, approved_at TEXT,
        applied_at TEXT, resume_version_id TEXT, ats_platform TEXT,
        external_reference_id TEXT, created_at TEXT, updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS application_form_data (
        id TEXT PRIMARY KEY, application_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
        field_key TEXT, field_name TEXT, field_type TEXT, category TEXT,
        required INTEGER DEFAULT 0, options TEXT, field_value TEXT,
        field_source TEXT, completion_status TEXT, approval_status TEXT,
        note TEXT, updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS application_submissions (
        id TEXT PRIMARY KEY, application_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
        submitted_at TEXT, result TEXT, confirmation_reference TEXT,
        error_details TEXT, signals TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS application_documents (
        id TEXT PRIMARY KEY, application_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
        field_key TEXT, document_type TEXT, resume_version TEXT, filename TEXT,
        permission_granted INTEGER DEFAULT 0, upload_status TEXT, detail TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS application_events (
        id BIGSERIAL PRIMARY KEY, application_id TEXT NOT NULL,
        candidate_id TEXT NOT NULL, ts TEXT, event TEXT, detail TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_intelligence (
        company_id TEXT PRIMARY KEY, company_name TEXT, industry TEXT,
        overview TEXT, official_website TEXT, career_page TEXT, details TEXT,
        last_researched TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_intelligence (
        job_id TEXT PRIMARY KEY, company_id TEXT, description_hash TEXT,
        role_overview TEXT, responsibilities TEXT, required_skills TEXT,
        experience_requirements TEXT, qualifications TEXT, updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS hiring_processes (
        id TEXT PRIMARY KEY, company_id TEXT, job_id TEXT, stage_key TEXT,
        stage_order INTEGER, hiring_stage TEXT, stage_description TEXT,
        assessment_type TEXT, interview_format TEXT, confidence_status TEXT,
        scope TEXT, conflict TEXT, researched_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS hiring_process_sources (
        id TEXT PRIMARY KEY, hiring_process_id TEXT, source_url TEXT,
        source_type TEXT, is_official INTEGER DEFAULT 0, evidence TEXT,
        publication_date TEXT, last_verified TEXT, link_status TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS hiring_research_runs (
        company_id TEXT NOT NULL, job_id TEXT NOT NULL, researched_at TEXT,
        notes TEXT, sources_checked TEXT, PRIMARY KEY (company_id, job_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_preparation (
        candidate_id TEXT NOT NULL, job_id TEXT NOT NULL, existing_skills TEXT,
        missing_skills TEXT, recommended_topics TEXT, preparation_plan TEXT,
        updated_at TEXT, PRIMARY KEY (candidate_id, job_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS intelligence_reports (
        id BIGSERIAL PRIMARY KEY, candidate_id TEXT NOT NULL, job_id TEXT,
        section TEXT, stage_key TEXT, message TEXT, created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_alert_preferences (
        candidate_id TEXT PRIMARY KEY, roles_json TEXT, locations_json TEXT,
        employment_types_json TEXT, experience_levels_json TEXT,
        sponsorship_only INTEGER DEFAULT 0, daily_enabled INTEGER DEFAULT 1,
        email_enabled INTEGER DEFAULT 0, last_run_date TEXT, updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_alert_matches (
        candidate_id TEXT NOT NULL, job_id TEXT NOT NULL,
        match_score DOUBLE PRECISION, created_at TEXT,
        PRIMARY KEY (candidate_id, job_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_alert_notifications (
        id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, job_id TEXT,
        message TEXT, is_read INTEGER DEFAULT 0, created_at TEXT
    )
    """,
)


def upgrade() -> None:
    for statement in TABLES:
        op.execute(statement)


def downgrade() -> None:
    for table in (
        "job_alert_notifications", "job_alert_matches", "job_alert_preferences",
        "intelligence_reports", "candidate_preparation", "hiring_research_runs",
        "hiring_process_sources", "hiring_processes", "job_intelligence",
        "company_intelligence", "application_events", "application_documents",
        "application_submissions", "application_form_data", "job_applications",
        "agent_notifications", "agent_logs", "follow_up_records", "email_drafts",
        "interviews", "email_classifications", "email_messages",
        "connected_email_accounts", "applications", "tailored_resume_versions",
        "tailored_resumes", "scraper_runs", "jobs",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")

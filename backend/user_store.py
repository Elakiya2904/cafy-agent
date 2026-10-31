"""Per-user persistence for the parsed résumé and the original uploaded file (Postgres/SQLite via JobDatabase)."""
import json
import logging
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .context import current_candidate

logger = logging.getLogger("cafy.user_store")

MAX_RESUME_BYTES = 10 * 1024 * 1024
_MATCH_CACHE_USERS = 256


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserStore:
    def __init__(self, database):
        self.db = database

    # ------------------------------------------------------------ parsed résumé
    def get_resume(self, candidate: str) -> Optional[Dict[str, Any]]:
        with self.db._get_connection() as conn:
            row = conn.execute("SELECT resume_json FROM user_profiles WHERE candidate_id = ?", (candidate,)).fetchone()
        return json.loads(row["resume_json"]) if row and row["resume_json"] else None

    def set_resume(self, candidate: str, resume: Optional[Dict[str, Any]]) -> None:
        with self.db._get_connection() as conn:
            conn.execute(
                "INSERT INTO user_profiles (candidate_id, resume_json, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(candidate_id) DO UPDATE SET resume_json=excluded.resume_json, updated_at=excluded.updated_at",
                (candidate, json.dumps(resume, ensure_ascii=False) if resume is not None else None, _now()))
            conn.commit()

    # --------------------------------------------------------- original upload
    def save_file(self, candidate: str, filename: str, content_type: Optional[str], content: bytes,
                  parsed_resume: Optional[Dict[str, Any]]) -> None:
        if len(content) > MAX_RESUME_BYTES:
            raise ValueError("Résumé file is larger than 10 MB.")
        with self.db._get_connection() as conn:
            conn.execute(
                "INSERT INTO user_resume_files (candidate_id, filename, content_type, size_bytes, content, parsed_resume, uploaded_at) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET filename=excluded.filename, "
                "content_type=excluded.content_type, size_bytes=excluded.size_bytes, content=excluded.content, "
                "parsed_resume=excluded.parsed_resume, uploaded_at=excluded.uploaded_at",
                (candidate, filename or "resume", content_type or "application/octet-stream", len(content), content,
                 json.dumps(parsed_resume or {}, ensure_ascii=False), _now()))
            conn.commit()

    def file_meta(self, candidate: str) -> Optional[Dict[str, Any]]:
        with self.db._get_connection() as conn:
            row = conn.execute("SELECT filename, content_type, size_bytes, parsed_resume, uploaded_at FROM user_resume_files "
                               "WHERE candidate_id = ?", (candidate,)).fetchone()
        if not row:
            return None
        meta = dict(row)
        meta["resume"] = json.loads(meta.pop("parsed_resume") or "{}")
        return meta

    def clear_file(self, candidate: str) -> None:
        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM user_resume_files WHERE candidate_id = ?", (candidate,))
            conn.commit()

    def file_content(self, candidate: str) -> Optional[Dict[str, Any]]:
        with self.db._get_connection() as conn:
            row = conn.execute("SELECT filename, content_type, content FROM user_resume_files WHERE candidate_id = ?", (candidate,)).fetchone()
        if not row:
            return None
        return {"filename": row["filename"], "content_type": row["content_type"], "content": bytes(row["content"])}


class UserSession:
    """Dict-like view of the *current request's user*: ``session["resume"]``, ``session["last_matched_jobs"]``.

    The résumé lives in the database (shared by every worker/instance); matched jobs are a recomputable
    per-process cache that is dropped whenever the résumé changes.
    """

    def __init__(self, store: UserStore):
        self.store = store
        self._matches: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str, default: Any = None) -> Any:
        value = self[key]
        return default if value is None else value

    def __getitem__(self, key: str) -> Any:
        candidate = current_candidate()
        if key == "resume":
            return self.store.get_resume(candidate)
        if key == "last_matched_jobs":
            with self._lock:
                return self._matches.get(candidate, [])
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        candidate = current_candidate()
        if key == "resume":
            self.store.set_resume(candidate, value)
            with self._lock:
                self._matches.pop(candidate, None)
        elif key == "last_matched_jobs":
            with self._lock:
                self._matches[candidate] = value
                self._matches.move_to_end(candidate)
                while len(self._matches) > _MATCH_CACHE_USERS:
                    self._matches.popitem(last=False)
        else:
            raise KeyError(key)

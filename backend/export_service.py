"""Builds the "Export Your Data" ZIP archive for Cafy Agent."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

EXPORT_PARTS = ("profile", "resumes", "applications")


def build_export_zip(
    include: Iterable[str],
    profile: Optional[Dict[str, Any]],
    applications: List[Dict[str, Any]],
    versions: List[Dict[str, Any]],
    resume_dir: Path,
) -> bytes:
    """Return ZIP bytes containing only the requested parts."""
    parts = set(include)
    buffer = io.BytesIO()
    manifest: Dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "included": sorted(parts & set(EXPORT_PARTS)),
        "notes": [],
    }

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if "profile" in parts:
            if profile:
                archive.writestr("profile.json", json.dumps(profile, indent=2, ensure_ascii=False, default=str))
            else:
                manifest["notes"].append("No profile was loaded, so profile.json was not included.")

        if "applications" in parts:
            archive.writestr("applications.json", json.dumps(applications, indent=2, ensure_ascii=False))

        if "resumes" in parts:
            metadata = []
            for version in versions:
                resume_id = version["resume_id"]
                stem = f"version-{version['version_number']}"
                files = []
                for ext in ("pdf", "docx", "tex"):
                    source = resume_dir / f"{resume_id}.{ext}"
                    if source.is_file():
                        name = f"resumes/{stem}.{ext}"
                        archive.write(source, name)
                        files.append(name)
                metadata.append({key: version.get(key) for key in (
                    "version_number", "resume_id", "job_id", "job_title", "company", "created_at", "updated_at",
                )} | {"files": files})
            archive.writestr("resumes/versions.json", json.dumps(metadata, indent=2, ensure_ascii=False))
            if not versions:
                manifest["notes"].append("No generated resumes exist yet.")

        archive.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buffer.getvalue()

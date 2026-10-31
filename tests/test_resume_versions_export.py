import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, ".")
from backend.database import JobDatabase
from backend.export_service import build_export_zip
from backend.user_store import UserSession, UserStore


def bind_main_to_db(main, db, resume=None):
    """Point the app's data layer at ``db`` (a real, temporary database) and give the dev user an optional résumé."""
    store = UserStore(db)
    if resume is not None:
        store.set_resume("local", resume)
    return [mock.patch.object(main, "db", db), mock.patch.object(main, "user_store", store),
            mock.patch.object(main, "ACTIVE_SESSION", UserSession(store))]


class TestResumeVersions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = os.path.join(self.tmp.name, "test.db")
        self.db = JobDatabase(db_path=self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_versions_numbered_newest_first(self):
        self.db.save_resume_version("r1", "job-a", {"skills": ["Python"]}, job_title="SRE", company="Databricks")
        self.db.save_resume_version("r2", "job-b", {"skills": ["Go"]}, job_title="DevOps", company="Google")
        versions = self.db.list_resume_versions()
        self.assertEqual([v["resume_id"] for v in versions], ["r2", "r1"])
        self.assertEqual([v["version_number"] for v in versions], [2, 1])
        self.assertTrue(versions[0]["is_current"])
        self.assertFalse(versions[1]["is_current"])
        self.assertEqual(versions[1]["company"], "Databricks")

    def test_save_updates_existing_version(self):
        self.db.save_resume_version("r1", "job-a", {"skills": ["Python"]}, job_title="SRE", company="Acme")
        self.db.save_resume_version("r1", "job-a", {"skills": ["Python", "Go"]})
        versions = self.db.list_resume_versions()
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["resume"]["skills"], ["Python", "Go"])
        self.assertEqual(versions[0]["job_title"], "SRE")  # kept when not supplied

    def test_backfill_from_existing_tailored_resumes(self):
        self.db.save_tailored_resume("job-x", "legacy-1", {"skills": ["Rust"]})
        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM tailored_resume_versions")
        reopened = JobDatabase(db_path=self.db_path)
        versions = reopened.list_resume_versions()
        self.assertEqual([v["resume_id"] for v in versions], ["legacy-1"])
        # Re-initialising again must not duplicate
        self.assertEqual(len(JobDatabase(db_path=self.db_path).list_resume_versions()), 1)


class TestExportZip(unittest.TestCase):
    def test_only_requested_parts(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = Path(tmp)
            (out / "r1.docx").write_bytes(b"docx")
            (out / "r1.tex").write_text("tex")
            versions = [{"version_number": 1, "resume_id": "r1", "job_id": "j", "job_title": "SRE",
                         "company": "Acme", "created_at": "t", "updated_at": "t"}]
            data = build_export_zip(["resumes", "applications"], {"candidate_name": "X"},
                                    [{"title": "SRE"}], versions, out)
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
            self.assertIn("resumes/version-1.docx", names)
            self.assertIn("resumes/version-1.tex", names)
            self.assertNotIn("resumes/version-1.pdf", names)
            self.assertIn("applications.json", names)
            self.assertNotIn("profile.json", names)

    def test_profile_missing_is_noted(self):
        data = build_export_zip(["profile"], None, [], [], Path("."))
        archive = zipfile.ZipFile(io.BytesIO(data))
        self.assertNotIn("profile.json", archive.namelist())
        self.assertTrue(json.loads(archive.read("manifest.json"))["notes"])


class TestExportEndpoints(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from backend import main
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.test_db = JobDatabase(db_path=os.path.join(self.tmp.name, "api.db"))
        self.test_db.save_resume_version("api-r1", "job-a", {"skills": ["Python"]}, job_title="SRE", company="Acme")
        self.patches = bind_main_to_db(main, self.test_db, {"candidate_name": "Test User"})
        for p in self.patches:
            p.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_versions_endpoint(self):
        body = self.client.get("/api/resumes/versions").json()
        self.assertEqual(body["count"], 1)
        version = body["versions"][0]
        self.assertEqual(version["version_number"], 1)
        self.assertTrue(version["is_current"])
        self.assertIn("pdf_url", version)

    def test_export_endpoint(self):
        resp = self.client.post("/api/export", json={
            "include": ["profile", "applications", "resumes"],
            "applications": [{"job_id": "j1", "title": "SRE", "company": "Acme", "status": "In pipeline"}],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "application/zip")
        self.assertIn("cafy-export-", resp.headers["content-disposition"])
        archive = zipfile.ZipFile(io.BytesIO(resp.content))
        self.assertEqual(json.loads(archive.read("profile.json"))["candidate_name"], "Test User")
        self.assertEqual(json.loads(archive.read("applications.json"))[0]["company"], "Acme")
        self.assertEqual(json.loads(archive.read("resumes/versions.json"))[0]["resume_id"], "api-r1")

    def test_export_requires_selection(self):
        self.assertEqual(self.client.post("/api/export", json={"include": []}).status_code, 400)


if __name__ == "__main__":
    unittest.main()


class TestUploadedResumeEndpoints(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from backend import main
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = JobDatabase(db_path=os.path.join(self.tmp.name, "uploads.db"))
        self.patches = bind_main_to_db(main, self.db)
        for p in self.patches:
            p.start()
        self.main = main
        self.client = TestClient(main.app)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_no_upload(self):
        self.assertEqual(self.client.get("/api/resume/uploaded").json(), {"uploaded": None})
        self.assertEqual(self.client.get("/api/resume/uploaded/file").status_code, 404)

    def test_latest_upload_is_kept_and_downloadable(self):
        self.main._store_uploaded_resume("old.docx", "application/octet-stream", b"old")
        self.main._store_uploaded_resume("My Resume.pdf", "application/pdf", b"%PDF-1.4 test")
        meta = self.client.get("/api/resume/uploaded").json()["uploaded"]
        self.assertEqual(meta["filename"], "My Resume.pdf")
        self.assertEqual(meta["size_bytes"], 13)

        inline = self.client.get(meta["preview_url"])
        self.assertEqual(inline.content, b"%PDF-1.4 test")
        self.assertTrue(inline.headers["content-disposition"].startswith("inline"))
        download = self.client.get(meta["download_url"])
        self.assertTrue(download.headers["content-disposition"].startswith("attachment"))
        # Only the latest upload is stored.
        with self.db._get_connection() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM user_resume_files").fetchone()[0], 1)


class TestEditedVersions(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from backend import main
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.test_db = JobDatabase(db_path=os.path.join(self.tmp.name, "edits.db"))
        self.patches = bind_main_to_db(main, self.test_db, {"candidate_name": "Test User", "skills": ["Python"]}) + [
            # Don't render LaTeX/DOCX into the real output folder.
            mock.patch.object(main.resume_generation_svc, "update_artifacts", return_value={}),
        ]
        for p in self.patches:
            p.start()
        self.client = TestClient(main.app)
        self.base = self.client.post("/api/resumes/save", json={
            "job_id": "job-x", "resume": {"professional_summary": "First.", "skills": ["Python"]},
        }).json()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_saved_edits_update_the_current_version(self):
        saved = self.client.post("/api/resumes/save", json={
            "job_id": "job-x", "resume_id": self.base["resume_id"],
            "resume": {**self.base["resume"], "professional_summary": "Second."},
        }).json()
        self.assertEqual(saved["resume_id"], self.base["resume_id"])
        versions = self.client.get("/api/resumes/versions").json()["versions"]
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["resume"]["professional_summary"], "Second.")

    def test_each_ai_rewrite_is_a_new_version_with_recommended_skills(self):
        from backend import main
        job = {"id": "job-x", "title": "SRE", "company": "Acme", "description": "Python and Kubernetes",
               "extracted_skills": ["Python", "Kubernetes"]}

        def fake_rewrite(current, job_arg, extractor):
            return {"resume": {**current, "professional_summary": "Rewritten."}, "rejected_lines": 0}

        with mock.patch.object(self.test_db, "get_job", return_value=job),                 mock.patch.object(main.resume_generation_svc, "rewrite_full", side_effect=fake_rewrite):
            for _ in range(2):
                body = self.client.post("/api/resumes/rewrite-full", json={
                    "job_id": "job-x", "resume_id": self.base["resume_id"], "resume": self.base["resume"],
                }).json()
        self.assertEqual(body["resume"]["professional_summary"], "Rewritten.")
        self.assertEqual(body["recommended_skills"], ["Kubernetes"])
        self.assertNotIn("Kubernetes", body["resume"]["skills"])
        versions = self.client.get("/api/resumes/versions").json()["versions"]
        self.assertEqual(len(versions), 3)
        self.assertEqual([v["kind"] for v in versions], ["ai_rewrite", "ai_rewrite", "generated"])


class TestRewriteFactGuard(unittest.TestCase):
    def test_rewrite_cannot_add_numbers_or_technologies(self):
        from backend.resume_generation_service import ResumeGenerationService
        from backend.resume_service import ResumeService
        tailored = {
            "professional_summary": "Engineer working with Python.",
            "skills": ["Python"],
            "experience": [{"title": "Dev", "organization": "Acme", "dates": "2021",
                            "description": "", "bullets": ["Built APIs in Python", "Cut costs by 20%"]}],
            "projects": [],
        }
        rewritten = {
            "professional_summary": "Results-driven engineer delivering Python services.",
            "experience": [{"index": 0, "bullets": [
                "Built Kubernetes APIs in Python",        # adds a technology -> rejected
                "Reduced costs by 45%",                   # adds a number -> rejected
                "Extra invented bullet",                  # beyond original count -> dropped
            ]}],
        }
        out = ResumeGenerationService.merge_rewrite(tailored, rewritten, ResumeService())
        resume = out["resume"]
        self.assertEqual(resume["professional_summary"], "Results-driven engineer delivering Python services.")
        self.assertEqual(resume["experience"][0]["bullets"], ["Built APIs in Python", "Cut costs by 20%"])
        self.assertEqual(out["rejected_lines"], 2)
        self.assertEqual(resume["skills"], ["Python"])
        self.assertEqual(tailored["experience"][0]["bullets"][1], "Cut costs by 20%")  # input not mutated

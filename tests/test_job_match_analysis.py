import copy
import sys
import unittest
sys.path.insert(0, ".")
from backend.job_match_analysis_service import analyze_profile_for_job


JOB = {
    "id": "job-1",
    "title": "Senior DevOps Engineer",
    "company": "Acme",
    "description": (
        "We need 5+ years of experience with AWS, Kubernetes, Terraform, Docker and Python. "
        "Experience with Prometheus and Grafana is a plus. AWS Certified preferred. "
        "Bachelor's degree in Computer Science or similar."
    ),
}

PROFILE = {
    "candidate_name": "Marcus Vance",
    "email": "marcus@example.com",
    "summary": "DevOps engineer with 6 years running Kubernetes on AWS.",
    "skills": ["AWS", "Kubernetes", "Docker"],
    "years_of_experience": 6,
    "experience": [
        {
            "title": "DevOps Engineer",
            "company": "Initech",
            "dates": "2019 - 2025",
            "bullets": [
                "Managed Kubernetes clusters on AWS with Terraform",
                "Reduced deploy time by 40% using Python automation",
            ],
        }
    ],
    "education": [{"degree": "BSc Computer Science", "institution": "UCL", "dates": "2018"}],
    "projects": [],
    "certifications": [],
}


class TestJobMatchAnalysis(unittest.TestCase):
    def test_returns_all_sections_and_scores_in_range(self):
        result = analyze_profile_for_job(PROFILE, JOB)
        self.assertEqual(
            set(result["sections"]),
            {"summary", "skills", "experience", "education", "projects", "certifications"},
        )
        self.assertTrue(0 <= result["job_match_score"] <= 100)
        for section in result["sections"].values():
            self.assertTrue(0 <= section["score"] <= 100)

    def test_job_match_is_distinct_from_profile_completeness(self):
        result = analyze_profile_for_job(PROFILE, JOB)
        self.assertIn("profile_completeness", result)
        self.assertIn("overall_score", result["profile_completeness"])

    def test_matched_and_missing_skills(self):
        result = analyze_profile_for_job(PROFILE, JOB)
        self.assertIn("Kubernetes", result["matched_skills"])
        self.assertIn("Terraform", result["missing_skills"])
        # Terraform and Python appear in experience bullets but not in the skills list
        self.assertIn("Terraform", result["sections"]["skills"]["evidenced_elsewhere"])
        self.assertTrue(any("Terraform" in s["text"] for s in result["suggestions"]))

    def test_missing_certification_flagged_when_job_asks(self):
        result = analyze_profile_for_job(PROFILE, JOB)
        self.assertTrue(result["sections"]["certifications"]["missing"])

    def test_edits_raise_score(self):
        before = analyze_profile_for_job(PROFILE, JOB)
        edited = copy.deepcopy(PROFILE)
        edited["skills"] += ["Terraform", "Python", "Prometheus", "Grafana"]
        edited["certifications"] = [{"name": "AWS Certified Solutions Architect", "issuer": "AWS"}]
        edited["projects"] = [{"title": "Observability stack", "bullets": ["Prometheus and Grafana on Kubernetes"]}]
        after = analyze_profile_for_job(edited, JOB)
        self.assertGreater(after["job_match_score"], before["job_match_score"])
        self.assertGreater(after["sections"]["skills"]["score"], before["sections"]["skills"]["score"])
        self.assertGreater(after["sections"]["projects"]["score"], before["sections"]["projects"]["score"])

    def test_gap_analysis(self):
        result = analyze_profile_for_job(PROFILE, JOB)
        by_title = {g["title"]: g for g in result["gaps"]}
        # Terraform is in the experience bullets, Grafana appears nowhere
        self.assertEqual(by_title["Terraform"]["type"], "missing_from_profile")
        self.assertIn("experience", by_title["Terraform"]["detail"])
        self.assertEqual(by_title["Grafana"]["detail"], "Skill not found in your profile")
        quals = [g for g in result["gaps"] if g["type"] == "missing_qualification"]
        self.assertTrue(any(g["section"] == "certifications" for g in quals))

        senior = dict(PROFILE, years_of_experience=2)
        quals = [g for g in analyze_profile_for_job(senior, JOB)["gaps"] if g["type"] == "missing_qualification"]
        self.assertTrue(any(g["title"] == "5+ years experience" for g in quals))

    def test_empty_profile(self):
        result = analyze_profile_for_job({}, JOB)
        self.assertEqual(result["profile_completeness"]["overall_score"], 0)
        self.assertLess(result["job_match_score"], 40)

    def test_scores_are_ints_or_none(self):
        for profile, job in ((PROFILE, JOB), ({}, JOB), (STRONG_PROFILE, PLAIN_JOB), ({}, {})):
            result = analyze_profile_for_job(profile, job)
            self.assertIsInstance(result["job_match_score"], int)
            self.assertTrue(0 <= result["job_match_score"] <= 100)
            for section in result["sections"].values():
                score = section["score"]
                if score is None:
                    self.assertEqual(section["status"], "not_applicable")
                    self.assertTrue(section["not_applicable"])
                    self.assertIn("name", section)
                    self.assertIn("weight", section)
                else:
                    self.assertIsInstance(score, int)
                    self.assertTrue(0 <= score <= 100)

    def test_listed_but_unevidenced_skills_do_not_reach_100(self):
        profile = copy.deepcopy(STRONG_PROFILE)
        profile["experience"] = [{"title": "DevOps Engineer", "company": "Initech", "dates": "2019 - 2025",
                                  "bullets": ["Owned the platform roadmap", "Mentored 4 engineers"]}]
        profile["projects"] = [{"title": "Internal tool", "description": "Built an internal tool for 200 users."}]
        result = analyze_profile_for_job(profile, PLAIN_JOB)
        # every job skill is listed, but none is evidenced in experience/projects
        self.assertEqual(set(result["matched_skills"]), set(result["job_skills"]))
        self.assertLess(result["sections"]["skills"]["score"], 100)
        self.assertLessEqual(result["sections"]["skills"]["score"], 80)
        self.assertLess(result["job_match_score"], 100)

    def test_strong_but_imperfect_profile_below_100(self):
        result = analyze_profile_for_job(PROFILE, JOB)
        self.assertLess(result["job_match_score"], 100)
        self.assertLess(result["sections"]["skills"]["score"], 100)
        self.assertLess(result["sections"]["summary"]["score"], 100)
        self.assertLess(result["sections"]["experience"]["score"], 100)

    def test_short_summary_scores_less_than_ideal_length(self):
        short = dict(STRONG_PROFILE, summary="DevOps engineer, 6 years, AWS.")
        long_result = analyze_profile_for_job(STRONG_PROFILE, PLAIN_JOB)
        short_result = analyze_profile_for_job(short, PLAIN_JOB)
        self.assertLess(short_result["sections"]["summary"]["score"], long_result["sections"]["summary"]["score"])

    def test_certifications_not_applicable_when_job_does_not_ask(self):
        result = analyze_profile_for_job(STRONG_PROFILE, PLAIN_JOB)
        certs = result["sections"]["certifications"]
        self.assertIsNone(certs["score"])
        self.assertEqual(certs["status"], "not_applicable")
        self.assertTrue(certs["not_applicable"])
        self.assertEqual(certs["weight"], 5)
        self.assertFalse(any(g["section"] == "certifications" for g in result["gaps"]))

        with_certs = dict(STRONG_PROFILE, certifications=[{"name": "CKA", "issuer": "CNCF"}])
        without_certs = dict(STRONG_PROFILE, certifications=[])
        self.assertEqual(
            analyze_profile_for_job(with_certs, PLAIN_JOB)["job_match_score"],
            analyze_profile_for_job(without_certs, PLAIN_JOB)["job_match_score"],
        )

    def test_certifications_graded_when_required(self):
        none_listed = analyze_profile_for_job(PROFILE, JOB)["sections"]["certifications"]["score"]
        wrong = dict(PROFILE, certifications=[{"name": "Scrum Master", "issuer": "Scrum Alliance"}])
        right = dict(PROFILE, certifications=[{"name": "AWS Certified Solutions Architect", "issuer": "AWS"}])
        wrong_score = analyze_profile_for_job(wrong, JOB)["sections"]["certifications"]["score"]
        right_score = analyze_profile_for_job(right, JOB)["sections"]["certifications"]["score"]
        self.assertEqual(none_listed, 0)
        self.assertLess(none_listed, wrong_score)
        self.assertLess(wrong_score, right_score)

    def test_skills_not_applicable_when_job_lists_none(self):
        job = {"title": "Office Coordinator", "description": "Friendly team, great office.", "extracted_skills": []}
        result = analyze_profile_for_job(dict(PROFILE, skills=[]), dict(job))
        self.assertEqual(result["job_skills"], [])
        self.assertIsNone(result["sections"]["skills"]["score"])
        self.assertEqual(result["sections"]["skills"]["status"], "not_applicable")

    def test_education_not_applicable_without_degree_requirement_or_entry(self):
        result = analyze_profile_for_job(dict(STRONG_PROFILE, education=[]), PLAIN_JOB)
        self.assertIsNone(result["sections"]["education"]["score"])
        graded = analyze_profile_for_job(STRONG_PROFILE, PLAIN_JOB)["sections"]["education"]["score"]
        self.assertIsInstance(graded, int)

    def test_fully_evidenced_metric_rich_profile_scores_high(self):
        result = analyze_profile_for_job(STRONG_PROFILE, PLAIN_JOB)
        self.assertGreaterEqual(result["job_match_score"], 80)
        self.assertEqual(result["match_tier"], "Strong Match")

    def test_metric_proportion_is_graded(self):
        half = copy.deepcopy(STRONG_PROFILE)
        half["experience"][0]["bullets"] = [
            "Ran Kubernetes on AWS with Terraform",
            "Cut deploy time by 40% with Python and Docker",
        ]
        full = analyze_profile_for_job(STRONG_PROFILE, PLAIN_JOB)["sections"]["experience"]["score"]
        partial = analyze_profile_for_job(half, PLAIN_JOB)["sections"]["experience"]["score"]
        self.assertLess(partial, full)


PLAIN_JOB = {
    "id": "job-2",
    "title": "DevOps Engineer",
    "company": "Acme",
    "description": "We need 4+ years of experience with AWS, Kubernetes, Terraform, Docker and Python.",
}

STRONG_PROFILE = {
    "candidate_name": "Dana Reyes",
    "email": "dana@example.com",
    "summary": (
        "DevOps Engineer with 6 years of experience building cloud platforms on AWS. I run production "
        "Kubernetes clusters provisioned with Terraform, package services with Docker and automate "
        "operations in Python, cutting deployment time by 40% and keeping 99.9% uptime for 2M users."
    ),
    "skills": ["AWS", "Kubernetes", "Terraform", "Docker", "Python"],
    "years_of_experience": 6,
    "experience": [
        {
            "title": "DevOps Engineer",
            "company": "Initech",
            "dates": "2019 - 2025",
            "bullets": [
                "Migrated 40 services to Kubernetes on AWS, cutting hosting cost by 30%",
                "Provisioned infrastructure with Terraform across 3 regions, reducing setup time by 60%",
                "Containerised 25 services with Docker and automated releases in Python, saving 10 hours per week",
            ],
        }
    ],
    "education": [{"degree": "BSc Computer Science", "institution": "UCL", "dates": "2018"}],
    "projects": [
        {
            "title": "Self-healing cluster",
            "bullets": ["Python operator for Kubernetes on AWS that restarted failed pods, cutting incidents by 35%"],
        }
    ],
    "certifications": [],
}


if __name__ == "__main__":
    unittest.main()

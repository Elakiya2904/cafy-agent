"""Requirement-level, job-description-driven matching (backend/requirement_matching.py)."""
import copy
import sys
import unittest

sys.path.insert(0, ".")

from backend.requirement_matching import (
    DEFAULT_MATCH_CONFIG,
    _deep_merge,
    classify_lines,
    extract_requirements,
    score_job,
)
from backend.recommendation_service import RecommendationService

UK_LISTING = {
    "id": "uk-1",
    "title": "Data Engineer",
    "company": "Example Ltd",
    "description": (
        "<p><strong>About the role</strong></p><p>You will build pipelines in Airflow for our analysts.</p>"
        "<p><strong>Essential</strong></p><ul>"
        "<li>3+ years of experience as a data engineer</li>"
        "<li>Strong Python and SQL</li><li>Hands-on AWS</li><li>Experience with Spark</li>"
        "<li>A degree in Computer Science or equivalent experience</li>"
        "<li>Excellent communication skills</li></ul>"
        "<p><strong>Desirable</strong></p><ul><li>Kafka</li><li>Terraform</li><li>Docker</li></ul>"
        "<p>You must have the right to work in the UK; we cannot offer visa sponsorship.</p>"
    ),
}

PROFILE = {
    "skills": ["Python", "SQL", "Azure", "Docker", "Communication"],
    "years_of_experience": 4,
    "career_level": "experienced",
    "summary": "Data engineer building batch and streaming pipelines.",
    "experience": [{
        "title": "Data Engineer", "company": "Acme", "dates": "2021 - 2025",
        "bullets": ["Built Spark jobs in Python on Azure", "Wrote SQL models for finance reporting"],
    }],
    "education": [{"degree": "BSc Computer Science", "institution": "University of Leeds"}],
    "projects": [],
    "certifications": [],
}


def req(result, name):
    return next(r for r in result["requirements"] if r["name"] == name)


class TestListingParsing(unittest.TestCase):
    def test_headings_set_essential_and_desirable(self):
        lines, structured = classify_lines(UK_LISTING["description"])
        self.assertTrue(structured)
        kinds = {line: kind for line, kind in lines}
        self.assertEqual(kinds["Strong Python and SQL"], "essential")
        self.assertEqual(kinds["Kafka"], "desirable")
        self.assertEqual(kinds["You will build pipelines in Airflow for our analysts."], "context")

    def test_requirements_from_the_listing(self):
        reqs = extract_requirements(UK_LISTING)
        importance = {r["name"]: r["importance"] for r in reqs["skills"]}
        self.assertEqual(importance["Python"], "essential")
        self.assertEqual(importance["Apache Spark"], "essential")
        self.assertEqual(importance["Apache Kafka"], "desirable")
        # Only named in the duties, and the listing states its own requirements -> desirable.
        self.assertEqual(importance.get("Airflow"), "desirable")
        # Soft skills are listed but never scored.
        self.assertNotIn("Communication", importance)
        self.assertIn("Communication", reqs["general_skills"])
        self.assertEqual(reqs["experience"]["min_years"], 3)
        degree = reqs["qualifications"][0]
        self.assertEqual((degree["type"], degree["level"], degree["equivalent_accepted"]), ("degree", 3, True))
        self.assertEqual([e["check"] for e in reqs["eligibility"]], ["Right to work in the UK"])

    def test_each_skill_counted_once(self):
        listing = dict(UK_LISTING, id="dup", description=UK_LISTING["description"] + "<p>Desirable: Python</p>")
        names = [r["name"] for r in extract_requirements(listing)["skills"]]
        self.assertEqual(len(names), len(set(names)))
        # Named as essential and desirable: the employer's stronger statement wins.
        self.assertEqual(next(r for r in extract_requirements(listing)["skills"] if r["name"] == "Python")["importance"], "essential")


class TestEvidence(unittest.TestCase):
    def setUp(self):
        self.result = score_job(PROFILE, UK_LISTING)

    def test_direct_weak_transferable_missing(self):
        self.assertEqual(req(self.result, "Python")["evidence_type"], "direct")
        self.assertEqual(req(self.result, "Docker")["evidence_type"], "weak")  # Skills list only
        self.assertEqual(req(self.result, "AWS")["evidence_type"], "transferable")  # has Azure
        self.assertEqual(req(self.result, "AWS")["transferable_from"]["candidate_skill"], "Azure")
        self.assertEqual(req(self.result, "Apache Kafka")["evidence_type"], "missing")

    def test_exact_resume_evidence_is_quoted(self):
        spark = req(self.result, "Apache Spark")
        self.assertEqual(spark["resume_evidence"][0]["text"], "Built Spark jobs in Python on Azure")
        self.assertEqual(spark["resume_evidence"][0]["source"], "Data Engineer at Acme")

    def test_score_is_earned_over_possible(self):
        rows = self.result["requirements"]
        expected = 100 * sum(r["points"] for r in rows) / sum(r["weight"] for r in rows)
        self.assertAlmostEqual(self.result["raw_score"], round(expected, 1), places=1)
        self.assertIn("not part of this score", self.result["visa_sponsorship"])


class TestTopBandGates(unittest.TestCase):
    STRONG = dict(PROFILE, skills=["Python", "SQL", "AWS", "Spark", "Kafka", "Terraform", "Docker", "Airflow"],
                  experience=[{"title": "Data Engineer", "company": "Acme", "dates": "2021 - 2025", "bullets": [
                      "Built Spark and Airflow pipelines in Python on AWS",
                      "Streamed events with Kafka; provisioned with Terraform and Docker",
                      "Wrote SQL models"]}])

    def test_all_conditions_met_reaches_top_band(self):
        result = score_job(self.STRONG, UK_LISTING)
        self.assertGreaterEqual(result["score"], 85)
        self.assertTrue(result["top_band_eligible"])

    def test_fewer_than_four_matched_skills_is_capped(self):
        listing = {"id": "small", "title": "Python Developer",
                   "description": "<p>Essential</p><ul><li>Python</li><li>SQL</li><li>Git</li></ul>"}
        result = score_job(self.STRONG, listing)
        self.assertLess(result["score"], 85)
        self.assertFalse(result["checks"]["skills"]["passed"])

    def test_experience_is_a_listing_filter_not_a_score_gate(self):
        junior = dict(self.STRONG, years_of_experience=1, career_level="fresher")
        result = score_job(junior, UK_LISTING)
        # Shown as a failed check, but only skills (4+) and qualifications gate the top band...
        self.assertFalse(result["checks"]["experience"]["passed"])
        self.assertGreaterEqual(result["score"], 85)
        # ...because the job list never shows a 3+ years role to a fresher in the first place.
        self.assertEqual(RecommendationService().recommend_jobs(junior, [UK_LISTING], min_score=0), [])

    def test_experience_gate_can_be_switched_on(self):
        strict = _deep_merge(DEFAULT_MATCH_CONFIG, {"top_band": {"require_experience_match": True}})
        junior = dict(self.STRONG, years_of_experience=1, career_level="fresher")
        result = score_job(junior, UK_LISTING, config=strict)
        self.assertEqual(result["score"], 84)
        self.assertTrue(result["capped"])

    def test_missing_essential_qualification_is_capped(self):
        listing = dict(UK_LISTING, id="acca",
                       description=UK_LISTING["description"].replace("or equivalent experience", "and ACCA qualification"))
        result = score_job(self.STRONG, listing)
        self.assertIn("ACCA", result["checks"]["qualifications"]["essential_unmet"])
        self.assertLess(result["score"], 85)
        self.assertFalse(result["top_band_eligible"])

    def test_eligibility_does_not_change_the_score(self):
        without = dict(UK_LISTING, id="no-rtw",
                       description=UK_LISTING["description"].split("<p>You must have")[0])
        self.assertEqual(score_job(self.STRONG, UK_LISTING)["raw_score"], score_job(self.STRONG, without)["raw_score"])


class TestConfigurable(unittest.TestCase):
    def test_weights_come_from_config(self):
        flat = _deep_merge(DEFAULT_MATCH_CONFIG, {"importance": {"essential": 1.0, "desirable": 1.0}})
        default = score_job(PROFILE, UK_LISTING)
        equal = score_job(PROFILE, UK_LISTING, config=flat)
        self.assertNotEqual(default["raw_score"], equal["raw_score"])
        self.assertEqual(equal["weights"]["importance"], {"essential": 1.0, "desirable": 1.0})
        self.assertEqual(DEFAULT_MATCH_CONFIG["importance"]["essential"], 2.0)  # defaults untouched


class TestRecommendationList(unittest.TestCase):
    def test_threshold_and_breakdown(self):
        service = RecommendationService()
        recs = service.recommend_jobs(TestTopBandGates.STRONG, [UK_LISTING], min_score=85)
        self.assertEqual(len(recs), 1)
        self.assertIn("match_breakdown", recs[0])
        self.assertEqual(service.recommend_jobs(PROFILE, [UK_LISTING], min_score=85), [])

    def test_fresher_never_sees_experienced_roles(self):
        fresher = copy.deepcopy(TestTopBandGates.STRONG)
        fresher.update(years_of_experience=0, career_level="fresher")
        senior = dict(UK_LISTING, id="senior", title="Senior Data Engineer")
        self.assertEqual(RecommendationService().recommend_jobs(fresher, [senior], min_score=0), [])


if __name__ == "__main__":
    unittest.main()

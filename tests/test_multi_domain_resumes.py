import unittest

from backend.recommendation_service import RecommendationService
from backend.resume_service import ResumeService

RESUMES = {
    "Teacher": """ANITA RAO
anita@example.com
SUMMARY
Primary school teacher with 4 years of experience in classroom teaching.
SKILLS
Lesson Planning, Classroom Management, Differentiated Instruction, Student Assessment, Google Classroom
EXPERIENCE
Primary Teacher | Green Valley School 2020 - 2024
• Planned lessons and ran parent communication.
""",
    "Accountant": """RAVI KUMAR
ravi@example.com
SKILLS
• Accounts Payable
• Bank Reconciliation
• Month-End Close
• QuickBooks
• Tally
EXPERIENCE
Accountant | Patel & Co 2021 - 2024
• Prepared general ledger entries, GST returns and financial statements.
""",
    "Hardware Engineer": """MEERA S
meera@example.com
SKILLS
Embedded C, PCB Design, Altium Designer, Verilog, Oscilloscope, STM32
EXPERIENCE
Hardware Engineer | Volt Labs 2022 - 2025
• Designed circuit boards and debugged firmware bring-up.
""",
    "Nurse": """JOHN D
SKILLS
Patient Care, Medication Administration, Triage, Electronic Health Records, Infection Control
EXPERIENCE
Registered Nurse | City Hospital 2020 - 2024
""",
    "Financial Analyst": """SARA K
SKILLS
Financial Modeling, FP&A, Budgeting, Forecasting, Excel, Variance Analysis
EXPERIENCE
Financial Analyst | Acme 2021 - 2024
""",
}

JOBS = [
    {"id": "t", "title": "Primary School Teacher", "description": "Lesson planning, classroom management, student assessment and differentiated instruction.", "extracted_skills": []},
    {"id": "a", "title": "Accountant", "description": "Accounts payable, bank reconciliation, month-end close in QuickBooks.", "extracted_skills": []},
    {"id": "h", "title": "Hardware Engineer", "description": "PCB design in Altium, Embedded C firmware, Verilog, lab debugging with oscilloscope.", "extracted_skills": []},
    {"id": "n", "title": "Registered Nurse", "description": "Patient care, medication administration, triage, electronic health records.", "extracted_skills": []},
    {"id": "f", "title": "Financial Analyst", "description": "Financial modeling, FP&A, budgeting, forecasting, variance analysis.", "extracted_skills": []},
    {"id": "s", "title": "Software Engineer", "description": "Python, AWS, Docker, Kubernetes, React.", "extracted_skills": []},
]
EXPECTED = {"Teacher": "t", "Accountant": "a", "Hardware Engineer": "h", "Nurse": "n", "Financial Analyst": "f"}


class MultiDomainTests(unittest.TestCase):
    def setUp(self):
        self.parser = ResumeService()
        self.rec = RecommendationService()

    def test_every_profession_is_parsed_and_matched(self):
        for name, text in RESUMES.items():
            with self.subTest(profession=name):
                resume = self.parser.analyze_text(text, f"{name}.pdf")
                self.assertGreaterEqual(len(resume["skills"]), 4, resume["skills"])
                self.assertTrue(resume["target_roles"], "no target role detected")
                jobs = [dict(j) for j in JOBS]
                ids = [r["id"] for r in self.rec.recommend_jobs(resume, jobs, min_score=60)]
                self.assertIn(EXPECTED[name], ids)
                self.assertNotIn("s", ids, "engineering job must not match a non-engineering résumé")

    def test_lead_generation_is_not_lead_seniority(self):
        _, seniority = self.parser._detect_experience("Skilled in Lead Generation and prospecting")
        self.assertNotEqual(seniority, "Lead")

    def test_unknown_profession_falls_back_to_listed_skills_and_titles(self):
        text = "SKILLS\nBeekeeping, Honey Extraction, Hive Management, Pollination\nEXPERIENCE\nApiarist | Bee Farm 2021 - 2024\n"
        resume = self.parser.analyze_text(text, "bee.pdf")
        self.assertIn("Beekeeping", resume["skills"])
        self.assertIn("Apiarist", resume["target_roles"])


if __name__ == "__main__":
    unittest.main()

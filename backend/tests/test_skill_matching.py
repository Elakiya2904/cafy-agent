import unittest

from backend.skill_catalog import DOMAINS, SYNONYMS
from backend.skill_matching import text_has_skill


class SkillMatchingTests(unittest.TestCase):
    def test_word_forms_order_and_synonyms_match(self):
        cases = [
            ("Patient Care", "You will provide care to patients on the ward"),
            ("Lesson Planning", "plan and deliver engaging lesson plans"),
            ("Accounts Payable", "owns the purchase ledger and supplier payments"),
            ("Customer Support", "handle customer queries"),
            ("Financial Modeling", "building financial models"),
            ("Teaching", "experienced teachers wanted"),
        ]
        for skill, text in cases:
            with self.subTest(skill=skill):
                self.assertTrue(text_has_skill(skill, text))

    def test_no_false_substring_matches(self):
        self.assertFalse(text_has_skill("Java", "javascript developer"))
        self.assertFalse(text_has_skill("Sales", "salesforce administrator"))
        self.assertFalse(text_has_skill("Go", "we are going to grow"))

    def test_every_domain_has_enough_skills_and_roles(self):
        for name, d in DOMAINS.items():
            if name == "Business & Productivity Tools":
                continue
            with self.subTest(domain=name):
                self.assertGreaterEqual(len(d["skills"]), 20)
                self.assertGreaterEqual(len(d["roles"]), 1)
                for role, phrases in d["roles"].items():
                    self.assertTrue(phrases, role)

    def test_synonyms_point_at_real_catalog_skills(self):
        known = {s.lower() for d in DOMAINS.values() for s in d["skills"]}
        orphans = [k for k in SYNONYMS if k not in known]
        self.assertEqual(orphans, [], "synonym keys must be catalog skills (add the skill or fix the key)")


if __name__ == "__main__":
    unittest.main()

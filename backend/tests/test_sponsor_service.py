import csv
import tempfile
import unittest
from pathlib import Path

from backend.sponsor_service import VisaSponsorRegistry
from backend.sponsor_service import LOCATION_UNVERIFIED, NON_UK, UK_CONFIRMED


class TestVisaSponsorRegistry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.temp_dir.name) / "register.csv"
        with self.csv_path.open("w", encoding="utf-8", newline="") as register:
            writer = csv.DictWriter(
                register,
                fieldnames=["Organisation Name", "Town/City", "County", "Route"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "Organisation Name": "  AARUVIKA Limited ",
                    "Town/City": "Edinburgh",
                    "Route": "Skilled Worker",
                }
            )
            writer.writerow(
                {
                    "Organisation Name": "Figma UK Limited",
                    "Town/City": "London",
                    "County": "Greater London",
                    "Route": "Skilled Worker",
                }
            )
            writer.writerow(
                {
                    "Organisation Name": "GitHub Software UK Ltd",
                    "Town/City": "London",
                    "Route": "Skilled Worker",
                }
            )
            writer.writerow(
                {
                    "Organisation Name": "CFC Underwriting Limited",
                    "Town/City": "London",
                    "Route": "Skilled Worker",
                }
            )
            for legal_name in ("Scale AI Limited", "Robinhood U.K Ltd.", "Snowflake Computing U.K. Limited", "Notion Capital Managers LLP"):
                writer.writerow({"Organisation Name": legal_name, "Town/City": "London", "Route": "Skilled Worker"})
            writer.writerow(
                {
                    "Organisation Name": "Stripe Payments UK Ltd",
                    "Town/City": "London",
                    "Route": "Skilled Worker",
                }
            )
        self.registry = VisaSponsorRegistry(self.csv_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # ------------------------------------------------------------------
    # Company name matching
    # ------------------------------------------------------------------

    def test_company_match_ignores_case_whitespace_and_punctuation(self):
        self.assertTrue(self.registry.is_sponsored("Aaruvika, Limited"))

    def test_non_matching_company_is_not_sponsored(self):
        self.assertFalse(self.registry.is_sponsored("Aaruvika Group"))

    def test_company_match_ignores_uk_and_legal_entity_suffixes(self):
        self.assertTrue(self.registry.is_sponsored("Figma"))

    def test_company_match_supports_known_brand_and_legal_name_variant(self):
        self.assertTrue(self.registry.is_sponsored("GitHub"))

    def test_company_match_supports_known_employer_alias(self):
        self.assertTrue(self.registry.is_sponsored("CFC"))

    def test_company_match_supports_stripe_legal_entity(self):
        self.assertTrue(self.registry.is_sponsored("Stripe"))

    def test_company_match_supports_brand_to_legal_entity_aliases(self):
        for brand in ("Scaleai", "Robinhood", "Snowflake"):
            self.assertTrue(self.registry.is_sponsored(brand), brand)

    def test_alias_does_not_match_unrelated_company_with_similar_name(self):
        self.assertFalse(self.registry.is_sponsored("Notion"))

    def test_company_match_does_not_match_unrelated_name_prefix(self):
        self.assertFalse(self.registry.is_sponsored("Figma Consulting"))

    def test_ordinary_words_are_not_read_as_us_states(self):
        for location in ("London or Dublin", "Remote in London", "Dublin or London", "Belfast and Leeds"):
            self.assertNotEqual(self.registry.job_location_status(location), "NON_UK", location)

    def test_either_or_locations_with_a_uk_city_are_uk_confirmed(self):
        for location in ("London or Dublin", "Dublin, London OR Berlin"):
            self.assertEqual(self.registry.job_location_status(location), "UK_CONFIRMED", location)

    def test_us_state_codes_after_a_comma_are_still_non_uk(self):
        for location in ("San Francisco, CA", "Seattle, WA OR New York, NY", "Toronto, ON"):
            self.assertEqual(self.registry.job_location_status(location), "NON_UK", location)

    # ------------------------------------------------------------------
    # Location status
    # ------------------------------------------------------------------

    def test_job_country_matches_explicit_uk_location(self):
        self.assertTrue(
            self.registry.is_job_in_sponsor_country("London, United Kingdom")
        )

    def test_job_country_matches_register_town_when_country_is_omitted(self):
        self.assertTrue(self.registry.is_job_in_sponsor_country("London"))

    def test_uk_city_and_uk_wide_do_not_require_employer_registered_city(self):
        self.assertEqual(self.registry.job_location_status("Bristol"), UK_CONFIRMED)
        self.assertEqual(self.registry.job_location_status("UK-wide"), UK_CONFIRMED)

    def test_job_country_rejects_non_uk_and_unknown_locations(self):
        self.assertFalse(
            self.registry.is_job_in_sponsor_country("London, Canada")
        )
        self.assertFalse(self.registry.is_job_in_sponsor_country("London, ON"))
        self.assertFalse(self.registry.is_job_in_sponsor_country("Remote"))

    # ------------------------------------------------------------------
    # Overseas jobs — registered employer must NOT receive UK badge
    # ------------------------------------------------------------------

    def test_overseas_job_for_registered_employer_is_not_visa_sponsored(self):
        """Core rule: overseas location blocks the badge even for a registered employer."""
        job = self.registry.annotate_jobs([{
            "company": "Figma UK Limited",
            "location": "London, Canada",
        }])[0]

        self.assertEqual(job["visa_sponsor_location_status"], NON_UK)
        self.assertTrue(job["visa_sponsor_registered"])
        self.assertFalse(job["visa_sponsored"])
        self.assertIsNone(job["visa_sponsor_country"])
        self.assertIsNone(job["visa_sponsor_disclaimer"])

    def test_us_location_for_registered_employer_is_not_visa_sponsored(self):
        job = self.registry.annotate_jobs([{
            "company": "Figma",
            "location": "San Francisco, CA, United States",
        }])[0]

        self.assertEqual(job["visa_sponsor_location_status"], NON_UK)
        self.assertTrue(job["visa_sponsor_registered"])
        self.assertFalse(job["visa_sponsored"])

    def test_multiple_overseas_countries_all_rejected(self):
        overseas = [
            "New York, United States",
            "Toronto, Canada",
            "Berlin, Germany",
            "Sydney, Australia",
            "Singapore",
            "Dublin, Ireland",
        ]
        for location in overseas:
            with self.subTest(location=location):
                job = self.registry.annotate_jobs([{
                    "company": "Figma UK Limited",
                    "location": location,
                }])[0]
                self.assertFalse(
                    job["visa_sponsored"],
                    f"Expected no badge for overseas location: {location}",
                )

    # ------------------------------------------------------------------
    # Remote / ambiguous locations
    # ------------------------------------------------------------------

    def test_remote_requires_explicit_uk_work_location(self):
        confirmed, city_confirmed, description_confirmed, unknown = self.registry.annotate_jobs([
            {
                "company": "Figma UK Limited",
                "location": "Remote",
                "is_remote": True,
                "description": "This role can be performed remotely from within the United Kingdom.",
            },
            {
                "company": "Figma UK Limited",
                "location": "Remote, Bristol",
                "is_remote": True,
            },
            {
                "company": "Figma UK Limited",
                "location": "",
                "is_remote": True,
                "description": "This remote role can be performed from Bristol, UK.",
            },
            {
                "company": "Figma UK Limited",
                "location": "Remote, EMEA",
                "is_remote": True,
                "description": "Remote role across EMEA.",
            },
        ])

        self.assertEqual(confirmed["visa_sponsor_location_status"], UK_CONFIRMED)
        self.assertTrue(confirmed["visa_sponsored"])
        self.assertEqual(city_confirmed["visa_sponsor_location_status"], UK_CONFIRMED)
        self.assertTrue(city_confirmed["visa_sponsored"])
        self.assertEqual(description_confirmed["visa_sponsor_location_status"], UK_CONFIRMED)
        self.assertTrue(description_confirmed["visa_sponsored"])
        self.assertEqual(unknown["visa_sponsor_location_status"], LOCATION_UNVERIFIED)
        self.assertFalse(unknown["visa_sponsored"])

    def test_missing_and_ambiguous_locations_are_unverified(self):
        annotated = self.registry.annotate_jobs([
            {"company": "Figma UK Limited", "location": ""},
            {"company": "Figma UK Limited", "location": "Remote"},
        ])

        self.assertEqual(
            [job["visa_sponsor_location_status"] for job in annotated],
            [LOCATION_UNVERIFIED, LOCATION_UNVERIFIED],
        )
        self.assertFalse(any(job["visa_sponsored"] for job in annotated))

    def test_remote_emea_without_uk_mention_is_unverified_not_badged(self):
        """EMEA remote without any UK signal must not receive the badge."""
        job = self.registry.annotate_jobs([{
            "company": "Figma UK Limited",
            "location": "Remote, EMEA",
            "is_remote": True,
            "description": "Work from anywhere in Europe, Middle East, or Africa.",
        }])[0]

        self.assertEqual(job["visa_sponsor_location_status"], LOCATION_UNVERIFIED)
        self.assertFalse(job["visa_sponsored"])

    # ------------------------------------------------------------------
    # UK jobs — correct badge behaviour
    # ------------------------------------------------------------------

    def test_job_annotation_requires_employer_and_country_match(self):
        jobs = [{
            "company": "Aaruvika Limited",
            "title": "Engineer",
            "location": "Edinburgh, Scotland",
        }]

        annotated = self.registry.annotate_jobs(jobs)

        self.assertEqual(annotated[0]["title"], "Engineer")
        self.assertTrue(annotated[0]["visa_sponsor_registered"])
        self.assertIn("AARUVIKA Limited", annotated[0]["visa_sponsor_registered_names"])
        self.assertTrue(annotated[0]["visa_sponsored"])
        self.assertEqual(annotated[0]["visa_sponsor_country"], "United Kingdom")
        self.assertTrue(annotated[0]["visa_sponsored_country_match"])
        self.assertNotIn("visa_sponsored", jobs[0])

    def test_employer_match_without_uk_job_location_is_not_visa_sponsored(self):
        annotated = self.registry.annotate_jobs([{
            "company": "Figma",
            "location": "San Francisco, CA, United States",
        }])

        self.assertTrue(annotated[0]["visa_sponsor_registered"])
        self.assertIn("Figma UK Limited", annotated[0]["visa_sponsor_registered_names"])
        self.assertFalse(annotated[0]["visa_sponsored"])
        self.assertFalse(annotated[0]["visa_sponsored_country_match"])

    def test_country_match_requires_sponsor_employer(self):
        annotated = self.registry.annotate_jobs([{
            "company": "Figma Consulting",
            "location": "London, United Kingdom",
        }])

        self.assertFalse(annotated[0]["visa_sponsored"])
        self.assertFalse(annotated[0]["visa_sponsored_country_match"])

    def test_only_registered_uk_jobs_are_marked_sponsored(self):
        annotated = self.registry.annotate_jobs([
            {"company": "Figma", "location": "London, United Kingdom"},
            {"company": "Figma UK Limited", "location": "Bristol"},
            {"company": "Figma Consulting", "location": "London, United Kingdom"},
            {"company": "Figma", "location": "San Francisco, CA, United States"},
            {"company": "Figma", "location": "Remote"},
        ])

        self.assertEqual(
            [job["visa_sponsored"] for job in annotated],
            [True, True, False, False, False],
        )
        self.assertEqual(annotated[1]["visa_sponsor_location_status"], UK_CONFIRMED)
        self.assertEqual(annotated[4]["visa_sponsor_location_status"], LOCATION_UNVERIFIED)

    # ------------------------------------------------------------------
    # Disclaimer field
    # ------------------------------------------------------------------

    def test_disclaimer_present_only_on_badged_jobs(self):
        """visa_sponsor_disclaimer must be set for UK-badged jobs and None otherwise."""
        annotated = self.registry.annotate_jobs([
            {"company": "Figma UK Limited", "location": "London, United Kingdom"},
            {"company": "Figma UK Limited", "location": "San Francisco, CA, United States"},
            {"company": "Figma UK Limited", "location": "Remote"},
            {"company": "Figma Consulting", "location": "London, United Kingdom"},
        ])

        uk_job, overseas_job, remote_job, unregistered_job = annotated

        self.assertIsNotNone(uk_job["visa_sponsor_disclaimer"])
        self.assertIn("does not guarantee", uk_job["visa_sponsor_disclaimer"])
        self.assertIsNone(overseas_job["visa_sponsor_disclaimer"])
        self.assertIsNone(remote_job["visa_sponsor_disclaimer"])
        self.assertIsNone(unregistered_job["visa_sponsor_disclaimer"])

    def test_disclaimer_does_not_claim_sponsorship_guaranteed(self):
        """The disclaimer text must explicitly state sponsorship is not guaranteed."""
        job = self.registry.annotate_jobs([{
            "company": "Figma UK Limited",
            "location": "London, United Kingdom",
        }])[0]

        disclaimer = job["visa_sponsor_disclaimer"]
        self.assertIsNotNone(disclaimer)
        self.assertIn("does not guarantee", disclaimer.lower())
        self.assertIn("specific vacancy", disclaimer.lower())


if __name__ == "__main__":
    unittest.main()


class TestIrelandPermitRegistry(unittest.TestCase):
    def setUp(self):
        import openpyxl
        from backend.sponsor_service import VisaSponsorRegistry
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        uk = root / "uk"
        uk.mkdir()
        (uk / "SP_-_Worker_and_Temporary_Worker_Web_Register_2026-01-01.csv").write_text(
            "Organisation Name,Town/City,County,Route\nFigma UK Limited,London,,Skilled Worker\n", encoding="utf-8")
        ie = root / "ie"
        ie.mkdir()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Employer Name", "Permits Issued Jan", "Permits Issued Feb"])
        ws.append(["Anthropic Ireland Limited", 2, 4])
        ws.append(["Stripe Payments Europe Limited", 1, None])
        ws.append(["Asana foods limited", None, None])  # listed but no permits issued
        ws.append(["Grand Total", 7, 4])
        wb.save(ie / "employment-permits-issued-to-companies-2026.xlsx")
        self.registry = VisaSponsorRegistry.from_directory(uk, ie)

    def annotate(self, company, location):
        return self.registry.annotate_jobs([{"company": company, "location": location}])[0]

    def test_irish_job_at_permit_issuing_employer_is_badged_for_ireland(self):
        job = self.annotate("Anthropic", "Dublin, Ireland")
        self.assertTrue(job["visa_sponsored"])
        self.assertEqual(job["visa_sponsor_country"], "Ireland")
        self.assertEqual(job["ireland_permits_issued"], {"2026": 6})
        self.assertIn("6 Irish employment permits", job["visa_sponsor_disclaimer"])

    def test_brand_alias_matches_irish_legal_entity(self):
        self.assertTrue(self.annotate("Stripe", "Dublin")["visa_sponsored"])

    def test_employer_with_zero_permits_or_not_listed_is_not_badged(self):
        self.assertFalse(self.annotate("Asana", "Dublin")["visa_sponsored"])
        self.assertFalse(self.annotate("Unknown Co", "Dublin")["visa_sponsored"])

    def test_irish_permits_do_not_badge_a_non_irish_job(self):
        self.assertFalse(self.annotate("Anthropic", "San Francisco, CA")["visa_sponsored"])

    def test_uk_sponsor_still_wins_for_uk_job_and_northern_ireland_is_uk(self):
        job = self.annotate("Figma", "Belfast, Northern Ireland")
        self.assertEqual(job["visa_sponsor_country"], "United Kingdom")
        self.assertFalse(job["job_in_ireland"])

    def test_either_or_uk_and_ireland_location_is_badged_by_whichever_list_applies(self):
        self.assertEqual(self.annotate("Figma", "London or Dublin")["visa_sponsor_country"], "United Kingdom")
        self.assertEqual(self.annotate("Anthropic", "London or Dublin")["visa_sponsor_country"], "Ireland")

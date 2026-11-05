"""Sponsor-register discovery: which board names are tried, and when a found board is trusted."""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import discover_employers as d  # noqa: E402


class TestSlugCandidates(unittest.TestCase):
    def test_brand_guess_drops_descriptor_words(self):
        self.assertEqual(d.slug_candidates("Monzo Bank Limited"),
                         {"monzobank": "exact", "monzo-bank": "exact", "monzo": "brand"})
        self.assertEqual(d.slug_candidates("Stripe Payments UK Ltd")["stripe"], "brand")
        self.assertEqual(d.slug_candidates("Palantir Technologies UK, Ltd.")["palantir"], "brand")
        self.assertEqual(d.slug_candidates("Deliveroo Hop Limited")["deliveroo"], "brand")

    def test_trading_name_and_legal_leftovers(self):
        self.assertEqual(d.slug_candidates("Toasttab UK Limited T/A Toast"), {"toasttab": "exact", "toast": "exact"})
        self.assertEqual(d.slug_candidates("Bloomberg L.P."), {"bloomberg": "exact"})
        self.assertEqual(d.slug_candidates("GSK Services Unlimited"), {"gsk": "exact"})
        self.assertEqual(d.slug_candidates("Datadog Ireland Limited"), {"datadog": "exact"})

    def test_names_without_descriptors_get_no_risky_guess(self):
        self.assertEqual(set(d.slug_candidates("Bird & Bird LLP").values()), {"exact"})
        self.assertEqual(d.slug_candidates("Figma UK Limited"), {"figma": "exact"})
        self.assertEqual(d.slug_candidates("Ltd"), {})


class TestBoardNameMatch(unittest.TestCase):
    def test_matches(self):
        for board, slug in (("Monzo", "monzo"), ("Palantir Technologies", "palantir"), ("Monzo Bank", "monzo")):
            self.assertTrue(d.board_name_matches(board, slug), board)

    def test_rejects(self):
        for board, slug in (("Wise Owl Media", "wise"), ("Acme Corp", "monzo"), ("", "x"), (None, "x")):
            self.assertFalse(d.board_name_matches(board, slug), board)


class TestAccept(unittest.TestCase):
    def setUp(self):
        self.runner = d.Runner(SimpleNamespace(out=os.path.join(os.environ.get("TMPDIR", "/tmp"), "discover-test")))

    def accept(self, platform, slug, entries, board=None, locs=None):
        async def fetch(url):
            return {"name": board} if board is not None else None
        locs = locs if locs is not None else d.Locations(["London, UK"])
        return asyncio.run(self.runner.accept(platform, fetch, slug, entries, locs))

    def test_exact_name_is_trusted(self):
        self.assertEqual(self.accept("lever", "monzobank", [("Monzo Bank Limited", "exact")]), ("Monzo Bank Limited", "exact"))

    def test_brand_guess_needs_the_board_to_say_who_it_is(self):
        self.assertEqual(self.accept("greenhouse", "monzo", [("Monzo Bank Limited", "brand")], board="Monzo"),
                         ("Monzo Bank Limited", "brand-verified"))
        self.assertEqual(self.accept("greenhouse", "monzo", [("Monzo Bank Limited", "brand")], board="Someone Else"),
                         (None, None))

    def test_smartrecruiters_uses_the_company_name_in_its_postings(self):
        locs = d.Locations(["Reading, United Kingdom"])
        locs.board_name = "Bosch Group"
        self.assertEqual(self.accept("smartrecruiters", "bosch", [("Bosch Technologies Ltd", "brand")], locs=locs),
                         ("Bosch Technologies Ltd", "brand-verified"))  # "Bosch Group" reduces to "bosch"
        locs.board_name = "Boschetti Foods"
        self.assertEqual(self.accept("smartrecruiters", "bosch", [("Bosch Technologies Ltd", "brand")], locs=locs),
                         (None, None))

    def test_unverifiable_platforms_accept_only_unambiguous_distinctive_brands(self):
        self.assertEqual(self.accept("lever", "palantir", [("Palantir Technologies UK, Ltd.", "brand")]),
                         ("Palantir Technologies UK, Ltd.", "brand-unique"))
        self.assertEqual(self.accept("lever", "acme", [("Acme Bank Ltd", "brand")]), (None, None))      # too short
        self.assertEqual(self.accept("ashby", "zenith", [("Zenith Bank Ltd", "brand"), ("Zenith Labs Ltd", "brand")]),
                         (None, None))                                                              # two employers


class TestMerge(unittest.TestCase):
    def test_brand_guesses_need_explicit_review_and_rejects_are_skipped(self):
        import json, shutil, tempfile
        from pathlib import Path
        from unittest import mock
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "hits.jsonl").write_text("\n".join(json.dumps(h) for h in [
            {"platform": "greenhouse", "slug": "acmebank", "org": "Acme Bank Ltd", "total": 5, "uk_ie": 3, "kind": "exact"},
            {"platform": "greenhouse", "slug": "monzo", "org": "Monzo Bank Ltd", "total": 9, "uk_ie": 4, "kind": "brand-verified"},
            {"platform": "ashby", "slug": "philo", "org": "Philo Consulting Services Ltd", "total": 5, "uk_ie": 5, "kind": "brand-unique"},
            {"platform": "lever", "slug": "nouk", "org": "No UK Ltd", "total": 5, "uk_ie": 0, "kind": "exact"},
        ]))
        sources = tmp / "backend" / "scrapers" / "sources.yaml"
        sources.parent.mkdir(parents=True)

        def merged(**kw):
            sources.write_text("platforms:\n  greenhouse:\n    companies: []\n")
            with mock.patch.object(d, "ROOT", tmp):
                d.merge_into_sources(tmp, **kw)
            import yaml
            plats = yaml.safe_load(sources.read_text())["platforms"]
            return sorted(f"{p}:{c['token']}" for p, cfg in plats.items() for c in cfg.get("companies", []))

        self.assertEqual(merged(), ["greenhouse:acmebank"])
        self.assertEqual(merged(include_brand=True, exclude=["ashby:philo"]), ["greenhouse:acmebank", "greenhouse:monzo"])


if __name__ == "__main__":
    unittest.main()

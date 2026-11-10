import unittest
from datetime import date, datetime, timezone

from energy_lit.model import doi, journal_match, load_journals, week
from energy_lit.sources import crossref_record


class ContractTests(unittest.TestCase):
    def test_doi(self):
        self.assertEqual(doi(" https://DOI.org/10.1038/A%2FB "), "10.1038/a/b")
        self.assertIsNone(doi("javascript:alert(1)"))
        self.assertIsNone(doi("https://evil.example/10.1038/a"))

    def test_strict_journal_and_conflicts(self):
        journals = load_journals()
        self.assertEqual(len(journals), 27)
        self.assertEqual(journal_match(journals, {"1476-4687"}, set())[0], "Nature")
        self.assertIsNone(journal_match(journals, {"1476-4687", "2058-7546"}, set())[0])
        self.assertIsNone(journal_match(journals, {"1932-6203"}, set())[0])
        name, issue = journal_match(journals, {"1476-4687", "1932-6203"}, {"https://openalex.org/S137773608"})
        self.assertIsNone(name)
        self.assertEqual(issue, "Conflicting journal identifiers")

    def test_bibliographic_date_is_not_deposit_date(self):
        record = crossref_record({
            "DOI": "10.1234/sample", "title": ["Test"], "ISSN": ["1476-4687"],
            "published-online": {"date-parts": [[2026, 1, 10]]},
            "published-print": {"date-parts": [[2026, 2]]},
            "indexed": {"date-time": "2026-03-03T09:00:00Z"},
        })
        self.assertEqual(record["online_date"], "2026-01-10")
        self.assertEqual(record["print_date"], "2026-02")
        self.assertEqual(record["source_updated"], "2026-03-03T09:00:00Z")

    def test_week_boundary(self):
        before = datetime(2026, 11, 9, 0, 59, tzinfo=timezone.utc)
        after = datetime(2026, 11, 9, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(week(before), date(2026, 11, 2))
        self.assertEqual(week(after), date(2026, 11, 9))

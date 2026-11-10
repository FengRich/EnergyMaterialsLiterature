import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from energy_lit.model import abstract_digest, empty_state, load_journals
from energy_lit.rules import classify, load_rules
from energy_lit.sync import apply_batch, make_reports, read_state, store_state

NOW = datetime(2026, 11, 10, 1, tzinfo=timezone.utc)
DOI = "10.1234/sample"
ABSTRACT = "We performed density functional theory calculations on the lithium battery interface."


def observation(source="Crossref", issns=None, abstract=ABSTRACT):
    return dict(doi=DOI, source=source, source_id=DOI, title="Lithium battery electrode interface",
                authors=["A. Researcher"], journal_reported="Nature", issns=issns or ["1476-4687"],
                journal_id=None, publication_date="2026-10-31", online_date=None, print_date=None,
                source_updated=None, type="journal-article", abstract=abstract,
                publisher_url=None, retracted=False)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.journals = load_journals()
        self.rules = load_rules()

    def batch(self, state, rows, *, reviews=None, licenses=None, historical=False):
        apply_batch(state, rows, self.journals, self.rules, reviews or {}, licenses or {}, NOW,
                    historical=historical)

    def test_missing_and_weak_evidence(self):
        self.assertEqual(classify("Lithium battery interface", "", self.rules)[2], "Pending")
        self.assertEqual(classify("Lithium battery interface",
            "DFT may be useful in future work.", self.rules)[2], "Pending")

    def test_abstract_default_hidden_and_override_persists(self):
        state = empty_state()
        self.batch(state, [observation()])
        row = state["papers"][DOI]
        self.assertEqual(row["status"], "Accepted")
        self.assertIsNone(row["abstract"])
        self.assertEqual(row["abstract_source"], "Crossref")
        review = {DOI: {"decision": "Rejected", "reason": "Experimental only",
                        "evidence": "https://doi.org/10.1234/sample", "date": "2026-11-10"}}
        self.batch(state, [observation(), observation("OpenAlex")], reviews=review)
        row = state["papers"][DOI]
        self.assertEqual(row["status"], "Rejected")
        self.assertEqual(len(state["papers"]), 1)
        self.assertEqual(set(row["sources"]), {"OpenAlex", "Crossref"})
        self.batch(state, [], reviews=review)
        self.assertEqual(state["papers"][DOI]["status"], "Rejected")

    def test_license_must_bind_to_source_and_exact_text(self):
        state = empty_state()
        license = {DOI: {"source": "Crossref", "sha256": abstract_digest(ABSTRACT), "license": "CC BY 4.0",
                         "evidence": "https://doi.org/10.1234/sample", "date": "2026-11-10"}}
        self.batch(state, [observation()], licenses=license)
        self.assertEqual(state["papers"][DOI]["abstract"], ABSTRACT)
        self.batch(state, [observation(abstract=ABSTRACT + " Changed.")], licenses=license)
        self.assertIsNone(state["papers"][DOI]["abstract"])

    def test_bootstrap_and_idempotent_reports(self):
        state = empty_state()
        self.batch(state, [observation()], historical=True)
        self.batch(state, [observation()])
        make_reports(state, self.rules, date(2026, 11, 9))
        self.assertEqual(state["reports"]["2026-11-09"]["papers"], [])
        first_seen = state["papers"][DOI]["first_seen"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            store_state(path, state, empty_state(), self.journals)
            recovered = read_state(path)
            self.assertEqual(recovered["papers"][DOI]["first_seen"], first_seen)
            self.assertEqual(recovered, state)

    def test_conflict_blocks_manual_acceptance(self):
        state = empty_state()
        self.batch(state, [observation(), observation("OpenAlex", ["2058-7546"])],
                   reviews={DOI: {"decision": "Accepted", "reason": "Check",
                                  "evidence": "https://doi.org/10.1234/sample", "date": "2026-11-10"}})
        self.assertEqual(state["papers"][DOI]["status"], "Pending")

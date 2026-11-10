import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from tests import test_pipeline as fixtures
from energy_lit.model import abstract_digest, empty_state, week
from energy_lit.sources import SourceError, crossref_record
from energy_lit.sync import apply_batch, exclusive_sync, make_reports, read_state, store_state, synchronize


class ProtectionTests(unittest.TestCase):
    def setUp(self):
        self.setup = fixtures.PipelineTests()
        self.setup.setUp()

    def test_reject_cover_metadata(self):
        row = fixtures.observation()
        row["title"] = "DFT simulation for lithium battery interfaces (Adv. Energy Mater. 39/2026)"
        state = empty_state()
        self.setup.batch(state, [row])
        self.assertEqual(state["papers"][fixtures.DOI]["status"], "Rejected")

    def test_known_openalex_work_does_not_duplicate_when_doi_disappears(self):
        row = fixtures.observation("OpenAlex")
        row["source_id"] = "https://openalex.org/W12345"
        state = empty_state()
        self.setup.batch(state, [row])
        self.setup.batch(state, [{**row, "doi": None}])
        self.assertEqual(list(state["papers"]), [fixtures.DOI])

    def test_duplicate_json_keys_are_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            path.write_text('{"papers":{"10.1234/sample":{},"10.1234/sample":{}}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                read_state(path)

    def test_store_rechecks_accepted_journal_identifiers(self):
        state = empty_state()
        self.setup.batch(state, [fixtures.observation()])
        state["papers"][fixtures.DOI]["issns"] = ["1932-6203"]
        make_reports(state, self.setup.rules)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "Journal identity"):
                store_state(Path(temp) / "state.json", state, empty_state(), self.setup.journals)

    def test_crossref_retraction_marks_target(self):
        state = empty_state()
        self.setup.batch(state, [fixtures.observation()])
        notice = crossref_record({
            "DOI": "10.1234/notice", "title": ["Retraction notice"],
            "update-to": [{"type": "retraction", "DOI": fixtures.DOI}],
        })
        self.setup.batch(state, [notice])
        self.assertEqual(state["papers"][fixtures.DOI]["status"], "Rejected")
        self.assertEqual(state["papers"][fixtures.DOI]["reason"], "Source reports a retraction")

    @patch("energy_lit.sync.lookup_record", create=True)
    def test_approved_older_abstract_can_be_retrieved(self, lookup):
        from energy_lit.sync import refresh_approved_abstracts

        state = empty_state()
        self.setup.batch(state, [fixtures.observation()], historical=True)
        license = {fixtures.DOI: {"source": "Crossref", "sha256": abstract_digest(fixtures.ABSTRACT),
                                  "license": "CC BY 4.0", "evidence": "https://doi.org/10.1234/sample",
                                  "date": "2026-11-10"}}
        lookup.return_value = fixtures.observation()
        refresh_approved_abstracts(state, self.setup.journals, self.setup.rules, {}, license, fixtures.NOW)
        self.assertEqual(state["papers"][fixtures.DOI]["abstract"], fixtures.ABSTRACT)

    @patch("energy_lit.sync.discover")
    def test_same_week_manual_sync_keeps_one_edition(self, discover):
        status = {"Crossref": {"state": "ok", "count": 1},
                  "OpenAlex": {"state": "ok", "count": 1}}
        discover.side_effect = lambda *args, **kwargs: (
            [fixtures.observation(), fixtures.observation("OpenAlex")],
            {key: dict(value) for key, value in status.items()},
        )
        state = empty_state()
        self.setup.batch(state, [fixtures.observation()])
        state["last_success"] = fixtures.NOW.isoformat()
        make_reports(state, self.setup.rules, week(fixtures.NOW))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            store_state(path, state, empty_state(), self.setup.journals)
            first = synchronize(path, now=fixtures.NOW + timedelta(hours=1))
            second = synchronize(path, now=fixtures.NOW + timedelta(hours=2))
            self.assertEqual(first["reports"], second["reports"])
            self.assertEqual(len(second["reports"]), 1)
            self.assertEqual(len(second["papers"]), 1)
            self.assertEqual(second["papers"][fixtures.DOI]["first_seen"], state["papers"][fixtures.DOI]["first_seen"])
            self.assertEqual(second["papers"][fixtures.DOI]["publication_date"], "2026-10-31")

    @patch("energy_lit.sync.discover", side_effect=SourceError("network unavailable"))
    def test_severe_failure_preserves_previous_file(self, discover):
        state = empty_state()
        self.setup.batch(state, [fixtures.observation()])
        state["last_success"] = fixtures.NOW.isoformat()
        make_reports(state, self.setup.rules)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            store_state(path, state, empty_state(), self.setup.journals)
            previous = path.read_bytes()
            with self.assertRaises(SourceError):
                synchronize(path, now=fixtures.NOW)
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(read_state(path), state)
            self.assertFalse(path.with_suffix(".lock").exists())
            with exclusive_sync(path):
                with self.assertRaisesRegex(ValueError, "lock already exists"):
                    synchronize(path, now=fixtures.NOW)
            with self.assertRaisesRegex(ValueError, "Anomalous paper-count"):
                store_state(path, empty_state(), state, self.setup.journals)
            self.assertEqual(path.read_bytes(), previous)

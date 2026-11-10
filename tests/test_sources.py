import unittest
from unittest.mock import patch

from energy_lit.model import load_journals
from energy_lit.sources import SourceError, crossref_pages, openalex_pages


class PaginationTests(unittest.TestCase):
    @patch("energy_lit.sources.fetch")
    def test_crossref_uses_cursor_without_incompatible_sort(self, fetch):
        fetch.side_effect = [
            {"message": {"items": [{}] * 250, "next-cursor": "next"}},
            {"message": {"items": []}},
        ]
        pages = list(crossref_pages(load_journals(), "2026-11-01", "2026-11-02"))
        self.assertEqual(list(map(len, pages)), [250, 0])
        self.assertNotIn("sort", fetch.call_args_list[0].args[1])
        self.assertEqual(fetch.call_args_list[1].args[1]["cursor"], "next")

    @patch.dict("os.environ", {"OPENALEX_API_KEY": ""})
    @patch("energy_lit.sources.fetch")
    @patch("energy_lit.sources.TOPIC_QUERIES", ("battery",))
    def test_openalex_no_key_pagination(self, fetch):
        fetch.side_effect = [
            {"meta": {"count": 101}, "results": [{}] * 100},
            {"meta": {"count": 101}, "results": [{}]},
        ]
        pages = list(openalex_pages(load_journals(), "2026-11-01", "2026-11-02"))
        self.assertEqual(list(map(len, pages)), [100, 1])
        self.assertEqual([call.args[1]["page"] for call in fetch.call_args_list], [1, 2])


    @patch.dict("os.environ", {"OPENALEX_API_KEY": ""})
    @patch("energy_lit.sources.fetch")
    @patch("energy_lit.sources.TOPIC_QUERIES", ("battery",))
    def test_openalex_rejects_short_last_page(self, fetch):
        fetch.side_effect = [
            {"meta": {"count": 102}, "results": [{}] * 100},
            {"meta": {"count": 102}, "results": [{}]},
        ]
        with self.assertRaisesRegex(SourceError, "truncated"):
            list(openalex_pages(load_journals(), "2026-11-01", "2026-11-02"))


    @patch("energy_lit.sources.fetch")
    def test_indexed_crossref_stays_inside_publication_horizon(self, fetch):
        fetch.return_value = {"message": {"items": []}}
        list(crossref_pages(load_journals(), "2026-10-20", "2026-11-10", indexed=True,
                            publication_floor="2026-08-10"))
        self.assertIn("from-pub-date:2026-08-10", fetch.call_args.args[1]["filter"])
        self.assertIn("from-index-date:2026-10-20", fetch.call_args.args[1]["filter"])

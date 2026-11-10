import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tests import test_pipeline as fixtures
from energy_lit.model import empty_state, week
from energy_lit.site import build
from energy_lit.sync import make_reports


class SiteTests(unittest.TestCase):
    def test_render_and_feed(self):
        setup = fixtures.PipelineTests()
        setup.setUp()
        state = empty_state()
        row = fixtures.observation()
        row["title"] = "Lithium battery <script>alert(1)</script>"
        setup.batch(state, [row])
        make_reports(state, setup.rules, week(fixtures.NOW))
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            build(state, output, setup.journals, "https://example.org/hub/", None)
            for page in ("index", "library", "archive", "pending", "about"):
                self.assertTrue((output / f"{page}.html").exists())
            library = (output / "library.html").read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;", library)
            self.assertNotIn(row["abstract"], library)
            rss = ET.parse(output / "feed.xml")
            self.assertEqual(rss.findtext(".//guid"), f"https://doi.org/{fixtures.DOI}")
            self.assertEqual(len(rss.findall(".//item")), 1)

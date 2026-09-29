import unittest
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).parents[1]
HTML_PATH = ROOT / "app" / "static" / "index.html"


class FrontendContractTests(unittest.TestCase):
    def test_initial_form_has_exactly_three_user_inputs(self):
        document = BeautifulSoup(HTML_PATH.read_text(encoding="utf-8"), "html.parser")
        fields = document.select("#match-search input, #match-search select")

        self.assertEqual(
            [field.get("name") for field in fields],
            ["home_team", "away_team", "kickoff_local"],
        )

    def test_semantic_live_regions_and_assets_exist(self):
        document = BeautifulSoup(HTML_PATH.read_text(encoding="utf-8"), "html.parser")

        self.assertIsNotNone(document.select_one("#research-progress[aria-live]"))
        self.assertIsNotNone(document.select_one("#analysis-result[aria-live]"))
        self.assertIsNotNone(document.select_one("#evidence-list"))
        self.assertIsNotNone(document.select_one('link[href*="tokens.css"]'))
        self.assertIsNotNone(document.select_one('link[href*="app.css"]'))
        self.assertTrue(
            (ROOT / "app" / "static" / "assets" / "stadium-night.png").exists()
        )

    def test_form_fields_have_accessible_labels_and_mobile_input_sizes(self):
        document = BeautifulSoup(HTML_PATH.read_text(encoding="utf-8"), "html.parser")

        for field in document.select("#match-search input"):
            self.assertIsNotNone(document.select_one(f'label[for="{field.get("id")}"]'))
        self.assertEqual(
            document.select_one('meta[name="viewport"]')["content"],
            "width=device-width, initial-scale=1",
        )


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import textwrap
import unittest
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).parents[1]
HTML_PATH = ROOT / "app" / "static" / "index.html"
RESULTS_MODULE = (ROOT / "app" / "static" / "js" / "results.js").as_uri()
ODDS_MODULE = (ROOT / "app" / "static" / "js" / "odds-chart.js").as_uri()


def run_node(source: str):
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


class ResultRenderingTests(unittest.TestCase):
    def test_result_surface_exposes_validation_missing_and_evidence_regions(self):
        document = BeautifulSoup(HTML_PATH.read_text(encoding="utf-8"), "html.parser")

        self.assertIsNotNone(document.select_one("#validation-status"))
        self.assertIsNotNone(document.select_one("#missing-data"))
        self.assertIsNotNone(document.select_one("#odds-timeline"))
        self.assertIsNotNone(document.select_one("#evidence-list"))

    def test_result_model_keeps_unvalidated_status_and_filters_unsafe_evidence(self):
        result = run_node(
            textwrap.dedent(
                f"""
                import {{ buildResultViewModel }} from {json.dumps(RESULTS_MODULE)};
                console.log(JSON.stringify(buildResultViewModel({{
                  fixture: {{ home_team: "Arsenal", away_team: "Chelsea", competition: "Premier League", kickoff_utc: "2026-10-03T12:00:00Z" }},
                  action: "NO_BET_UNVALIDATED",
                  missing_sources: ["weather"],
                  data_completeness: 0.85,
                  quantitative: {{
                    result_probabilities: {{ home: 0.5, draw: 0.3, away: 0.2 }},
                    asian_state_probabilities: {{ full_loss: 0.2, half_loss: 0.1, push: 0.2, half_win: 0.1, full_win: 0.4 }},
                    asian_ev: 0.04,
                    asian_line: -0.25,
                    relative_direction: "home",
                    validated_for_betting: false,
                  }},
                  evidence: [
                    {{ title: "Trusted", url: "https://source.test/story", publisher: "Source" }},
                    {{ title: "Unsafe", url: "javascript:alert(1)", publisher: "Bad" }},
                  ],
                  ai_explanation: {{ summary: "Evidence summary", supporting_factors: ["Home form"], opposing_factors: [], risk_notes: ["Unvalidated"] }},
                }})));
                """
            )
        )

        self.assertEqual(result["actionLabel"], "暂不投注：模型尚未通过前瞻验证")
        self.assertFalse(result["validated"])
        self.assertEqual(result["probabilities"][0]["percent"], "50.0%")
        self.assertEqual([item["title"] for item in result["evidence"]], ["Trusted"])
        self.assertEqual(result["missing"], ["比赛地天气"])

    def test_odds_series_uses_only_recorded_snapshot_boundaries(self):
        result = run_node(
            textwrap.dedent(
                f"""
                import {{ buildOddsSeries }} from {json.dumps(ODDS_MODULE)};
                console.log(JSON.stringify(buildOddsSeries([
                  {{ bookmaker: "A", line: -0.25, home_price: 1.94, away_price: 1.92, captured_at: "2026-10-03T08:00:00Z" }},
                  {{ bookmaker: "A", line: -0.5, home_price: 2.02, away_price: 1.84, captured_at: "2026-10-03T10:00:00Z" }},
                  {{ bookmaker: "B", line: -0.25, home_price: 1.91, away_price: 1.95, captured_at: "2026-10-03T09:00:00Z" }}
                ])));
                """
            )
        )

        self.assertEqual(result["start"], "2026-10-03T08:00:00Z")
        self.assertEqual(result["end"], "2026-10-03T10:00:00Z")
        self.assertEqual(len(result["series"]["A"]), 2)
        self.assertEqual(len(result["series"]["B"]), 1)
        self.assertEqual(result["series"]["A"][1]["line"], -0.5)


if __name__ == "__main__":
    unittest.main()

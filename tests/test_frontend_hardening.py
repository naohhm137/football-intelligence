import json
import subprocess
import textwrap
import unittest
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).parents[1]
HTML_PATH = ROOT / "app" / "static" / "index.html"
SEARCH_MODULE = (ROOT / "app" / "static" / "js" / "search.js").as_uri()


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


class FrontendHardeningTests(unittest.TestCase):
    def test_page_has_retry_control_and_accessible_status_regions(self):
        document = BeautifulSoup(HTML_PATH.read_text(encoding="utf-8"), "html.parser")

        retry = document.select_one("#retry-analysis")
        self.assertIsNotNone(retry)
        self.assertEqual(retry.get("type"), "button")
        self.assertIsNotNone(document.select_one("#form-message[role='alert']"))
        self.assertIsNotNone(document.select_one("#research-progress[aria-live]"))

    def test_analysis_runner_times_out_without_losing_the_query(self):
        result = run_node(
            textwrap.dedent(
                f"""
                import {{ createAnalysisRunner }} from {json.dumps(SEARCH_MODULE)};
                let received;
                const submit = (query, {{ signal }}) => new Promise((resolve, reject) => {{
                  received = query;
                  signal.addEventListener("abort", () => reject(
                    Object.assign(new Error("aborted"), {{ name: "AbortError" }})
                  ));
                }});
                const runner = createAnalysisRunner({{ submit, timeoutMs: 5 }});
                try {{
                  await runner.run({{ home_team: "Arsenal", away_team: "Chelsea" }});
                }} catch (error) {{
                  console.log(JSON.stringify({{
                    name: error.name,
                    code: error.code,
                    received,
                  }}));
                }}
                """
            )
        )

        self.assertEqual(result["name"], "AnalysisApiError")
        self.assertEqual(result["code"], "REQUEST_TIMEOUT")
        self.assertEqual(result["received"]["home_team"], "Arsenal")

    def test_motion_focus_and_touch_safety_are_present(self):
        css = (ROOT / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")

        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("min-height: 44px", css)


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
API_MODULE = (ROOT / "app" / "static" / "js" / "api.js").as_uri()
SEARCH_MODULE = (ROOT / "app" / "static" / "js" / "search.js").as_uri()
PROGRESS_MODULE = (ROOT / "app" / "static" / "js" / "progress.js").as_uri()


def run_node(source: str) -> dict:
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


class FrontendApiContractTests(unittest.TestCase):
    def test_submit_match_posts_only_the_three_public_fields(self):
        result = run_node(
            textwrap.dedent(
                f"""
                import {{ submitMatch }} from {json.dumps(API_MODULE)};

                let captured;
                const fetchImpl = async (url, options) => {{
                  captured = {{ url, options }};
                  return {{
                    ok: true,
                    status: 200,
                    json: async () => ({{ analysis_id: "analysis-1" }}),
                  }};
                }};

                const result = await submitMatch({{
                  home_team: "  Arsenal ",
                  away_team: " Chelsea  ",
                  kickoff_local: "2026-10-03T20:00",
                  home_odds: 2.1,
                }}, {{ fetchImpl }});

                console.log(JSON.stringify({{
                  url: captured.url,
                  method: captured.options.method,
                  contentType: captured.options.headers["Content-Type"],
                  body: JSON.parse(captured.options.body),
                  result,
                }}));
                """
            )
        )

        self.assertEqual(result["url"], "/api/analyze")
        self.assertEqual(result["method"], "POST")
        self.assertEqual(result["contentType"], "application/json")
        self.assertEqual(
            result["body"],
            {
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "kickoff_local": "2026-10-03T12:00:00.000Z",
            },
        )
        self.assertEqual(result["result"]["analysis_id"], "analysis-1")

    def test_api_error_preserves_code_and_fixture_candidates(self):
        result = run_node(
            textwrap.dedent(
                f"""
                import {{ submitMatch }} from {json.dumps(API_MODULE)};

                const fetchImpl = async () => ({{
                  ok: false,
                  status: 409,
                  json: async () => ({{
                    error: {{ code: "AMBIGUOUS_FIXTURE", message: "请选择比赛" }},
                    candidates: [{{ fixture_id: 991, home_team: "A", away_team: "B" }}],
                  }}),
                }});

                try {{
                  await submitMatch({{
                    home_team: "A",
                    away_team: "B",
                    kickoff_local: "2026-10-03T20:00",
                  }}, {{ fetchImpl }});
                }} catch (error) {{
                  console.log(JSON.stringify({{
                    name: error.name,
                    code: error.code,
                    status: error.status,
                    candidates: error.candidates,
                  }}));
                }}
                """
            )
        )

        self.assertEqual(result["name"], "AnalysisApiError")
        self.assertEqual(result["code"], "AMBIGUOUS_FIXTURE")
        self.assertEqual(result["status"], 409)
        self.assertEqual(result["candidates"][0]["fixture_id"], 991)

    def test_starting_a_new_analysis_aborts_the_previous_request(self):
        result = run_node(
            textwrap.dedent(
                f"""
                import {{ createAnalysisRunner }} from {json.dumps(SEARCH_MODULE)};

                const signals = [];
                const submit = (query, {{ signal }}) => new Promise((resolve, reject) => {{
                  signals.push(signal);
                  signal.addEventListener("abort", () => reject(
                    Object.assign(new Error("aborted"), {{ name: "AbortError" }})
                  ));
                  if (query.home_team === "Second") resolve({{ analysis_id: "second" }});
                }});
                const activeStates = [];
                const runner = createAnalysisRunner({{
                  submit,
                  onActiveChange: (active) => activeStates.push(active),
                }});

                const first = runner.run({{ home_team: "First" }}).catch((error) => error.name);
                const second = runner.run({{ home_team: "Second" }});
                console.log(JSON.stringify({{
                  first: await first,
                  second: await second,
                  firstAborted: signals[0].aborted,
                  secondAborted: signals[1].aborted,
                  activeStates,
                }}));
                """
            )
        )

        self.assertEqual(result["first"], "AbortError")
        self.assertEqual(result["second"]["analysis_id"], "second")
        self.assertTrue(result["firstAborted"])
        self.assertFalse(result["secondAborted"])
        self.assertEqual(result["activeStates"], [True, True, False])

    def test_source_states_are_derived_from_the_real_report(self):
        result = run_node(
            textwrap.dedent(
                f"""
                import {{ sourceStatesFromReport }} from {json.dumps(PROGRESS_MODULE)};
                console.log(JSON.stringify(sourceStatesFromReport({{
                  missing_sources: ["odds", "news"],
                  source_statuses: [
                    {{ source: "news", status: "error", last_success_at: "2026-10-03T08:00:00Z", error_code: "SOURCE_TIMEOUT" }}
                  ],
                }})));
                """
            )
        )

        states = {item["id"]: item["state"] for item in result}
        self.assertEqual(states["fixture"], "success")
        self.assertEqual(states["team_context"], "success")
        self.assertEqual(states["weather"], "success")
        self.assertEqual(states["odds"], "missing")
        self.assertEqual(states["news"], "error")
        news = next(item for item in result if item["id"] == "news")
        self.assertIn("上次成功", news["detail"])


if __name__ == "__main__":
    unittest.main()

import json
import unittest

from app.ai_client import AilindoClient
from app.contracts import (
    AnalysisReport,
    EvidenceItem,
    QuantitativeReport,
    ResolvedFixture,
)


FIXTURE = ResolvedFixture(
    fixture_id=991,
    home_team="Arsenal",
    away_team="Chelsea",
    kickoff_utc="2026-10-03T12:00:00Z",
    competition="Premier League",
)
EVIDENCE = EvidenceItem(
    title="Official update",
    url="https://source.test/item",
    publisher="Club",
    published_at="2026-10-03T08:00:00Z",
    fetched_at="2026-10-03T09:00:00Z",
    summary="Confirmed team update.",
)
REPORT = AnalysisReport(
    fixture=FIXTURE,
    quantitative=QuantitativeReport(
        result_probabilities={"home": 0.5, "draw": 0.28, "away": 0.22}
    ),
    action="NO_BET_UNVALIDATED",
    evidence=(EVIDENCE,),
    data_completeness=0.75,
    analysis_id="analysis-1",
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeStreamingResponse(FakeResponse):
    def __init__(self, fragments, status_code=200):
        super().__init__({}, status_code)
        self.fragments = fragments

    def iter_lines(self, decode_unicode=False):
        lines = []
        for fragment in self.fragments:
            lines.extend(
                [
                    "data: "
                    + json.dumps(
                        {"choices": [{"delta": {"content": fragment}}]}
                    ),
                    "",
                ]
            )
        lines.append("data: [DONE]")
        return lines


class FakeSplitStreamingResponse(FakeResponse):
    def __init__(self, content, status_code=200):
        super().__init__({}, status_code)
        self.content = content

    def iter_lines(self, decode_unicode=False):
        event = json.dumps(
            {"choices": [{"delta": {"content": self.content}}]}
        )
        split_at = len(event) // 2
        return [
            "data: " + event[:split_at],
            "data: " + event[split_at:],
            "",
            "data: [DONE]",
        ]


class FakeMalformedStreamingResponse(FakeResponse):
    def __init__(self):
        super().__init__({})

    def iter_lines(self, decode_unicode=False):
        return ['data: {"choices":[{"delta":{"content":"unterminated']


class FakeTransport:
    def __init__(self, *, get_responses=None, post_responses=None):
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.get_calls = []
        self.post_calls = []

    def get(self, url, *, headers, timeout):
        self.get_calls.append({"url": url, "headers": headers, "timeout": timeout})
        response = self.get_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url, *, headers, json, timeout, stream=False):
        self.post_calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
                "stream": stream,
            }
        )
        response = self.post_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def completion(content):
    return FakeResponse({"choices": [{"message": {"content": content}}]})


class AilindoClientTests(unittest.TestCase):
    def test_streaming_completion_is_assembled(self):
        document = {
            "summary": "Arsenal slightly favoured.",
            "supporting_factors": [],
            "opposing_factors": [],
            "risk_notes": ["Research only"],
            "citations": [],
        }
        encoded = json.dumps(document)
        transport = FakeTransport(
            post_responses=[
                FakeStreamingResponse([encoded[:20], encoded[20:]])
            ]
        )
        client = AilindoClient(
            "https://gateway.test/v1",
            "secret-value",
            "new-provider-model",
            transport=transport,
        )

        explanation = client.explain(REPORT)

        self.assertTrue(transport.post_calls[0]["stream"])
        self.assertTrue(transport.post_calls[0]["json"]["stream"])
        self.assertTrue(explanation.trusted_json)
        self.assertEqual(explanation.summary, document["summary"])

    def test_split_sse_data_lines_are_reassembled_before_json_parsing(self):
        document = {
            "summary": "Arsenal slightly favoured.",
            "supporting_factors": [],
            "opposing_factors": [],
            "risk_notes": [],
            "citations": [],
        }
        transport = FakeTransport(
            post_responses=[
                FakeSplitStreamingResponse(json.dumps(document))
            ]
        )
        client = AilindoClient(
            "https://gateway.test/v1",
            "secret-value",
            "new-provider-model",
            transport=transport,
        )

        explanation = client.explain(REPORT)

        self.assertTrue(explanation.trusted_json)
        self.assertEqual(explanation.summary, document["summary"])

    def test_malformed_stream_is_retried_once(self):
        document = {
            "summary": "Arsenal slightly favoured.",
            "supporting_factors": [],
            "opposing_factors": [],
            "risk_notes": [],
            "citations": [],
        }
        transport = FakeTransport(
            post_responses=[
                FakeMalformedStreamingResponse(),
                FakeStreamingResponse([json.dumps(document)]),
            ]
        )
        client = AilindoClient(
            "https://gateway.test/v1",
            "secret-value",
            "new-provider-model",
            transport=transport,
        )

        explanation = client.explain(REPORT)

        self.assertEqual(len(transport.post_calls), 2)
        self.assertTrue(explanation.trusted_json)

    def test_configured_model_is_sent_verbatim(self):
        payload = json.dumps(
            {
                "summary": "Arsenal slightly favoured.",
                "supporting_factors": ["Recent form"],
                "opposing_factors": ["Incomplete odds"],
                "risk_notes": ["Research only"],
                "citations": ["https://source.test/item"],
            }
        )
        transport = FakeTransport(post_responses=[completion(payload)])
        client = AilindoClient(
            "https://gateway.test/v1", "secret-value", "new-provider-model",
            transport=transport
        )

        explanation = client.explain(REPORT)

        self.assertEqual(transport.post_calls[0]["json"]["model"], "new-provider-model")
        self.assertTrue(explanation.trusted_json)
        self.assertEqual(explanation.citations, ("https://source.test/item",))

    def test_prompt_contains_only_saved_evidence_and_requires_citations(self):
        transport = FakeTransport(post_responses=[completion("plain fallback")])
        client = AilindoClient(
            "https://gateway.test/v1", "secret-value", "new-provider-model",
            transport=transport
        )

        client.explain(REPORT)

        messages = transport.post_calls[0]["json"]["messages"]
        combined = "\n".join(message["content"] for message in messages)
        self.assertIn("https://source.test/item", combined)
        self.assertIn("禁止补充未提供的事实", combined)
        self.assertIn("NO_BET_UNVALIDATED", combined)
        self.assertIn("json", combined)
        self.assertIn("json", messages[1]["content"])
        self.assertIn("禁止换行", combined)
        self.assertIn("\\uXXXX", combined)
        self.assertNotIn("secret-value", combined)

    def test_invalid_citation_is_rejected(self):
        payload = json.dumps(
            {
                "summary": "Claim",
                "supporting_factors": [],
                "opposing_factors": [],
                "risk_notes": [],
                "citations": ["https://invented.test/story"],
            }
        )
        transport = FakeTransport(post_responses=[completion(payload)])
        client = AilindoClient(
            "https://gateway.test/v1", "secret-value", "new-provider-model",
            transport=transport
        )

        explanation = client.explain(REPORT)

        self.assertFalse(explanation.trusted_json)
        self.assertEqual(explanation.citations, ())
        self.assertIn("AI_CITATION_REJECTED", explanation.risk_notes)

    def test_verify_model_checks_models_and_minimal_chat(self):
        transport = FakeTransport(
            get_responses=[FakeResponse({"data": [{"id": "new-provider-model"}]})],
            post_responses=[completion("ok")],
        )
        client = AilindoClient(
            "https://gateway.test/v1/", "secret-value", "new-provider-model",
            transport=transport
        )

        health = client.verify_model()

        self.assertTrue(health.available)
        self.assertEqual(health.configured_model, "new-provider-model")
        self.assertEqual(transport.get_calls[0]["url"], "https://gateway.test/v1/models")
        self.assertEqual(
            transport.post_calls[0]["url"], "https://gateway.test/v1/chat/completions"
        )

    def test_unique_discovered_model_can_be_selected_but_multiple_cannot(self):
        unique_transport = FakeTransport(
            get_responses=[FakeResponse({"data": [{"id": "only-model"}]})],
            post_responses=[completion("ok")],
        )
        unique = AilindoClient(
            "https://gateway.test/v1", "secret-value", None,
            transport=unique_transport
        )
        ambiguous_transport = FakeTransport(
            get_responses=[
                FakeResponse({"data": [{"id": "model-a"}, {"id": "model-b"}]})
            ]
        )
        ambiguous = AilindoClient(
            "https://gateway.test/v1", "secret-value", None,
            transport=ambiguous_transport
        )

        self.assertEqual(unique.verify_model().configured_model, "only-model")
        ambiguous_health = ambiguous.verify_model()
        self.assertFalse(ambiguous_health.available)
        self.assertEqual(ambiguous_health.error_code, "MODEL_SELECTION_REQUIRED")
        self.assertEqual(ambiguous_transport.post_calls, [])

    def test_errors_never_include_api_key(self):
        transport = FakeTransport(get_responses=[FakeResponse({}, 503)])
        client = AilindoClient(
            "https://gateway.test/v1", "secret-value", "new-provider-model",
            transport=transport
        )

        result = client.verify_model()

        self.assertFalse(result.available)
        self.assertNotIn("secret-value", repr(result))
        self.assertNotIn("secret-value", repr(client))


if __name__ == "__main__":
    unittest.main()

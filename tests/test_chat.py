from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.domain.models import ChunkRecord
from backend.services.chat import _extract_citations, build_chat_response, local_preview_chat, synthesize_grounded_chat
from backend.services.indexing import AzureSearchKnowledgeBaseAdapter


class ChatServiceTests(unittest.TestCase):
    def test_extracts_citations_from_activity_references(self) -> None:
        payload = {
            "activity": [
                {
                    "references": [
                        {
                            "title": "Future of AI",
                            "sourceUri": "https://contoso.example/docs/future",
                            "chunkId": "chunk-001",
                            "doc_id": "doc-123",
                            "page_numbers": [9],
                            "image_evidence_json": '[{"artifact_id":"fig-1","description":"Adoption curve"}]',
                            "content": "Generative AI is becoming a general-purpose capability.",
                        }
                    ]
                }
            ]
        }

        citations = _extract_citations(payload)

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].title, "Future of AI")
        self.assertEqual(citations[0].chunk_id, "chunk-001")
        self.assertEqual(citations[0].doc_id, "doc-123")
        self.assertEqual(citations[0].page_numbers, [9])
        self.assertEqual(citations[0].image_evidence[0]["artifact_id"], "fig-1")

    def test_build_chat_response_extracts_subqueries(self) -> None:
        payload = {
            "activity": [
                {
                    "type": "searchIndex",
                    "id": 0,
                    "knowledgeSourceName": "enterprise-knowledge-source",
                    "count": 7,
                    "elapsedMs": 123,
                    "searchIndexArguments": {"search": "future of generative AI energy demand"},
                }
            ],
            "answer": "placeholder",
        }

        response = build_chat_response(payload)

        self.assertEqual(response.diagnostics["subqueries"][0]["search"], "future of generative AI energy demand")

    @patch("backend.services.chat.settings.azure_foundry_chat_deployment", new="gpt-5-4")
    @patch("backend.services.chat.settings.azure_foundry_resource_endpoint", new="https://example.cognitiveservices.azure.com/")
    @patch("backend.services.chat.call_foundry_text")
    def test_synthesizes_grounded_answer_with_gpt(self, mock_completion) -> None:
        retrieval_payload = {
            "activity": [
                {
                    "references": [
                        {
                            "title": "Future of AI",
                            "sourceUri": "https://contoso.example/docs/future",
                            "chunkId": "chunk-001",
                            "content": "Generative AI is becoming a general-purpose capability.",
                        }
                    ]
                }
            ]
        }

        mock_completion.return_value = (
            "Generative AI is becoming a general-purpose capability across industries. [1]",
            "https://example.openai.azure.com/openai/v1/chat/completions",
        )

        response = synthesize_grounded_chat("What is changing?", retrieval_payload)

        self.assertIn("[1]", response.answer)
        self.assertEqual(response.diagnostics["mode"], "search_plus_gpt54")
        self.assertEqual(response.diagnostics["model"], "gpt-5-4")
        self.assertEqual(len(response.citations), 1)

    def test_local_preview_chat_respects_selected_corpora(self) -> None:
        chunks = [
            ChunkRecord(
                chunk_id="chunk-1",
                doc_id="doc-a",
                source_name="A.pdf",
                checksum="a",
                clean_text="Labor shortages are a major issue in this report.",
                token_estimate=10,
            ),
            ChunkRecord(
                chunk_id="chunk-2",
                doc_id="doc-b",
                source_name="B.pdf",
                checksum="b",
                clean_text="Safety risk drives schedule pressure in this report.",
                token_estimate=10,
            ),
        ]

        response = local_preview_chat("labor shortages", chunks, doc_ids=["doc-a"])

        self.assertEqual(len(response.citations), 1)
        self.assertEqual(response.citations[0].doc_id, "doc-a")
        self.assertEqual(response.diagnostics["selected_doc_ids"], ["doc-a"])

    def test_build_doc_filter_escapes_values(self) -> None:
        adapter = AzureSearchKnowledgeBaseAdapter()

        result = adapter._build_doc_filter(["doc-a", "doc-b", "doc'a"])

        self.assertEqual(result, "doc_id eq 'doc-a' or doc_id eq 'doc-b' or doc_id eq 'doc''a'")


if __name__ == "__main__":
    unittest.main()

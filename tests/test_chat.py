from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.core.config import SearchKnowledgeSourceConfig
from backend.domain.models import ChatCitation, ChunkRecord
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

    @patch("backend.services.chat._search_supporting_chunks")
    def test_extract_citations_supplements_missing_positive_source_from_activity(self, mock_supporting_chunks) -> None:
        mock_supporting_chunks.return_value = [
            ChatCitation(
                title="Energy report",
                doc_id="doc-energy",
                chunk_id="energy-chunk-1",
                snippet="Power availability is now an early project dependency.",
                knowledge_source="energy-knowledge-source",
                index_name="energy-knowledge-index",
                evidence_kind="activity_support",
                supporting_query="energy supply impacts on project delivery",
                retrieval_step=2,
            )
        ]
        payload = {
            "citations": [
                {
                    "title": "Construction report",
                    "doc_id": "doc-construction",
                    "chunk_id": "construction-chunk-1",
                    "snippet": "Construction delivery is becoming more complex.",
                    "knowledgeSourceName": "enterprise-knowledge-source",
                    "index_name": "enterprise-knowledge-index",
                }
            ],
            "diagnostics": {
                "knowledge_source_index_map": {
                    "enterprise-knowledge-source": "enterprise-knowledge-index",
                    "energy-knowledge-source": "energy-knowledge-index",
                }
            },
            "activity": [
                {
                    "type": "searchIndex",
                    "knowledgeSourceName": "enterprise-knowledge-source",
                    "count": 10,
                    "elapsedMs": 100,
                    "searchIndexArguments": {"search": "construction delivery complexity"},
                },
                {
                    "type": "searchIndex",
                    "knowledgeSourceName": "energy-knowledge-source",
                    "count": 7,
                    "elapsedMs": 90,
                    "searchIndexArguments": {"search": "energy supply impacts on project delivery"},
                },
            ],
        }

        citations = _extract_citations(payload)

        self.assertEqual(
            [citation.knowledge_source for citation in citations[:2]],
            ["enterprise-knowledge-source", "energy-knowledge-source"],
        )
        self.assertEqual(citations[1].supporting_query, "energy supply impacts on project delivery")
        self.assertEqual(citations[1].reference_id, 2)

    def test_extract_citations_prefers_richer_duplicate_metadata(self) -> None:
        payload = {
            "citations": [
                {
                    "title": "Construction report",
                    "snippet": "Project teams need stronger document control because permitting packs move faster than manual coordination can absorb.",
                },
                {
                    "title": "Construction report enriched",
                    "doc_id": "doc-construction",
                    "chunk_id": "chunk-42",
                    "snippet": "Project teams need stronger document control because permitting packs move faster than manual coordination can absorb.",
                    "knowledgeSourceName": "enterprise-knowledge-source",
                    "index_name": "enterprise-knowledge-index",
                },
            ]
        }

        citations = _extract_citations(payload)

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].chunk_id, "chunk-42")
        self.assertEqual(citations[0].knowledge_source, "enterprise-knowledge-source")

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

    @patch(
        "backend.services.indexing.settings.azure_search_extra_sources",
        new=(
            SearchKnowledgeSourceConfig(
                knowledge_source_name="construction-source",
                index_name="construction-index",
                description="Construction safety schedules BIM delivery",
                route_keywords=("construction", "bim", "safety"),
            ),
            SearchKnowledgeSourceConfig(
                knowledge_source_name="energy-source",
                index_name="energy-index",
                description="Power demand grid transmission generation data centers",
                route_keywords=("power", "grid", "energy", "data center"),
            ),
        ),
    )
    @patch("backend.services.indexing.AzureSearchKnowledgeBaseAdapter._published_document_terms_for_source", return_value=set())
    def test_route_knowledge_sources_selects_keyword_matched_extra_index(self, _mock_terms) -> None:
        adapter = AzureSearchKnowledgeBaseAdapter()

        selected, diagnostics = adapter._route_knowledge_sources(
            "How does construction safety interact with BIM delivery risk?"
        )

        self.assertEqual(
            [source.knowledge_source_name for source in selected],
            ["construction-source"],
        )
        self.assertFalse(diagnostics["multi_index_routing"])
        self.assertEqual(diagnostics["routing_mode"], "keyword_routed")

    @patch(
        "backend.services.indexing.settings.azure_search_extra_sources",
        new=(
            SearchKnowledgeSourceConfig(
                knowledge_source_name="construction-source",
                index_name="construction-index",
                description="Construction safety schedules BIM delivery",
                route_keywords=("construction", "bim", "safety"),
            ),
            SearchKnowledgeSourceConfig(
                knowledge_source_name="energy-source",
                index_name="energy-index",
                description="Power demand grid transmission generation data centers",
                route_keywords=("power", "grid", "energy", "data center"),
            ),
        ),
    )
    def test_route_knowledge_sources_uses_all_indexes_for_cross_source_queries(self) -> None:
        adapter = AzureSearchKnowledgeBaseAdapter()

        selected, diagnostics = adapter._route_knowledge_sources(
            "Compare construction delivery risk with grid capacity constraints across the indexes."
        )

        self.assertEqual(
            [source.knowledge_source_name for source in selected],
            ["enterprise-knowledge-source", "construction-source", "energy-source"],
        )
        self.assertTrue(diagnostics["multi_index_routing"])
        self.assertEqual(diagnostics["routing_mode"], "cross_source_intent")

    @patch(
        "backend.services.indexing.settings.azure_search_extra_sources",
        new=(
            SearchKnowledgeSourceConfig(
                knowledge_source_name="construction-source",
                index_name="construction-index",
                description="Construction safety schedules BIM delivery",
                route_keywords=("construction",),
            ),
        ),
    )
    def test_custom_doc_scope_keeps_search_on_primary_index(self) -> None:
        adapter = AzureSearchKnowledgeBaseAdapter()

        selected, diagnostics = adapter._route_knowledge_sources(
            "Compare construction delivery risk with the uploaded corpus.",
            doc_ids=["doc-a"],
        )

        self.assertEqual([source.knowledge_source_name for source in selected], ["enterprise-knowledge-source"])
        self.assertFalse(diagnostics["multi_index_routing"])
        self.assertEqual(diagnostics["routing_mode"], "custom_doc_scope")

    @patch(
        "backend.services.indexing.settings.azure_search_extra_sources",
        new=(
            SearchKnowledgeSourceConfig(
                knowledge_source_name="construction-source",
                index_name="construction-index",
                description="Construction safety schedules BIM delivery",
                route_keywords=("construction",),
            ),
            SearchKnowledgeSourceConfig(
                knowledge_source_name="energy-source",
                index_name="energy-index",
                description="Power demand grid transmission generation data centers",
                route_keywords=("power",),
            ),
        ),
    )
    def test_knowledge_base_body_references_multiple_sources(self) -> None:
        adapter = AzureSearchKnowledgeBaseAdapter()

        body = adapter._knowledge_base_body()

        self.assertEqual(
            [item["name"] for item in body["knowledgeSources"]],
            ["enterprise-knowledge-source", "construction-source", "energy-source"],
        )

    @patch(
        "backend.services.indexing.settings.azure_search_extra_sources",
        new=(
            SearchKnowledgeSourceConfig(
                knowledge_source_name="energy-source",
                index_name="energy-index",
                description="Power systems electricity grid transmission interconnection load growth",
                route_keywords=("power", "grid", "energy"),
                assignment_keywords=("power", "electricity", "grid"),
            ),
        ),
    )
    def test_select_target_source_for_document_assigns_energy_index(self) -> None:
        adapter = AzureSearchKnowledgeBaseAdapter()

        target, diagnostics = adapter._select_target_source_for_document(
            source_name="power-system-transformation-report.pdf",
            route_text="Grid modernization load growth interconnection queues",
        )

        self.assertEqual(target.knowledge_source_name, "energy-source")
        self.assertEqual(target.index_name, "energy-index")
        self.assertEqual(diagnostics["assignment_mode"], "keyword_assigned")

    @patch(
        "backend.services.indexing.settings.azure_search_extra_sources",
        new=(
            SearchKnowledgeSourceConfig(
                knowledge_source_name="energy-source",
                index_name="energy-index",
                description="Power systems electricity grid transmission interconnection load growth",
                route_keywords=("power", "grid", "energy"),
                assignment_keywords=("power", "electricity", "grid"),
            ),
            SearchKnowledgeSourceConfig(
                knowledge_source_name="construction-source",
                index_name="construction-index",
                description="Construction BIM safety retrofit project delivery",
                route_keywords=("construction", "bim", "retrofit"),
                assignment_keywords=("construction", "retrofit", "bim"),
            ),
        ),
    )
    def test_custom_doc_scope_groups_selected_docs_by_source(self) -> None:
        adapter = AzureSearchKnowledgeBaseAdapter()

        selected, diagnostics = adapter._route_knowledge_sources(
            "Use the selected corpora only.",
            doc_ids=["doc-energy", "doc-construction"],
            doc_source_assignments={
                "doc-energy": "energy-source",
                "doc-construction": "construction-source",
            },
        )

        self.assertEqual(
            [source.knowledge_source_name for source in selected],
            ["energy-source", "construction-source"],
        )
        self.assertTrue(diagnostics["multi_index_routing"])
        self.assertEqual(
            diagnostics["custom_scope_groups"],
            {
                "energy-source": ["doc-energy"],
                "construction-source": ["doc-construction"],
            },
        )

    def test_build_retrieve_payload_keeps_knowledge_source_params_flat(self) -> None:
        adapter = AzureSearchKnowledgeBaseAdapter()

        payload = adapter._build_retrieve_payload(
            "Use both corpora",
            [
                {"knowledgeSourceName": "enterprise-knowledge-source", "kind": "searchIndex"},
                {"knowledgeSourceName": "energy-source", "kind": "searchIndex"},
            ],
        )

        self.assertIsInstance(payload["knowledgeSourceParams"], list)
        self.assertEqual(len(payload["knowledgeSourceParams"]), 2)
        self.assertEqual(
            payload["knowledgeSourceParams"][0]["knowledgeSourceName"],
            "enterprise-knowledge-source",
        )
        self.assertEqual(payload["knowledgeSourceParams"][1]["knowledgeSourceName"], "energy-source")


if __name__ == "__main__":
    unittest.main()

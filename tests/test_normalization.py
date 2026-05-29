from __future__ import annotations

import unittest
from unittest.mock import PropertyMock, patch

from backend.core.config import settings
from backend.domain.models import IntermediateDocument, SectionNode
from backend.services.normalization import normalize_document


class NormalizationTests(unittest.TestCase):
    def test_stitches_cross_segment_paragraphs_and_merges_generic_sections(self) -> None:
        document = IntermediateDocument(
            doc_id="doc-1",
            source_name="sample.pdf",
            source_path="sample.pdf",
            format="pdf",
            complexity="complex",
            parser_path="azure_document_intelligence",
            metadata={"segmentation_strategy": "pdf_page_segmentation"},
            sections=[
                SectionNode(
                    heading="Pages 1-250",
                    page_start=1,
                    page_end=250,
                    paragraphs=["This paragraph ends without punctuation and continues"],
                ),
                SectionNode(
                    heading="Pages 251-500",
                    page_start=251,
                    page_end=500,
                    paragraphs=[
                        "into the next segment where the thought completes.",
                        "A new paragraph starts here.",
                    ],
                ),
            ],
        )

        normalized = normalize_document(document)

        self.assertEqual(len(normalized.sections), 1)
        self.assertEqual(
            normalized.sections[0].paragraphs[0],
            "This paragraph ends without punctuation and continues into the next segment where the thought completes.",
        )
        self.assertEqual(normalized.sections[0].paragraphs[1], "A new paragraph starts here.")
        self.assertEqual(normalized.sections[0].page_start, 1)
        self.assertEqual(normalized.sections[0].page_end, 500)
        self.assertEqual(normalized.metadata["boundary_stitch"]["heuristic_merges"], 1)

    def test_stitches_generic_follow_on_segment_into_named_section(self) -> None:
        document = IntermediateDocument(
            doc_id="doc-2",
            source_name="sample.pdf",
            source_path="sample.pdf",
            format="pdf",
            complexity="complex",
            parser_path="azure_document_intelligence",
            metadata={"segmentation_strategy": "pdf_page_segmentation"},
            sections=[
                SectionNode(
                    heading="Section 3. Project Delivery",
                    page_start=180,
                    page_end=250,
                    paragraphs=["Project delivery becomes harder as power dependencies move earlier"],
                ),
                SectionNode(
                    heading="Pages 251-500",
                    page_start=251,
                    page_end=500,
                    paragraphs=["into permitting, utility coordination, and schedule control."],
                ),
            ],
        )

        normalized = normalize_document(document)

        self.assertEqual(len(normalized.sections), 1)
        self.assertEqual(normalized.sections[0].heading, "Section 3. Project Delivery")
        self.assertIn("utility coordination", normalized.sections[0].paragraphs[0])
        self.assertEqual(normalized.sections[0].page_end, 500)

    @patch("backend.services.normalization.stitch_segment_boundary_with_foundry")
    def test_uses_llm_for_ambiguous_segment_boundary_when_available(self, mock_stitch) -> None:
        mock_stitch.return_value = (
            "Project delivery depends on early power coordination across regions and utility readiness."
        )
        document = IntermediateDocument(
            doc_id="doc-3",
            source_name="sample.pdf",
            source_path="sample.pdf",
            format="pdf",
            complexity="complex",
            parser_path="azure_document_intelligence",
            metadata={"segmentation_strategy": "pdf_page_segmentation"},
            sections=[
                SectionNode(
                    heading="Pages 1-250",
                    page_start=1,
                    page_end=250,
                    paragraphs=["Project delivery depends on early power coordination"],
                ),
                SectionNode(
                    heading="Pages 251-500",
                    page_start=251,
                    page_end=500,
                    paragraphs=["Across regions and utility readiness."],
                ),
            ],
        )

        with patch(
            "backend.services.normalization.settings.enable_llm_boundary_stitching",
            True,
        ), patch.object(
            type(settings),
            "azure_foundry_chat_enabled",
            new_callable=PropertyMock,
            return_value=True,
        ):
            normalized = normalize_document(document)

        self.assertEqual(len(normalized.sections), 1)
        self.assertEqual(
            normalized.sections[0].paragraphs[0],
            "Project delivery depends on early power coordination across regions and utility readiness.",
        )
        self.assertEqual(normalized.metadata["boundary_stitch"]["llm_merges"], 1)
        mock_stitch.assert_called_once()


if __name__ == "__main__":
    unittest.main()

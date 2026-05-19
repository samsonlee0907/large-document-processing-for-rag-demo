import unittest

from backend.domain.models import IntermediateDocument, SectionNode
from backend.services.chunking import ChunkPolicy, StructureAwareChunker


class ChunkingTests(unittest.TestCase):
    def test_structure_aware_chunker_preserves_section_path(self) -> None:
        document = IntermediateDocument(
            doc_id="doc-1",
            source_name="sample.txt",
            source_path="sample.txt",
            format="txt",
            complexity="simple",
            parser_path="local_simple_parser",
            sections=[
                SectionNode(
                    heading="Policy",
                    paragraphs=[
                        " ".join(["travel"] * 220),
                    ],
                )
            ],
        )
        chunker = StructureAwareChunker(ChunkPolicy(chunk_size_tokens=80, overlap_tokens=20))

        chunks = chunker.chunk(document)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].section_path, ["Policy"])
        self.assertTrue(all(chunk.clean_text for chunk in chunks))


if __name__ == "__main__":
    unittest.main()

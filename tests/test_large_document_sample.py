from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from PIL import Image

from backend.core.config import settings
from backend.services.parsers import (
    AzureDocumentIntelligenceParser,
    ParagraphBlock,
    _extract_pdf_figure_artifacts,
)
from backend.services.sample_documents import (
    CONSTRUCTION_INDUSTRY_SECTIONS,
    POWER_SYSTEM_TRANSFORMATION_SECTIONS,
    _build_section_diagram,
    _render_research_report_pdf,
)


class LargeDocumentSampleTests(unittest.TestCase):
    def _render_small_research_pdf(self, path: Path, page_count: int) -> None:
        diagram_dir = path.parent / "diagrams"
        diagram_dir.mkdir(parents=True, exist_ok=True)
        sections = POWER_SYSTEM_TRANSFORMATION_SECTIONS[:2]
        diagram_paths = [_build_section_diagram(section, index + 1, diagram_dir) for index, section in enumerate(sections)]
        _render_research_report_pdf(
            path,
            page_count,
            sections,
            diagram_paths,
            report_title="Power Systems In The Age Of Electricity",
            report_subtitle="Test Fixture",
        )

    def test_render_pdf_creates_expected_page_count(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "large-sample.pdf"
            self._render_small_research_pdf(path, 11)

            reader = PdfReader(str(path))
            self.assertEqual(len(reader.pages), 11)

    def test_split_pdf_creates_bounded_segments(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "split-sample.pdf"
            self._render_small_research_pdf(path, 11)

            parser = AzureDocumentIntelligenceParser()
            segments = parser._split_pdf(path, 4)

            self.assertEqual(len(segments), 3)
            self.assertEqual((segments[0].page_start, segments[0].page_end), (1, 4))
            self.assertEqual((segments[-1].page_start, segments[-1].page_end), (9, 11))

    def test_pdf_image_extraction_returns_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            from PIL import Image, ImageDraw
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas

            base = Path(directory)
            image_path = base / "figure.png"
            pdf_path = base / "with-figure.pdf"

            image = Image.new("RGB", (240, 120), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((12, 12, 228, 108), outline="black", width=3)
            draw.text((24, 48), "AI figure", fill="black")
            image.save(image_path)

            pdf = canvas.Canvas(str(pdf_path), pagesize=letter)
            pdf.drawImage(str(image_path), 100, 500, width=240, height=120)
            pdf.save()

            with patch("backend.services.parsers.build_blob_artifact_store", return_value=None):
                figures = _extract_pdf_figure_artifacts(pdf_path, "doc-figure-test", "with-figure.pdf")

            self.assertGreaterEqual(len(figures), 1)
            self.assertEqual(figures[0]["page_number"], 1)

    def test_pdf_image_extraction_skips_decompression_bomb_and_normalizes_formats(self) -> None:
        class StubImage:
            def __init__(self) -> None:
                self.name = "oversized-plan.tiff"
                self.data = b"raw-bytes"
                self.image = Image.new("RGB", (300, 120), "white")

        class StubImages:
            def keys(self) -> list[str]:
                return ["bad", "good"]

            def __getitem__(self, key: str) -> StubImage:
                if key == "bad":
                    raise Image.DecompressionBombError("too large")
                return StubImage()

        class StubPage:
            images = StubImages()

        class StubReader:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.pages = [StubPage()]

        with TemporaryDirectory() as directory:
            artifacts_dir = Path(directory) / "artifacts"
            with (
                patch("backend.services.parsers.PdfReader", StubReader),
                patch("backend.services.parsers.build_blob_artifact_store", return_value=None),
                patch.object(settings, "artifacts_dir", artifacts_dir),
            ):
                figures = _extract_pdf_figure_artifacts(Path("ignored.pdf"), "doc-oversized", "ignored.pdf")

        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0]["page_number"], 1)
        self.assertTrue(str(figures[0]["artifact_path"]).endswith(".png"))
        self.assertEqual(figures[0]["output_format"], "png")
        self.assertTrue(figures[0]["normalized_image"])

    def test_construction_blueprint_diagram_renders(self) -> None:
        with TemporaryDirectory() as directory:
            output = _build_section_diagram(CONSTRUCTION_INDUSTRY_SECTIONS[4], 5, Path(directory))
            self.assertTrue(output.exists())
            self.assertEqual(output.suffix.lower(), ".png")

    def test_power_system_architecture_diagram_renders(self) -> None:
        with TemporaryDirectory() as directory:
            output = _build_section_diagram(POWER_SYSTEM_TRANSFORMATION_SECTIONS[8], 9, Path(directory))
            self.assertTrue(output.exists())
            self.assertEqual(output.suffix.lower(), ".png")

    def test_pdf_size_limit_can_trigger_split(self) -> None:
        parser = AzureDocumentIntelligenceParser()
        profile = type(
            "Profile",
            (),
            {"page_count": 8},
        )()

        with patch.object(
            parser,
            "_file_size_bytes",
            return_value=settings.hard_file_split_threshold_bytes + (25 * 1024 * 1024),
        ):
            self.assertTrue(parser._should_split_pdf(Path("oversized.pdf"), profile))
            self.assertEqual(parser._recommended_segment_size(Path("oversized.pdf"), profile), 4)

    def test_structured_sections_preserve_paragraph_level_page_ranges(self) -> None:
        parser = AzureDocumentIntelligenceParser()

        sections = parser._build_structured_sections(
            [
                ParagraphBlock("Section 1. Capability Frontier", page_start=11, page_end=11),
                ParagraphBlock("Capability is rising across multimodal and agentic systems.", page_start=11, page_end=12),
                ParagraphBlock("Section 2. Delivery Bottlenecks", page_start=13, page_end=13),
                ParagraphBlock("Grid constraints and permitting timelines shape project delivery.", page_start=13, page_end=14),
            ],
            "Pages 11-14",
        )

        self.assertEqual(len(sections), 2)
        self.assertEqual((sections[0].page_start, sections[0].page_end), (11, 12))
        self.assertEqual((sections[1].page_start, sections[1].page_end), (13, 14))


if __name__ == "__main__":
    unittest.main()

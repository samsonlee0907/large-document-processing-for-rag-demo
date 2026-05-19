from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.services.parsers import parser_registry


class ParserTests(unittest.TestCase):
    def test_markdown_parser_creates_sections(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "guide.md"
            path.write_text("# Heading\n\nFirst paragraph.\n\n## Details\n\nSecond paragraph.", encoding="utf-8")

            profile = parser_registry.detect(path)
            document = parser_registry.parse(path, "doc-123", profile)

            self.assertEqual(profile.parser_path, "local_simple_parser")
            self.assertEqual(len(document.sections), 2)
            self.assertEqual(document.sections[0].heading, "Heading")
            self.assertIn("Second paragraph.", document.sections[1].paragraphs)


if __name__ == "__main__":
    unittest.main()

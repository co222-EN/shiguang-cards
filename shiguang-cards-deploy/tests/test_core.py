from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.ai import extract_output_text, fallback_analysis
from app.images import crop_to_ratio, make_images
from app.models import MomentRecord, RecordPatch
from app.storage import LocalStore


class ImageTests(unittest.TestCase):
    def test_crop_to_card_ratio(self) -> None:
        image = Image.new("RGB", (1200, 800), "white")
        cropped = crop_to_ratio(image)
        self.assertAlmostEqual(cropped.width / cropped.height, 4 / 5, places=2)

    def test_make_images(self) -> None:
        source = Image.new("RGB", (900, 1200), "#f3a6a6")
        buffer = BytesIO()
        source.save(buffer, format="JPEG")
        with tempfile.TemporaryDirectory() as temp:
            paths = make_images(buffer.getvalue(), Path(temp), "abc")
            self.assertTrue(paths["original"].exists())
            self.assertTrue(paths["cropped"].exists())
            self.assertTrue(paths["thumb"].exists())


class StorageTests(unittest.TestCase):
    def test_local_store_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = LocalStore(Path(temp))
            analysis = fallback_analysis()
            record = MomentRecord.from_analysis(
                record_id="one",
                analysis=analysis,
                image_url="/data/photos/cropped/one.jpg",
                thumbnail_url="/data/photos/thumbs/one.jpg",
                original_url="/data/photos/original/one.jpg",
            )
            store.save_record(record)
            self.assertEqual(len(store.list_records()), 1)
            updated = store.update_record(record.id, patch=RecordPatch(title="changed"))
            self.assertEqual(updated.title, "changed")
            analyzed = fallback_analysis("ok")
            analyzed.title = "AI title"
            analyzed.tags = ["AI"]
            updated_analysis = store.update_analysis(record.id, analyzed)
            self.assertEqual(updated_analysis.title, "AI title")
            self.assertEqual(updated_analysis.ai_status, "ok")
            store.delete_record(record.id)
            self.assertEqual(store.list_records(), [])


class AiTests(unittest.TestCase):
    def test_extract_output_text(self) -> None:
        payload = {"output": [{"content": [{"text": "{\"title\":\"x\"}"}]}]}
        self.assertEqual(extract_output_text(payload), "{\"title\":\"x\"}")


if __name__ == "__main__":
    unittest.main()

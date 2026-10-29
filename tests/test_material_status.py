"""Saved material status with synthetic temporary inputs; never production artwork."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sprite_pipeline.application.materials import source_material_state
from sprite_pipeline.storage.configuration import Config, source_fingerprint


class MaterialStatusTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "source").mkdir()
        (self.root / "source" / "sheet.png").write_bytes(b"synthetic source fingerprint input")
        self.cfg = Config(
            self.root / "pipeline.json",
            self.root,
            {
                "frame_size": [16, 16],
                "anchor": {"pixels": [8, 16], "x": 0.5, "y": 1.0},
                "paths": {},
                "sources": {"sheet.png": {"extract": {"method": "image"}}},
                "actions": {},
            },
        )
        self.directory = self.root / "processed_sprites" / "sheet"
        self.directory.mkdir(parents=True)

    def stage(self, **changes):
        value = {
            "stage": "process",
            "source": "sheet.png",
            "files": ["000.png"],
            "fingerprint": source_fingerprint(self.cfg, "sheet.png"),
            **changes,
        }
        (self.directory / "_stage.json").write_text(json.dumps(value), encoding="utf-8")

    def state(self, *files):
        return source_material_state(self.cfg, "sheet.png", set(files))

    def test_absent_materials_are_unprocessed_even_without_fingerprint(self):
        value = self.state()
        self.assertFalse(value["stale"])
        self.assertEqual(value["material_status"]["key"], "unprocessed")
        self.assertTrue(value["material_status"]["pending"])

    def test_existing_frames_without_inventory_are_unknown(self):
        value = self.state("000.png")
        self.assertEqual(value["material_status"]["key"], "unknown")
        self.assertFalse(value["material_status"]["pending"])

    def test_existing_frames_without_fingerprint_are_unknown(self):
        self.stage(fingerprint=None)
        value = self.state("000.png")
        self.assertFalse(value["stale"])
        self.assertEqual(value["material_status"]["key"], "unknown")

    def test_matching_fingerprint_and_complete_inventory_are_synced(self):
        self.stage()
        before = (self.directory / "_stage.json").read_bytes()
        value = self.state("000.png")
        self.assertEqual(value["material_status"]["key"], "synced")
        self.assertFalse(value["stale"])
        self.assertEqual((self.directory / "_stage.json").read_bytes(), before)

    def test_matching_fingerprint_does_not_hide_missing_outputs(self):
        self.stage(files=["000.png", "001.png"])
        value = self.state("000.png")
        self.assertFalse(value["stale"])
        self.assertEqual(value["material_status"]["key"], "pending")
        self.assertIn("1", value["material_status"]["reason"])

    def test_all_recorded_outputs_missing_are_pending(self):
        self.stage()
        self.assertEqual(self.state()["material_status"]["key"], "pending")

    def test_changed_digest_preserves_legacy_stale_and_honest_generic_reason(self):
        self.stage(fingerprint="older digest")
        value = self.state("000.png")
        self.assertTrue(value["stale"])
        self.assertEqual(value["material_status"]["key"], "pending")
        self.assertIn("无法细分原因", value["material_status"]["reason"])

    def test_corrupt_inventory_does_not_break_snapshot_or_claim_synced(self):
        path = self.directory / "_stage.json"
        for content in ("not JSON", "null", "[]"):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                self.assertEqual(self.state("000.png")["material_status"]["key"], "unknown")

    def test_wrong_source_and_missing_inventory_are_unverified(self):
        for changes in ({"source": "other.png"}, {"stage": "extract"}, {"files": None}):
            with self.subTest(changes=changes):
                self.stage(**changes)
                self.assertEqual(self.state("000.png")["material_status"]["key"], "unknown")

    def test_action_and_sequence_edits_do_not_stale_materials(self):
        self.stage()
        self.cfg.data["actions"] = {"idle": {"fps": 24}}
        self.cfg.data["workbench"] = {"reviews": {"sequence": {"slots": []}}}
        self.assertEqual(self.state("000.png")["material_status"]["key"], "synced")


if __name__ == "__main__":
    unittest.main()

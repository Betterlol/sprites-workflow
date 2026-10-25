"""Objective runtime composition checks against synthetic project data."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sprite_pipeline.config import load_config
from sprite_pipeline.files import write_json
from sprite_pipeline.projects import ProjectStore
from sprite_pipeline.projects_cli import main as manage


class CompositionCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspaces = self.root / "workspaces"
        ProjectStore(self.workspaces).create("Composition", "fish", frame_size=[16, 16])
        cfg = load_config(self.workspaces / "fish/pipeline.json")
        refs = [f"pose/{index:03d}.png" for index in range(4)]
        directory = cfg.directory("processed_sprites") / "pose"
        directory.mkdir(parents=True)
        for index in range(4):
            Image.new("RGBA", cfg.size, (index * 50, 0, 0, 255)).save(directory / f"{index:03d}.png")
        cfg.data["actions"] = {
            "part_a": {"sprites": refs[:3], "fps": 10},
            "part_b": {"sprites": refs[2:], "fps": 10},
            "full": {"sprites": refs, "fps": 10},
        }
        cfg.data["workbench"]["reviews"] = {
            "parts": {"mode": "runtime", "loop": False, "clips": [
                {"action": "part_a", "start": 0, "end": 2, "repeat": 1},
                {"action": "part_b", "start": 1, "end": 1, "repeat": 1},
            ]},
            "with_hold": {"mode": "runtime", "loop": False, "clips": [
                {"action": "part_a", "start": 0, "end": 2, "repeat": 1},
                {"action": "part_b", "start": 0, "end": 1, "repeat": 1},
            ]},
        }
        write_json(cfg.path, cfg.data)
        self.cfg = load_config(cfg.path)
        self.refs = refs

    def test_matching_review_reports_exact_runtime_steps_and_boundary(self):
        from sprite_pipeline.composition_check import compare_composition
        result = compare_composition(self.cfg, "full", review="parts")
        self.assertTrue(result["valid"])
        self.assertEqual(result["full_steps"], 4)
        self.assertEqual(result["composition_steps"], 4)
        self.assertEqual(result["full_duration_ms"], 400)
        self.assertIsNone(result["first_mismatch"])
        self.assertEqual(result["boundaries"], [{"slot": 3, "clip": 1,
            "previous_ref": "pose/002.png", "next_ref": "pose/003.png", "same_ref": False}])

    def test_duplicate_shared_endpoint_is_reported_not_removed(self):
        from sprite_pipeline.composition_check import compare_composition
        result = compare_composition(self.cfg, "full", review="with_hold")
        self.assertFalse(result["valid"])
        self.assertEqual(result["composition_steps"], 5)
        self.assertEqual(result["first_mismatch"]["slot"], 3)
        self.assertEqual(result["first_mismatch"]["full"], {"ref": "pose/003.png", "duration_ms": 100})
        self.assertEqual(result["first_mismatch"]["composition"], {"ref": "pose/002.png", "duration_ms": 100})
        self.assertTrue(result["boundaries"][0]["same_ref"])

    def test_sequence_and_duration_mismatch_can_be_checked_without_saved_review(self):
        from sprite_pipeline.composition_check import compare_composition
        sequence = {"steps": [{"ref": ref, "duration_ms": 100} for ref in self.refs]}
        self.assertTrue(compare_composition(self.cfg, "full", sequence=sequence)["valid"])
        sequence["steps"][2]["duration_ms"] = 200
        result = compare_composition(self.cfg, "full", sequence=sequence)
        self.assertFalse(result["valid"])
        self.assertEqual(result["first_mismatch"]["slot"], 2)
        self.assertEqual(result["first_mismatch"]["composition"]["duration_ms"], 200)

    def test_cli_returns_json_and_failure_status_without_writing_project(self):
        saved = self.cfg.path.read_bytes()
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = manage(["--workspace-root", str(self.workspaces), "--json",
                               "check-composition", "fish", "--action", "full", "--review", "with_hold"])
            except SystemExit as error:
                code = error.code
        self.assertEqual(code, 1, stderr.getvalue())
        self.assertFalse(json.loads(stdout.getvalue())["valid"])
        self.assertEqual(self.cfg.path.read_bytes(), saved)

    def test_display_review_and_missing_processed_ref_are_rejected(self):
        from sprite_pipeline.composition_check import compare_composition
        self.cfg.data["workbench"]["reviews"]["parts"]["mode"] = "display"
        with self.assertRaises(ValueError):
            compare_composition(self.cfg, "full", review="parts")
        self.cfg = load_config(self.cfg.path)
        (self.cfg.directory("processed_sprites") / self.refs[0]).unlink()
        with self.assertRaises(FileNotFoundError):
            compare_composition(self.cfg, "full", review="parts")

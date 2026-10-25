"""Compact inspection of saved processed sprites using temporary artwork."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sprite_pipeline.config import load_config
from sprite_pipeline.files import write_json
from sprite_pipeline.projects import ProjectStore
from sprite_pipeline.projects_cli import main as manage


class QaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspaces = self.root / "workspaces"
        ProjectStore(self.workspaces).create("QA", "fish", frame_size=[16, 16])
        self.cfg = load_config(self.workspaces / "fish/pipeline.json")
        self.cfg.data["actions"]["walk"] = {
            "sprites": ["walk/000.png", "walk/001.png", "walk/002.png"], "fps": 10,
            "loop": False,
            "animation": {"order": [1, 0, 1, 2], "durations_ms": [40, 80, 50, 100], "loop": 1},
        }
        self.cfg.data["workbench"]["reviews"]["walk_twice"] = {
            "name": "Walk twice", "mode": "runtime", "loop": False,
            "clips": [{"action": "walk", "start": 0, "end": 2, "repeat": 2}],
        }
        write_json(self.cfg.path, self.cfg.data)
        self.cfg = load_config(self.cfg.path)
        directory = self.cfg.directory("processed_sprites") / "walk"
        directory.mkdir(parents=True)
        for index, color in enumerate(("red", "green", "blue")):
            frame = Image.new("RGBA", self.cfg.size, (0, 0, 0, 0))
            frame.paste(color, (index * 4, 4, index * 4 + 4, 8))
            frame.save(directory / f"{index:03d}.png")

    def render(self, **kwargs):
        from sprite_pipeline.qa import render_qa
        return render_qa(self.cfg, **kwargs)

    def test_action_modes_write_playback_artifacts_and_exact_slot_report(self):
        saved = self.cfg.path.read_bytes()
        runtime = self.root / "runtime"
        result = self.render(action="walk", output=runtime)
        report = json.loads((runtime / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result["steps"], 3)
        self.assertEqual(report["mode"], "runtime")
        self.assertEqual([s["duration_ms"] for s in report["steps"]], [100] * 3)
        self.assertEqual([s["start_ms"] for s in report["steps"]], [0, 100, 200])
        self.assertEqual([s["ref"] for s in report["steps"]], self.cfg.data["actions"]["walk"]["sprites"])
        self.assertEqual(report["duration_ms"], 300)
        self.assertEqual(len(report["sprite_sha256"]), 3)
        self.assertEqual(len(report["config_sha256"]), 64)
        self.assertTrue((runtime / "preview.webp").is_file())
        self.assertTrue((runtime / "preview.gif").is_file())
        self.assertEqual(result["contacts"], ["contact-001.png"])
        with Image.open(runtime / "contact-001.png") as contact:
            self.assertEqual(contact.width, 1080)
            red, green, blue = contact.getpixel((20, 85))
            self.assertGreater(red, 220)
            self.assertLess(green + blue, 100)
        with Image.open(runtime / "preview.webp") as webp:
            self.assertEqual(webp.n_frames, 3)
            self.assertEqual(webp.info["loop"], 1)
        with Image.open(runtime / "preview.gif") as gif:
            self.assertEqual(gif.n_frames, 3)
            self.assertNotIn("loop", gif.info)

        display = self.root / "display"
        self.render(action="walk", mode="display", output=display)
        report = json.loads((display / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["mode"], "display")
        self.assertEqual([s["ref"] for s in report["steps"]], [
            "walk/001.png", "walk/000.png", "walk/001.png", "walk/002.png",
        ])
        self.assertEqual([s["duration_ms"] for s in report["steps"]], [40, 80, 50, 100])
        self.assertEqual(report["duration_ms"], 270)
        self.assertEqual(self.cfg.path.read_bytes(), saved)
        self.assertFalse((self.cfg.root / "exports").exists())

    def test_review_and_raw_references_preserve_repeats_and_paginate(self):
        review = self.root / "review"
        self.render(review="walk_twice", output=review)
        report = json.loads((review / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["source"], {"review": "walk_twice"})
        self.assertEqual(len(report["steps"]), 6)
        self.assertEqual(report["duration_ms"], 600)
        self.assertEqual([step["repetition"] for step in report["steps"]], [0, 0, 0, 1, 1, 1])

        raw = self.root / "raw"
        refs = ["walk/000.png", "walk/001.png"] * 19
        result = self.render(references=refs, output=raw)
        report = json.loads((raw / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result["contacts"], ["contact-001.png", "contact-002.png"])
        self.assertEqual(len(report["steps"]), 38)
        self.assertEqual(report["steps"][36]["slot"], 36)
        self.assertEqual(report["steps"][36]["ref"], "walk/000.png")
        self.assertEqual(len(report["sprite_sha256"]), 2)

    def test_invalid_input_and_existing_destination_leave_files_untouched(self):
        saved = self.cfg.path.read_bytes()
        destination = self.root / "missing"
        with self.assertRaises(ValueError):
            self.render(action="walk", references=["walk/000.png"], output=destination)
        with self.assertRaises(ValueError):
            self.render(references=["../outside.png"], output=destination)
        with self.assertRaises(FileNotFoundError):
            self.render(references=["walk/missing.png"], output=destination)
        self.assertFalse(destination.exists())
        existing = self.root / "existing"
        existing.mkdir()
        marker = existing / "keep.txt"
        marker.write_text("human", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.render(action="walk", output=existing)
        with self.assertRaises(ValueError):
            self.render(action="walk", output=self.cfg.directory("processed_sprites") / "qa")
        self.cfg.data["actions"]["walk"]["animation"]["durations_ms"] = [700_000] * 4
        write_json(self.cfg.path, self.cfg.data)
        self.cfg = load_config(self.cfg.path)
        saved = self.cfg.path.read_bytes()
        with self.assertRaises(ValueError):
            self.render(action="walk", mode="display", output=self.root / "failed-encode")
        self.assertFalse((self.root / "failed-encode").exists())
        self.assertEqual(list(self.root.glob(".sprite-qa-*")), [])
        self.assertEqual(marker.read_text(encoding="utf-8"), "human")
        self.assertEqual(self.cfg.path.read_bytes(), saved)

    def test_report_hashes_the_same_sprite_bytes_as_preview(self):
        import sprite_pipeline.qa as qa
        path = self.cfg.directory("processed_sprites") / "walk/000.png"
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        original_open = Image.open
        changed = False

        def change_during_decode(source, *args, **kwargs):
            nonlocal changed
            image = original_open(source, *args, **kwargs)
            if not changed:
                image.load()
                Image.new("RGBA", self.cfg.size, "purple").save(path)
                changed = True
            return image

        output = self.root / "same-bytes"
        with patch.object(Image, "open", change_during_decode):
            qa.render_qa(self.cfg, references=["walk/000.png"], output=output)
        self.assertTrue(changed)
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["sprite_sha256"]["walk/000.png"], expected)
        with Image.open(output / "preview.webp") as preview:
            self.assertEqual(preview.convert("RGBA").getpixel((1, 5))[:3], (255, 0, 0))

    def test_stale_loaded_config_does_not_publish_misleading_revision(self):
        changed = json.loads(self.cfg.path.read_text(encoding="utf-8"))
        changed["actions"]["walk"]["sprites"].reverse()
        write_json(self.cfg.path, changed)
        output = self.root / "stale"
        with self.assertRaisesRegex(ValueError, "changed"):
            self.render(action="walk", output=output)
        self.assertFalse(output.exists())

    def test_competing_output_created_at_publish_time_is_preserved(self):
        output = self.root / "competing"
        if os.name == "nt":
            original_rename = Path.rename

            def create_competitor(path, destination):
                if destination == output:
                    output.mkdir()
                    (output / "keep.txt").write_text("human", encoding="utf-8")
                return original_rename(path, destination)

            with patch.object(Path, "rename", create_competitor):
                with self.assertRaises(FileExistsError):
                    self.render(action="walk", output=output)
        else:
            original_mkdir = Path.mkdir

            def create_competitor(path, *args, **kwargs):
                if path == output:
                    original_mkdir(path)
                    (path / "keep.txt").write_text("human", encoding="utf-8")
                return original_mkdir(path, *args, **kwargs)

            with patch.object(Path, "mkdir", create_competitor):
                with self.assertRaises(FileExistsError):
                    self.render(action="walk", output=output)
        self.assertEqual((output / "keep.txt").read_text(encoding="utf-8"), "human")

    def test_final_output_is_not_visible_while_artifacts_are_written(self):
        output = self.root / "atomic"
        original_open = Path.open

        def check_open(path, *args, **kwargs):
            if path.is_relative_to(output):
                self.assertFalse(output.exists(), "Final QA directory became visible before writing finished")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", check_open):
            self.render(action="walk", output=output)
        self.assertTrue((output / "report.json").exists())

    def test_contact_ground_line_uses_scaled_non_square_canvas(self):
        from sprite_pipeline.qa import render_qa
        ProjectStore(self.workspaces).create("Wide", "wide", frame_size=[200, 100])
        wide = load_config(self.workspaces / "wide/pipeline.json")
        frame = wide.directory("processed_sprites") / "wide.png"
        Image.new("RGBA", wide.size, (0, 0, 0, 0)).save(frame)
        output = self.root / "wide-qa"
        render_qa(wide, references=["wide.png"], output=output)
        with Image.open(output / "contact-001.png") as contact:
            # 200×100 fits at 160×80, centered 40 px below the thumbnail top.
            expected_y = 27 + 40 + round(90 * 80 / 100)
            self.assertEqual(contact.getpixel((12, expected_y)), (201, 89, 89))

    def test_cli_can_create_qa_report_for_agent(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        output = self.root / "cli"
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = manage(["--workspace-root", str(self.workspaces), "--json", "qa", "fish",
                               "--action", "walk", "--output", str(output)])
            except SystemExit as error:
                code = error.code
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())["steps"], 3)
        self.assertTrue((output / "report.json").exists())

    def test_explicit_sequence_controls_timing_without_modifying_actions(self):
        saved = self.cfg.path.read_bytes()
        sequence = {"loop": 2, "steps": [
            {"ref": "walk/002.png", "duration_ms": 60},
            {"ref": "walk/000.png", "duration_ms": 140},
            {"ref": "walk/002.png", "duration_ms": 80},
        ]}
        manifest = self.root / "sequence.json"
        manifest.write_text(json.dumps(sequence), encoding="utf-8")
        output = self.root / "sequence-qa"
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = manage(["--workspace-root", str(self.workspaces), "--json", "qa", "fish",
                               "--sequence", str(manifest), "--output", str(output)])
            except SystemExit as error:
                code = error.code
        self.assertEqual(code, 0, stderr.getvalue())
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["mode"], "sequence")
        self.assertEqual(report["loop"], 2)
        self.assertEqual([step["duration_ms"] for step in report["steps"]], [60, 140, 80])
        self.assertEqual([step["ref"] for step in report["steps"]],
                         ["walk/002.png", "walk/000.png", "walk/002.png"])
        self.assertEqual(report["duration_ms"], 280)
        with Image.open(output / "preview.gif") as gif:
            self.assertEqual(gif.info["loop"], 1)
        self.assertEqual(self.cfg.path.read_bytes(), saved)

    def test_invalid_explicit_sequence_is_rejected_before_output(self):
        from sprite_pipeline.qa import render_qa
        invalid = [
            {"loop": True, "steps": [{"ref": "walk/000.png", "duration_ms": 100}]},
            {"loop": 1, "steps": []},
            {"loop": 1, "steps": [{"ref": "../outside.png", "duration_ms": 100}]},
            {"loop": 1, "steps": [{"ref": "walk/000.png", "duration_ms": 0}]},
        ]
        for index, sequence in enumerate(invalid):
            with self.subTest(sequence=sequence):
                output = self.root / f"invalid-sequence-{index}"
                with self.assertRaises(ValueError):
                    render_qa(self.cfg, sequence=sequence, output=output)
                self.assertFalse(output.exists())

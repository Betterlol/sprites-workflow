"""Action filters exercise real CLI exports using temporary synthetic artwork."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sprite_pipeline.cli import main as build
from sprite_pipeline.config import load_config
from sprite_pipeline.extract import extract_source
from sprite_pipeline.files import write_json
from sprite_pipeline.process import process_source
from sprite_pipeline.projects import ProjectStore
from sprite_pipeline.projects_cli import main as manage


class CliActionFilterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspaces = self.root / "workspaces"
        ProjectStore(self.workspaces).create("CLI filters", "fish", frame_size=[16, 16])
        self.config_path = self.workspaces / "fish/pipeline.json"
        cfg = load_config(self.config_path)
        Image.new("RGBA", (16, 16), "red").save(cfg.source / "pose.png")
        cfg.data["defaults"]["process"] = {"mode": "copy"}
        cfg.data["sources"] = {"pose.png": {"extract": {"method": "image"}}}
        cfg.data["actions"] = {
            name: {"sprites": ["pose/000.png"], "fps": 8}
            for name in ("idle", "run", "legacy", "debug")
        }
        write_json(cfg.path, cfg.data)
        self.cfg = load_config(self.config_path)
        extract_source(self.cfg, "pose.png")
        process_source(self.cfg, "pose.png")
        self.original_config = self.config_path.read_bytes()

    def invoke(self, main, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                status = main(arguments)
            except SystemExit as error:
                status = error.code
        return status, stdout.getvalue(), stderr.getvalue()

    def export(self, output, *filters, format="all"):
        return self.invoke(manage, [
            "--workspace-root", str(self.workspaces), "--json", "export", "fish",
            "--format", format, "--output", str(output), *filters,
        ])

    def stage(self, stage, *filters):
        return self.invoke(lambda args: build(argv=args), [
            stage, "--config", str(self.config_path), *filters,
        ])

    def archived_actions(self, names):
        return {
            action for action in self.cfg.data["actions"]
            if any(name.startswith(f"sprites/{action}/") or name in {
                f"spritesheets/fish_{action}.png", f"webp/fish_{action}.webp", f"gif/fish_{action}.gif",
                f"metadata/fish_{action}.json",
            } for name in names)
        }

    def test_project_export_excludes_repeated_actions_in_all_resource_formats(self):
        for format in ("frames", "atlas", "webp", "gif", "all"):
            with self.subTest(format=format):
                output = self.root / f"{format}.zip"
                status, _, error = self.export(
                    output, "--exclude-action", "legacy", "--exclude-action", "debug",
                    "--exclude-action", "legacy", format=format,
                )
                self.assertEqual(status, 0, error)
                with zipfile.ZipFile(output) as archive:
                    self.assertEqual(self.archived_actions(archive.namelist()), {"idle", "run"})
                self.assertEqual(self.config_path.read_bytes(), self.original_config)

    def test_project_export_applies_exclusion_after_explicit_inclusion(self):
        output = self.root / "included.zip"
        status, _, error = self.export(
            output, "--action", "run", "--action", "legacy", "--action", "run",
            "--action", "idle", "--exclude-action", "legacy", format="frames",
        )
        self.assertEqual(status, 0, error)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(self.archived_actions(archive.namelist()), {"idle", "run"})

    def test_project_export_rejects_unknown_and_empty_filters_before_writing(self):
        filters = (
            ("--exclude-action", "missing"),
            ("--action", "missing", "--exclude-action", "legacy"),
            ("--action", "idle", "--exclude-action", "idle"),
            tuple(part for name in self.cfg.data["actions"] for part in ("--exclude-action", name)),
        )
        for index, arguments in enumerate(filters):
            with self.subTest(arguments=arguments):
                output = self.root / "rejected" / f"{index}.zip"
                status, _, error = self.export(output, *arguments)
                self.assertEqual(status, 1, error)
                self.assertTrue(json.loads(error)["error"])
                self.assertFalse(output.parent.exists())
        self.assertEqual(self.config_path.read_bytes(), self.original_config)

    def test_project_backup_rejects_action_exclusion(self):
        output = self.root / "backup.zip"
        status, _, error = self.export(output, "--exclude-action", "legacy", format="project")
        self.assertEqual(status, 1, error)
        self.assertIn("project", json.loads(error)["error"])
        self.assertFalse(output.exists())

    def test_stage_cli_excludes_actions_from_select_pack_and_preview(self):
        for stage in ("select", "pack", "preview"):
            status, _, error = self.stage(stage, "--exclude-action", "legacy", "--exclude-action", "debug")
            self.assertEqual(status, 0, error)
        self.assertEqual({p.name for p in self.cfg.directory("sprites").iterdir()}, {"idle", "run"})
        self.assertEqual({p.name for p in self.cfg.directory("spritesheets").glob("*.png")},
                         {"fish_idle.png", "fish_run.png"})
        self.assertEqual({p.name for p in self.cfg.directory("webp").glob("*.webp")},
                         {"fish_idle.webp", "fish_run.webp"})
        self.assertEqual(self.config_path.read_bytes(), self.original_config)

    def test_build_cli_excludes_actions_and_still_prepares_sources(self):
        Image.new("RGBA", (16, 16), "blue").save(self.cfg.source / "debug_only.png")
        self.cfg.data["sources"]["debug_only.png"] = {"extract": {"method": "image"}}
        self.cfg.data["actions"]["debug"]["sprites"] = ["debug_only/000.png"]
        write_json(self.config_path, self.cfg.data)
        status, _, error = self.stage("build", "--exclude-action", "legacy", "--exclude-action", "debug")
        self.assertEqual(status, 0, error)
        self.assertEqual({p.name for p in self.cfg.directory("sprites").iterdir()}, {"idle", "run"})
        self.assertTrue((self.cfg.directory("source_sprites") / "pose/000.png").is_file())
        self.assertTrue((self.cfg.directory("processed_sprites") / "pose/000.png").is_file())
        self.assertTrue((self.cfg.directory("processed_sprites") / "debug_only/000.png").is_file())

    def test_stage_cli_combines_includes_and_excludes_in_requested_order(self):
        status, stdout, error = self.stage(
            "select", "--action", "run", "--action", "idle", "--action", "run",
            "--action", "legacy", "--exclude-action", "legacy",
        )
        self.assertEqual(status, 0, error)
        self.assertEqual(stdout.splitlines(), ["select: run (1 frames)", "select: idle (1 frames)"])

    def test_stage_cli_rejects_invalid_filters_without_creating_outputs(self):
        cases = (
            ("extract", "--exclude-action", "legacy"),
            ("process", "--exclude-action", "legacy"),
            ("select", "--exclude-action", "missing"),
            ("select", "--action", "missing", "--exclude-action", "legacy"),
            ("select", "--action", "idle", "--exclude-action", "idle"),
            ("select", *(part for name in self.cfg.data["actions"] for part in ("--exclude-action", name))),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                status, _, error = self.stage(*arguments)
                self.assertEqual(status, 1, error)
                self.assertTrue(error)
                self.assertFalse(self.cfg.directory("sprites").exists())
        self.assertEqual(self.config_path.read_bytes(), self.original_config)


if __name__ == "__main__":
    unittest.main()

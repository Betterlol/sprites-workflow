"""Project isolation and the complete human/agent workflow use temporary artwork."""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sprite_pipeline.cli import main as build
from sprite_pipeline.config import load_config
from sprite_pipeline.files import write_json
from sprite_pipeline.extract import extract_source
from sprite_pipeline.locking import project_lock
from sprite_pipeline.projects import ProjectStore
from sprite_pipeline.projects_cli import main as manage
from sprite_pipeline.workbench import ExportCancelled, Project, png_bytes

try:
    from fastapi.testclient import TestClient
    from sprite_pipeline.server import create_app
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "Install workbench requirements and httpx")
class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "workspaces"
        self.store = ProjectStore(self.root)
        self.client = TestClient(create_app(workspace_root=self.root))
        self.addCleanup(self.client.close)
        self.token = self.client.get("/api/projects").json()["token"]
        self.headers = {"x-workbench-token": self.token}

    def create(self, project_id="fish", name="大肥鱼"):
        response = self.client.post("/api/projects", json={"id": project_id, "name": name, "frame_size": [32, 32]}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return self.snapshot(project_id)

    def snapshot(self, project_id="fish"):
        response = self.client.get(f"/api/projects/{project_id}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def post(self, operation, snapshot, project_id="fish", **extra):
        return self.client.post(f"/api/projects/{project_id}/{operation}", headers=self.headers,
                                json={"data": snapshot["data"], "revision": snapshot["revision"],
                                      "asset_revision": snapshot["asset_revision"], **extra})

    def import_image(self, snapshot, project_id="fish", kind="source", filename="pose.png", color="red"):
        return self.post("upload", snapshot, project_id, kind=kind, filename=filename,
                         content=base64.b64encode(png_bytes(Image.new("RGBA", (32, 32) if kind == "processed" else (16, 16), color))).decode())

    def test_empty_install_and_first_source_import(self):
        self.assertFalse(self.root.exists())
        snapshot = self.create()
        self.assertEqual(snapshot["sources"], [])
        self.assertEqual(snapshot["assets"], [])
        self.assertEqual(snapshot["project"]["name"], "大肥鱼")
        for directory in ("source", "source_sprites", "processed_sprites", "references"):
            self.assertTrue((self.root / "fish" / directory).is_dir())
        response = self.import_image(snapshot)
        self.assertEqual(response.status_code, 200, response.text)
        response = self.post("apply", response.json(), source="pose.png")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["assets"]), 1)
        self.assertFalse((self.root / "fish" / "exports").exists())

    def test_upload_exclusive_create_race_preserves_external_file(self):
        snapshot = self.create()
        destination = self.root / "fish/source/pose.png"
        external = png_bytes(Image.new("RGBA", (16, 16), "blue"))
        original_open = Path.open

        def race_open(path, mode="r", *args, **kwargs):
            if path == destination and mode == "xb":
                destination.write_bytes(external)
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", race_open):
            response = self.import_image(snapshot)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(destination.read_bytes(), external)
        self.assertEqual(self.client.get("/api/projects/fish/history").json()["versions"], [])

    def test_processed_only_project_and_portable_backup_keep_reference_material(self):
        snapshot = self.create()
        response = self.import_image(snapshot, kind="processed")
        self.assertEqual(response.status_code, 200, response.text)
        snapshot = response.json()
        (self.root / "fish/reference").mkdir()
        (self.root / "fish/reference/character.txt").write_text("角色约束", encoding="utf-8")
        snapshot["data"]["actions"] = {"idle": {"sprites": ["imports/pose.png"], "fps": 8}}
        response = self.post("export", snapshot, options={"format": "project"})
        self.assertEqual(response.status_code, 200, response.text[:100])
        restored = self.root / "restored"
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertIn("reference/character.txt", archive.namelist())
            self.assertIn("README.md", archive.namelist())
            archive.extractall(restored)
        reopened = self.store.get("restored").state()
        self.assertEqual(len(reopened["assets"]), 1)
        self.assertEqual(reopened["sources"], [])
        self.assertEqual(reopened["data"]["actions"]["idle"]["sprites"], ["imports/pose.png"])

    def test_two_tabs_and_image_urls_remain_project_scoped(self):
        a = self.create("a")
        b = self.create("b", "另一角色")
        a = self.import_image(a, "a", kind="processed", color="red").json()
        b = self.import_image(b, "b", kind="processed", color="blue").json()
        for project_id, snapshot, expected in (("a", a, (255, 0, 0, 255)), ("b", b, (0, 0, 255, 255))):
            url = snapshot["assets"][0]["url"]
            self.assertIn(f"/projects/{project_id}/image", url)
            image = Image.open(io.BytesIO(self.client.get(url).content))
            self.assertEqual(image.getpixel((0, 0)), expected)
            snapshot["data"]["notes"] = [project_id]
            self.assertEqual(self.post("save", snapshot, project_id).status_code, 200)
        self.assertEqual(self.snapshot("a")["data"]["notes"], ["a"])
        self.assertEqual(self.snapshot("b")["data"]["notes"], ["b"])
        self.assertEqual(self.client.get("/api/project").status_code, 400)

    def test_versioned_images_are_cacheable_without_revalidating_unchanged_config(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="processed").json()
        url = snapshot["assets"][0]["url"]
        with patch("sprite_pipeline.projects.load_config", wraps=load_config) as store_load, \
             patch("sprite_pipeline.workbench.load_config", wraps=load_config) as image_load:
            first = self.client.get(url)
            loads_after_first = store_load.call_count + image_load.call_count
            second = self.client.get(url)
            self.assertEqual(store_load.call_count + image_load.call_count, loads_after_first)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.content, first.content)
        self.assertIn("immutable", first.headers["cache-control"])
        self.assertEqual(self.client.get("/api/projects/fish/changes").headers["cache-control"], "no-store")
        self.assertEqual(self.client.get("/static/app.js").headers["cache-control"], "private, no-cache")

        image_path = self.root / "fish/processed_sprites/imports/pose.png"
        original_stat = image_path.stat()
        Image.new("RGBA", (32, 32), "blue").save(image_path)
        os.utime(image_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1000000))
        stale = self.client.get(url)
        self.assertEqual(stale.headers["cache-control"], "no-store")
        self.assertEqual(Image.open(io.BytesIO(stale.content)).getpixel((0, 0)), (0, 0, 255, 255))
        fresh_url = self.snapshot()["assets"][0]["url"]
        self.assertNotEqual(fresh_url, url)
        self.assertIn("immutable", self.client.get(fresh_url).headers["cache-control"])

    def test_image_paths_refresh_after_external_config_change(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="processed").json()
        url = snapshot["assets"][0]["url"]
        self.assertEqual(self.client.get(url).status_code, 200)
        config_path = self.root / "fish/pipeline.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["paths"]["processed_sprites"] = "other_processed"
        write_json(config_path, data)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get("/api/projects/fish/image", params={"kind": "processed", "ref": "../source/pose.png"}).status_code, 400)
        data["paths"]["source"] = "../outside"
        write_json(config_path, data)
        self.assertEqual(self.client.get(url).status_code, 400)

    def test_snapshot_reuses_unchanged_processed_metadata_and_refreshes_changed_bbox(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="processed").json()
        self.assertEqual(snapshot["assets"][0]["bbox"], [0, 0, 32, 32])
        image_path = self.root / "fish/processed_sprites/imports/pose.png"
        image_open = Image.open

        def reject_redecode(path, *args, **kwargs):
            if Path(path) == image_path:
                raise AssertionError("unchanged processed image was decoded again")
            return image_open(path, *args, **kwargs)

        with patch("sprite_pipeline.workbench.Image.open", side_effect=reject_redecode):
            self.assertEqual(self.snapshot()["assets"][0]["bbox"], [0, 0, 32, 32])

        old_stat = image_path.stat()
        changed = Image.new("RGBA", (32, 32))
        changed.paste("blue", (4, 5, 12, 14))
        changed.save(image_path)
        os.utime(image_path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1000000))
        self.assertEqual(self.snapshot()["assets"][0]["bbox"], [4, 5, 12, 14])

    def test_image_operations_create_restorable_history_without_copying_unrelated_art(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="source", filename="walk.png").json()
        before_apply = snapshot["revision"]
        applied = self.post("apply", snapshot, source="walk.png").json()
        processed = self.root / "fish/processed_sprites/walk/000.png"
        self.assertTrue(processed.is_file())
        history = self.client.get("/api/projects/fish/history")
        self.assertEqual(history.status_code, 200, history.text)
        versions = history.json()["versions"]
        self.assertEqual(versions[0]["operation"], "apply")
        self.assertEqual(versions[1]["operation"], "upload source")
        restored = self.post("restore", applied, version=versions[0]["id"])
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertFalse(processed.exists())
        self.assertEqual(restored.json()["revision"], before_apply)
        self.assertEqual(restored.json()["sources"][0]["file"], "walk.png")
        redo = self.client.get("/api/projects/fish/history").json()["versions"][0]
        self.assertEqual(redo["operation"], "restore")
        self.assertEqual(self.post("restore", restored.json(), version=redo["id"]).status_code, 200)
        self.assertTrue(processed.is_file())

    def test_deleted_manual_sprite_can_be_restored_but_external_edits_block_restore(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="processed", filename="manual.png", color="red").json()
        manual = self.root / "fish/processed_sprites/imports/manual.png"
        original = manual.read_bytes()
        deleted = self.post("delete", snapshot, kind="processed", references=["imports/manual.png"]).json()
        self.assertFalse(manual.exists())
        history = self.client.get("/api/projects/fish/history")
        self.assertEqual(history.status_code, 200, history.text)
        version = history.json()["versions"][0]
        self.assertEqual(version["operation"], "delete processed")
        manual.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (32, 32), "blue").save(manual)
        self.assertEqual(self.post("restore", deleted, version=version["id"]).status_code, 409)
        manual.unlink()
        fresh = self.snapshot()
        restored = self.post("restore", fresh, version=version["id"])
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(manual.read_bytes(), original)

    def test_failed_apply_restores_prior_pixels_and_does_not_record_version(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="source", filename="walk.png").json()
        snapshot = self.post("apply", snapshot, source="walk.png").json()
        processed = self.root / "fish/processed_sprites/walk/000.png"
        original = processed.read_bytes()
        history = self.client.get("/api/projects/fish/history")
        self.assertEqual(history.status_code, 200, history.text)
        prior_versions = history.json()["versions"]
        snapshot["data"]["sources"]["walk.png"]["process"] = {"offset": [1, 0]}
        with patch("sprite_pipeline.workbench.write_json", side_effect=OSError("config write failed")):
            with self.assertRaisesRegex(OSError, "config write failed"):
                self.store.get("fish").apply(snapshot["data"], snapshot["revision"], "walk.png", snapshot["asset_revision"])
        self.assertEqual(processed.read_bytes(), original)
        self.assertEqual(self.client.get("/api/projects/fish/history").json()["versions"], prior_versions)

    def test_prepared_source_and_approved_migration_are_recoverable(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="source", filename="walk.png").json()
        prepared = self.post("prepare", snapshot).json()
        version = self.client.get("/api/projects/fish/history").json()["versions"][0]
        self.assertEqual(version["operation"], "prepare")
        self.assertTrue((self.root / "fish/processed_sprites/walk/000.png").exists())
        restored = self.post("restore", prepared, version=version["id"]).json()
        self.assertFalse((self.root / "fish/processed_sprites/walk/000.png").exists())

        restored = self.import_image(restored, kind="processed", filename="manual.png", color="red").json()
        restored["data"]["actions"]["idle"] = {"sprites": ["imports/manual.png"], "fps": 8}
        self.assertEqual(self.post("save", restored).status_code, 200)
        final = self.root / "fish/exports/frames/idle/idle_00.png"
        final.parent.mkdir(parents=True)
        Image.new("RGBA", (32, 32), "blue").save(final)
        snapshot = self.snapshot()
        migrated = self.post("migrate", snapshot)
        self.assertEqual(migrated.status_code, 200, migrated.text)
        new_ref = migrated.json()["data"]["actions"]["idle"]["sprites"][0]
        self.assertTrue(new_ref.startswith("_approved/idle/"))
        version = self.client.get("/api/projects/fish/history").json()["versions"][0]
        self.assertEqual(version["operation"], "migrate")
        restored = self.post("restore", migrated.json(), version=version["id"])
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["data"]["actions"]["idle"]["sprites"], ["imports/manual.png"])
        self.assertFalse((self.root / "fish/processed_sprites" / new_ref).exists())

    def test_deleted_source_restores_original_and_derived_files(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="source", filename="walk.png").json()
        snapshot = self.post("apply", snapshot, source="walk.png").json()
        source = self.root / "fish/source/walk.png"
        processed = self.root / "fish/processed_sprites/walk/000.png"
        source_bytes, processed_bytes = source.read_bytes(), processed.read_bytes()
        deleted = self.post("delete", snapshot, kind="source", references=["walk.png"]).json()
        self.assertFalse(source.exists())
        self.assertFalse(processed.exists())
        version = self.client.get("/api/projects/fish/history").json()["versions"][0]
        self.assertEqual(version["operation"], "delete source")
        restored = self.post("restore", deleted, version=version["id"])
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(source.read_bytes(), source_bytes)
        self.assertEqual(processed.read_bytes(), processed_bytes)

    def test_invalid_history_archive_cannot_remove_current_pixels(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="source", filename="walk.png").json()
        applied = self.post("apply", snapshot, source="walk.png").json()
        processed = self.root / "fish/processed_sprites/walk/000.png"
        original = processed.read_bytes()
        version = self.client.get("/api/projects/fish/history").json()["versions"][0]
        archive = self.root / "fish/.sprite-workbench-history/versions" / version["id"] / "before.zip"
        archive.write_bytes(b"broken archive")
        response = self.post("restore", applied, version=version["id"])
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(processed.read_bytes(), original)

    def test_cli_can_list_and_restore_versions_with_shared_guards(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="processed", filename="manual.png").json()
        deleted = self.post("delete", snapshot, kind="processed", references=["imports/manual.png"]).json()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(manage(["--workspace-root", str(self.root), "history", "fish"]), 0)
        version = json.loads(output.getvalue())["versions"][0]["id"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(manage(["--workspace-root", str(self.root), "restore", "fish", version,
                                     "--revision", deleted["revision"], "--asset-revision", deleted["asset_revision"]]), 0)
        self.assertTrue((self.root / "fish/processed_sprites/imports/manual.png").exists())

    def test_export_job_reports_progress_and_downloads_complete_zip(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="processed", filename="pose.png").json()
        snapshot["data"]["actions"]["idle"] = {"sprites": ["imports/pose.png"], "fps": 8}
        response = self.client.post("/api/projects/fish/jobs/export", headers=self.headers,
                                    json={"data": snapshot["data"], "revision": snapshot["revision"],
                                          "asset_revision": snapshot["asset_revision"],
                                          "options": {"format": "frames", "actions": ["idle"]}})
        self.assertEqual(response.status_code, 200, response.text)
        job_id = response.json()["id"]
        for _ in range(100):
            status = self.client.get(f"/api/projects/fish/jobs/{job_id}").json()
            if status["status"] in {"done", "failed", "cancelled"}:
                break
            time.sleep(.02)
        self.assertEqual(status["status"], "done", status)
        self.assertEqual(status["completed"], status["total"])
        download = self.client.get(f"/api/projects/fish/jobs/{job_id}/download")
        self.assertEqual(download.status_code, 200, download.text[:200])
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            self.assertIn("sprites/idle/idle_00.png", archive.namelist())
        self.assertFalse((self.root / "fish/exports").exists())
        self.assertEqual(self.client.get(f"/api/projects/other/jobs/{job_id}").status_code, 404)

    def test_export_job_cancel_is_project_scoped_and_has_no_download(self):
        self.create("fish")
        self.create("other")
        entered, release = threading.Event(), threading.Event()

        def delayed_export(project, data, options, *, progress, cancelled, **kwargs):
            progress(0, 2, "准备动作")
            entered.set()
            release.wait(3)
            if cancelled.is_set():
                raise ExportCancelled()
            return b"unexpected", "unexpected.zip", "application/zip"

        snapshot = self.snapshot("fish")
        with patch.object(Project, "export", delayed_export):
            response = self.client.post("/api/projects/fish/jobs/export", headers=self.headers,
                                        json={"data": snapshot["data"], "revision": snapshot["revision"],
                                              "asset_revision": snapshot["asset_revision"],
                                              "options": {"format": "project"}})
            self.assertEqual(response.status_code, 200, response.text)
            job_id = response.json()["id"]
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.client.get(f"/api/projects/other/jobs/{job_id}").status_code, 404)
            self.assertEqual(self.client.post(f"/api/projects/other/jobs/{job_id}/cancel", headers=self.headers, json={}).status_code, 404)
            self.assertEqual(self.client.get(f"/api/projects/fish/jobs/{job_id}/download").status_code, 409)
            self.assertEqual(self.client.post(f"/api/projects/fish/jobs/{job_id}/cancel", headers=self.headers, json={}).status_code, 200)
            release.set()
            for _ in range(100):
                status = self.client.get(f"/api/projects/fish/jobs/{job_id}").json()
                if status["status"] == "cancelled":
                    break
                time.sleep(.02)
            self.assertEqual(status["status"], "cancelled")
            self.assertEqual(self.client.get(f"/api/projects/fish/jobs/{job_id}/download").status_code, 409)

    def test_prepare_job_reports_source_progress_and_returns_snapshot(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="source", filename="walk.png").json()
        response = self.client.post("/api/projects/fish/jobs/prepare", headers=self.headers,
                                    json={"data": snapshot["data"], "revision": snapshot["revision"],
                                          "asset_revision": snapshot["asset_revision"]})
        self.assertEqual(response.status_code, 200, response.text)
        job_id = response.json()["id"]
        for _ in range(100):
            status = self.client.get(f"/api/projects/fish/jobs/{job_id}").json()
            if status["status"] in {"done", "failed", "cancelled"}:
                break
            time.sleep(.02)
        self.assertEqual(status["status"], "done", status)
        self.assertEqual(status["completed"], status["total"])
        self.assertEqual(len(status["result"]["assets"]),1)
        self.assertTrue((self.root / "fish/processed_sprites/walk/000.png").is_file())

    def test_history_storage_link_cannot_write_outside_project(self):
        snapshot = self.create()
        outside = self.root.parent / "outside-history"
        outside.mkdir()
        history_path = self.root / "fish/.sprite-workbench-history"
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(outside), str(history_path))
            else:
                history_path.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Directory links unavailable: {error}")
        response = self.import_image(snapshot, kind="processed", filename="manual.png")
        self.assertEqual(response.status_code, 400, response.text)
        self.assertFalse(list(outside.iterdir()))
        self.assertFalse((self.root / "fish/processed_sprites/imports/manual.png").exists())

    def test_history_list_does_not_follow_linked_version_directory(self):
        self.create()
        versions = self.root / "fish/.sprite-workbench-history/versions"
        versions.mkdir(parents=True)
        outside = self.root.parent / "outside-version"
        outside.mkdir()
        (outside / "manifest.json").write_text(json.dumps({"id": "00000000000000000001-abcdef12",
                                                        "operation": "outside", "created_at": 1,
                                                        "before": {}, "after": {}}), encoding="utf-8")
        link = versions / "00000000000000000001-abcdef12"
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(outside), str(link))
            else:
                link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Directory links unavailable: {error}")
        response = self.client.get("/api/projects/fish/history")
        self.assertEqual(response.status_code, 400, response.text)

    def test_failed_automatic_rollback_keeps_recovery_archive(self):
        from sprite_pipeline.history import ProjectHistory

        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="source", filename="walk.png").json()
        snapshot = self.post("apply", snapshot, source="walk.png").json()
        snapshot["data"]["sources"]["walk.png"]["process"] = {"offset": [1, 0]}
        with patch("sprite_pipeline.workbench.write_json", side_effect=OSError("config write failed")), \
             patch.object(ProjectHistory, "_restore_archive", side_effect=OSError("rollback failed")):
            with self.assertRaisesRegex(OSError, "backup"):
                self.store.get("fish").apply(snapshot["data"], snapshot["revision"], "walk.png", snapshot["asset_revision"])
        pending = list((self.root / "fish/.sprite-workbench-history/versions").glob(".pending-*"))
        self.assertEqual(len(pending), 1)
        self.assertTrue((pending[0] / "before.zip").is_file())

    def test_unchanged_project_requests_reuse_validation_but_external_edits_refresh(self):
        first = self.create()
        with patch("sprite_pipeline.projects.load_config", side_effect=AssertionError("config was revalidated")):
            repeat = self.snapshot()
            changes = self.client.get("/api/projects/fish/changes")
        self.assertEqual(repeat["revision"], first["revision"])
        self.assertEqual(changes.status_code, 200)
        self.assertEqual(repeat["project"]["name"], "大肥鱼")

        config_path = self.root / "fish/pipeline.json"
        updated = json.loads(config_path.read_text(encoding="utf-8"))
        updated["project"]["name"] = "新名称"
        write_json(config_path, updated)
        self.assertEqual(self.snapshot()["project"]["name"], "新名称")
        updated["paths"]["source"] = "../outside"
        write_json(config_path, updated)
        self.assertEqual(self.client.get("/api/projects/fish").status_code, 400)

    def test_same_stat_external_config_edit_cannot_bypass_workspace_path_validation(self):
        self.create()
        config_path = self.root / "fish/pipeline.json"
        before = config_path.stat()
        original = config_path.read_bytes()
        self.assertIn(b'"source": "source"', original)
        config_path.write_bytes(original.replace(b'"source": "source"', b'"source": "../bad"', 1))
        os.utime(config_path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(config_path.stat().st_size, before.st_size)
        self.assertEqual(config_path.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(self.client.get("/api/projects/fish").status_code, 400)

    def test_cached_project_rejects_source_directory_replaced_by_external_link(self):
        self.create()
        outside = self.root.parent / "outside"
        outside.mkdir()
        Image.new("RGBA", (16, 16), "red").save(outside / "secret.png")
        source = self.root / "fish/source"
        source.rmdir()
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(outside), str(source))
            else:
                source.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Directory links unavailable: {error}")
        self.assertEqual(self.client.get("/api/projects/fish").status_code, 400)
        self.assertEqual(self.client.get("/api/projects/fish/image", params={"kind": "source", "ref": "secret.png"}).status_code, 400)

    def test_revalidated_source_path_is_checked_after_link_replacement(self):
        self.create()
        config_path = self.root / "fish/pipeline.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["paths"]["source"] = "newsource"
        write_json(config_path, data)
        newsource = self.root / "fish/newsource"
        newsource.mkdir()
        self.assertEqual(self.snapshot()["project"]["id"], "fish")

        outside = self.root.parent / "outside"
        outside.mkdir()
        Image.new("RGBA", (16, 16), "red").save(outside / "private.png")
        newsource.rmdir()
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(outside), str(newsource))
            else:
                newsource.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Directory links unavailable: {error}")
        self.assertEqual(self.client.get("/api/projects/fish").status_code, 400)

    def test_workspace_project_state_checks_source_containment_itself(self):
        self.create()
        config_path = self.root / "fish/pipeline.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["paths"]["source"] = "../outside"
        write_json(config_path, data)
        project = Project(config_path, project_id="fish")
        with self.assertRaisesRegex(ValueError, "source 必须位于工程目录内"):
            project.state()

    def test_versioned_image_keeps_its_bytes_if_file_changes_before_response_send(self):
        from starlette.responses import FileResponse, Response

        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="processed", color="red").json()
        url = snapshot["assets"][0]["url"]
        image_path = self.root / "fish/processed_sprites/imports/pose.png"
        replaced = []
        file_call = FileResponse.__call__
        response_call = Response.__call__

        def replace_pixels():
            if not replaced:
                Image.new("RGBA", (32, 32), "blue").save(image_path)
                replaced.append(True)

        async def call_file(response, scope, receive, send):
            replace_pixels()
            return await file_call(response, scope, receive, send)

        async def call_response(response, scope, receive, send):
            if scope["path"].endswith("/image"):
                replace_pixels()
            return await response_call(response, scope, receive, send)

        with patch.object(FileResponse, "__call__", call_file), patch.object(Response, "__call__", call_response):
            result = self.client.get(url)
        self.assertTrue(replaced)
        self.assertIn("immutable", result.headers["cache-control"])
        self.assertEqual(Image.open(io.BytesIO(result.content)).getpixel((0, 0)), (255, 0, 0, 255))

    def test_names_creation_failures_and_isolation(self):
        original = self.create()
        for project_id in ("FISH", "../escape", "CON", "aux.png", "name.", "bad/name", "@config"):
            response = self.client.post("/api/projects", headers=self.headers,
                                        json={"name": "invalid", "id": project_id})
            self.assertIn(response.status_code, (400, 409), (project_id, response.text))
        self.assertEqual(self.snapshot()["revision"], original["revision"])
        self.assertEqual(self.client.post("/api/projects", json={"name": "unauthorized"}).status_code, 403)
        invalid = self.client.post("/api/projects", headers=self.headers,
                                  json={"name": "invalid", "id": "invalid", "frame_size": [0, 32]})
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse((self.root / "invalid").exists())
        self.create("中文工程", "中文工程")
        self.assertEqual(len(self.client.get("/api/projects").json()["projects"]), 2)

    def test_reserved_source_name_fails_without_leaving_files_or_rules(self):
        snapshot = self.create()
        for filename in ("imports.png", "_approved.png"):
            self.assertEqual(self.import_image(snapshot, filename=filename).status_code, 400)
            self.assertFalse((self.root / "fish/source" / filename).exists())
        self.assertEqual(self.snapshot()["revision"], snapshot["revision"])

    def test_external_config_and_material_changes_are_detected_and_protected(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot).json()
        before = snapshot["asset_revision"]
        source = self.root / "fish/source/pose.png"
        old = source.stat()
        Image.new("RGBA", (16, 16), "blue").save(source)
        os.utime(source, ns=(old.st_atime_ns, old.st_mtime_ns + 1000000))
        changes = self.client.get("/api/projects/fish/changes").json()
        self.assertEqual(changes["revision"], snapshot["revision"])
        self.assertNotEqual(changes["asset_revision"], before)
        self.assertEqual(self.post("apply", snapshot, source="pose.png").status_code, 409)
        self.assertEqual(self.post("apply", self.snapshot(), source="pose.png").status_code, 200)
        snapshot = self.snapshot()
        cfg = load_config(self.root / "fish/pipeline.json")
        cfg.data["notes"] = ["Agent update"]
        write_json(cfg.path, cfg.data)
        self.assertEqual(self.post("save", snapshot).status_code, 409)
        self.assertNotEqual(self.client.get("/api/projects/fish/changes").json()["revision"], snapshot["revision"])

    def test_external_source_drop_missing_source_and_invalid_project_do_not_hide_other_projects(self):
        snapshot = self.create()
        Image.new("RGBA", (16, 16), "red").save(self.root / "fish/source/agent.png")
        snapshot = self.snapshot()
        self.assertEqual(snapshot["sources"][0]["file"], "agent.png")
        snapshot["data"]["sources"]["missing.png"] = {}
        self.assertEqual(self.post("save", snapshot).status_code, 200)
        self.assertTrue(self.snapshot()["warnings"])
        other = self.create("other")
        other["data"]["paths"]["source"] = "../fish/source"
        write_json(self.root / "other/pipeline.json", other["data"])
        listing = self.client.get("/api/projects").json()["projects"]
        self.assertTrue(next(p for p in listing if p["id"] == "other")["error"])
        self.assertEqual(self.client.get("/api/projects/other").status_code, 400)
        self.assertEqual(self.snapshot()["project"]["id"], "fish")

    def test_cli_and_browser_share_operations_and_export_layout(self):
        self.create()
        original = self.root.parent / "agent.png"
        Image.new("RGBA", (16, 16), "green").save(original)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(manage(["--workspace-root", str(self.root), "import", "fish", "--kind", "source", "--file", str(original)]), 0)
            self.assertEqual(manage(["--workspace-root", str(self.root), "apply", "fish", "--source", "agent.png"]), 0)
        snapshot = self.snapshot()
        self.assertFalse(snapshot["sources"][0]["stale"])
        snapshot["data"]["actions"] = {"idle": {"sprites": ["agent/000.png"], "fps": 8}}
        draft = self.root.parent / "draft.json"
        write_json(draft, snapshot["data"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(manage(["--workspace-root", str(self.root), "save", "fish", "--data", str(draft), "--revision", snapshot["revision"]]), 0)
            self.assertEqual(build(argv=["select", "--config", str(self.root / "fish/pipeline.json")]), 0)
            self.assertEqual(build(argv=["pack", "--config", str(self.root / "fish/pipeline.json")]), 0)
        manifest_path = self.root / "fish/exports/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for field in ("sheet", "preview"):
            self.assertTrue((manifest_path.parent / manifest["actions"][0][field]).is_file())
        self.assertTrue((self.root / "fish/exports/frames/idle/idle_00.png").is_file())

    def test_cross_process_lock_rejects_competing_writer_and_releases(self):
        self.create()
        config = self.root / "fish/pipeline.json"
        script = (
            "import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; "
            "from sprite_pipeline.locking import project_lock, ProjectBusyError\n"
            "try:\n with project_lock(Path(sys.argv[2])): pass\n"
            "except ProjectBusyError:\n print('busy')\n"
            "else:\n raise SystemExit('writer unexpectedly acquired lock')\n"
        )
        with project_lock(config):
            child = subprocess.run([sys.executable, "-c", script, str(Path(__file__).resolve().parents[1] / "tools"), str(config)],
                                   capture_output=True, text=True, timeout=20)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(child.stdout.strip(), "busy")
        self.assertEqual(self.client.get("/api/projects/fish/changes").status_code, 200)

    def test_explicit_config_can_open_legacy_layout_even_inside_workspace_root(self):
        self.create()
        path = self.root / "fish/pipeline.json"
        cfg = load_config(path)
        cfg.data["paths"]["source"] = "../legacy-sources"
        write_json(path, cfg.data)
        with TestClient(create_app(path, self.root)) as client:
            listing = client.get("/api/projects").json()
            self.assertEqual(listing["initial_project"], "@config")
            self.assertEqual(len(listing["projects"]), 1)
            self.assertEqual(client.get("/api/projects/@config").status_code, 200)

    def test_batch_deletion_protects_used_assets_then_accepts_draft_reference_removal(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="processed", filename="a.png").json()
        snapshot = self.import_image(snapshot, kind="processed", filename="b.png").json()
        snapshot["data"]["actions"] = {"idle": {"sprites": ["imports/a.png"]}}
        self.assertEqual(self.post("save", snapshot).status_code, 200)
        snapshot = self.snapshot()
        before = (self.root / "fish/pipeline.json").read_bytes()
        response = self.post("delete", snapshot, kind="processed", references=["imports/b.png", "imports/a.png"])
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("idle", response.json()["error"])
        self.assertEqual(len(self.snapshot()["assets"]), 2)
        self.assertEqual((self.root / "fish/pipeline.json").read_bytes(), before)
        snapshot["data"]["actions"]["idle"]["sprites"] = None
        response = self.post("delete", snapshot, kind="processed", references=["imports/b.png", "imports/a.png"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["deleted"], 2)
        self.assertEqual(response.json()["assets"], [])
        self.assertIsNone(self.snapshot()["data"]["actions"]["idle"]["sprites"])

    def test_source_deletion_cleans_derived_directories_and_recipe_but_preserves_other_sources(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, filename="a.png").json()
        snapshot = self.import_image(snapshot, filename="b.png").json()
        snapshot = self.post("prepare", snapshot).json()
        cfg = load_config(self.root / "fish/pipeline.json")
        extract_source(cfg, "a.png")
        snapshot["data"]["actions"] = {"idle": {"sprites": ["a/000.png"]}}
        response = self.post("delete", snapshot, kind="source", references=["a.png"])
        self.assertEqual(response.status_code, 400, response.text)
        snapshot["data"]["actions"] = {}
        response = self.post("delete", snapshot, kind="source", references=["a.png"])
        self.assertEqual(response.status_code, 200, response.text)
        for relative in ("source/a.png", "source_sprites/a", "processed_sprites/a"):
            self.assertFalse((self.root / "fish" / relative).exists())
        self.assertTrue((self.root / "fish/source/b.png").is_file())
        self.assertTrue((self.root / "fish/processed_sprites/b/000.png").is_file())
        self.assertNotIn("a.png", response.json()["data"]["sources"])

    def test_invalid_or_stale_deletion_batch_changes_nothing(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="processed", filename="a.png").json()
        for references in (["imports/a.png", "imports/missing.png"], ["../source/a.png"], ["imports/a.png", "imports/A.png"]):
            response = self.post("delete", snapshot, kind="processed", references=references)
            self.assertIn(response.status_code, (400, 404), response.text)
            self.assertTrue((self.root / "fish/processed_sprites/imports/a.png").is_file())
        snapshot = self.import_image(snapshot, kind="processed", filename="b.png").json()
        old_revision = snapshot["asset_revision"]
        snapshot = self.import_image(snapshot, kind="processed", filename="c.png").json()
        snapshot["asset_revision"] = old_revision
        response = self.post("delete", snapshot, kind="processed", references=["imports/a.png"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.snapshot()["assets"]), 3)

    def test_delete_rolls_back_pixels_and_stage_metadata_when_config_write_fails(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot).json()
        snapshot = self.post("prepare", snapshot).json()
        project = self.store.get("fish")
        before = {p.relative_to(project.path.parent): p.read_bytes() for p in project.path.parent.rglob("*") if p.is_file()}
        def failing_write(path, data):
            if path == project.path:
                raise OSError("simulated config write failure")
            write_json(path, data)
        with patch("sprite_pipeline.workbench.write_json", side_effect=failing_write):
            with self.assertRaisesRegex(OSError, "simulated"):
                project.delete("processed", ["pose/000.png"], snapshot["data"], snapshot["revision"], snapshot["asset_revision"])
        after = {p.relative_to(project.path.parent): p.read_bytes() for p in project.path.parent.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_source_deletion_never_treats_a_directory_as_an_image(self):
        snapshot = self.create()
        directory = self.root / "fish/source/folder.png"
        directory.mkdir()
        Image.new("RGBA", (16, 16), "red").save(directory / "child.png")
        snapshot = self.snapshot()
        snapshot["data"]["sources"]["folder.png"] = {}
        self.assertEqual(self.post("save", snapshot).status_code, 200)
        response = self.post("delete", self.snapshot(), kind="source", references=["folder.png"])
        self.assertEqual(response.status_code, 400, response.text)
        self.assertTrue((directory / "child.png").is_file())

    def test_reference_import_view_delete_and_backup_support_both_directory_names(self):
        snapshot = self.create()
        snapshot = self.import_image(snapshot, kind="reference", filename="identity.png").json()
        self.assertEqual(snapshot["sources"], [])
        self.assertEqual(snapshot["assets"], [])
        self.assertEqual(snapshot["references"][0]["ref"], "references/identity.png")
        self.assertEqual(self.client.get(snapshot["references"][0]["url"]).status_code, 200)
        legacy = self.root / "fish/reference"
        legacy.mkdir()
        Image.new("RGBA", (50, 70), "blue").save(legacy / "legacy.png")
        snapshot = self.snapshot()
        self.assertEqual(len(snapshot["references"]), 2)
        response = self.post("export", snapshot, options={"format": "project"})
        self.assertEqual(response.status_code, 200, response.text[:100])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertIn("references/identity.png", archive.namelist())
            self.assertIn("reference/legacy.png", archive.namelist())
        for ref in ("source/pose.png", "references/../pipeline.json", "references/../reference/legacy.png"):
            self.assertEqual(self.post("delete", snapshot, kind="reference", references=[ref]).status_code, 400)
        response = self.post("delete", snapshot, kind="reference", references=["reference/legacy.png"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["references"]), 1)
        self.assertTrue((self.root / "fish/references/identity.png").is_file())

    def test_cli_batch_import_reports_failures_and_continues_and_cli_delete_is_shared(self):
        self.create()
        a, b = self.root.parent / "a.png", self.root.parent / "b.png"
        Image.new("RGBA", (32, 32), "blue").save(a)
        Image.new("RGBA", (32, 32), "red").save(b)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = manage(["--workspace-root", str(self.root), "import", "fish", "--kind", "processed",
                             "--file", str(a), "--file", str(a), "--file", str(b)])
        self.assertEqual(result, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["imported"], ["a.png", "b.png"])
        self.assertEqual(len(result["failed"]), 1)
        with contextlib.redirect_stdout(io.StringIO()):
            result = manage(["--workspace-root", str(self.root), "delete", "fish", "--kind", "processed",
                             "--ref", "imports/a.png", "--ref", "imports/b.png"])
        self.assertEqual(result, 0)
        self.assertEqual(self.snapshot()["assets"], [])


if __name__ == "__main__":
    unittest.main()

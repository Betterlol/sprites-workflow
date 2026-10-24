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
import unittest
import zipfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sprite_pipeline.cli import main as build
from sprite_pipeline.config import load_config
from sprite_pipeline.files import write_json
from sprite_pipeline.locking import project_lock
from sprite_pipeline.projects import ProjectStore
from sprite_pipeline.projects_cli import main as manage
from sprite_pipeline.workbench import Project, png_bytes

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
        for directory in ("source", "source_sprites", "processed_sprites", "reference"):
            self.assertTrue((self.root / "fish" / directory).is_dir())
        response = self.import_image(snapshot)
        self.assertEqual(response.status_code, 200, response.text)
        response = self.post("apply", response.json(), source="pose.png")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["assets"]), 1)
        self.assertFalse((self.root / "fish" / "exports").exists())

    def test_processed_only_project_and_portable_backup_keep_reference_material(self):
        snapshot = self.create()
        response = self.import_image(snapshot, kind="processed")
        self.assertEqual(response.status_code, 200, response.text)
        snapshot = response.json()
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


if __name__ == "__main__":
    unittest.main()

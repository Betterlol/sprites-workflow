"""Editor integration checks use tiny temporary projects, never production artwork."""

from __future__ import annotations

import base64
import copy
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

try:
    from fastapi.testclient import TestClient
    from sprite_pipeline.server import create_app
except ImportError:
    TestClient = None

from sprite_pipeline.config import load_config
from sprite_pipeline.extract import extract_source
from sprite_pipeline.process import process_source
from sprite_pipeline.workbench import Project, action_steps, png_bytes, preserve_slice_ids, review_steps


@unittest.skipIf(TestClient is None, "Install requirements-workbench.txt and httpx for HTTP checks")
class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        sheet = Image.new("RGBA", (24, 8))
        for index, color in enumerate(("red", "green", "blue")):
            sheet.paste(color, (index * 8, 0, index * 8 + 8, 8))
        sheet.save(self.source / "walk.png")
        self.path = self.root / "pipeline.json"
        self.data = {
            "version": 2, "character": "test", "frame_size": [16, 16],
            "anchor": {"x": .5, "y": .875, "pixels": [8, 14]},
            "defaults": {"fps": 16, "process": {"mode": "anchor", "overflow": "error"}},
            "sources": {"walk.png": {"extract": {"method": "grid", "cols": 3, "rows": 1}}},
            "actions": {
                "walk": {"loop": True, "sprites": ["walk/000.png", "walk/001.png", "walk/002.png"]},
                "rest": {"fps": 10, "sprites": ["walk/000.png"]},
            },
            "workbench": {"reviews": {"walk_rest": {"name": "Walk to rest", "mode": "runtime", "loop": True,
                "clips": [{"action": "walk", "repeat": 2, "start": 1, "end": 2}, {"action": "rest", "repeat": 1}]}}},
        }
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        self.app = create_app(self.path)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        snapshot = self.client.get("/api/project").json()
        self.token = snapshot["token"]
        self.revision = snapshot["revision"]

    def post(self, route, **extra):
        return self.client.post("/api/" + route, json={"data": self.data, "revision": self.revision, **extra},
                                headers={"x-workbench-token": self.token})

    def apply(self):
        response = self.post("apply", source="walk.png")
        self.assertEqual(response.status_code, 200, response.text)
        self.revision = response.json()["revision"]
        return response.json()

    def test_editor_shell_and_modules_are_served_locally(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        for name in ("app.js", "model.js", "player.js"):
            response = self.client.get("/static/" + name)
            self.assertEqual(response.status_code, 200)
            self.assertIn("javascript", response.headers["content-type"])
        self.assertEqual(self.client.get("/static/style.css").status_code, 200)

    def test_preview_uses_same_renderer_without_writing_any_stage_or_config(self):
        before = self.path.read_bytes()
        self.data["sources"]["walk.png"]["process"] = {"offset": [1, -2]}
        response = self.post("preview", source="walk.png")
        self.assertEqual(response.status_code, 200, response.text)
        frame = response.json()["frames"][0]
        image = Image.open(io.BytesIO(base64.b64decode(frame["url"].split(",", 1)[1]))).convert("RGBA")
        self.assertEqual(image.getbbox(), (5, 4, 13, 12))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / "source_sprites").exists())
        self.assertFalse((self.root / "processed_sprites").exists())

    def test_apply_persists_recipe_and_only_processed_images(self):
        snapshot = self.apply()
        self.assertEqual(len(snapshot["assets"]), 3)
        self.assertEqual(len(snapshot["sources"]), 1)
        self.assertFalse((self.root / "source_sprites").exists())
        self.assertFalse((self.root / "sprites").exists())
        stage = json.loads((self.root / "processed_sprites/walk/_stage.json").read_text())
        self.assertEqual(len(stage["frames"]), 3)
        self.assertIn("fingerprint", stage)

    def test_invalid_processing_does_not_replace_approved_pixels_or_config(self):
        self.apply()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.data["sources"]["walk.png"]["process"] = {"scale": 20}
        response = self.post("apply", source="walk.png")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_export_reads_unsaved_actions_without_materializing_project_outputs(self):
        self.apply()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.data["actions"]["walk"]["sprites"] = ["walk/002.png", "walk/000.png"]
        self.data["workbench"]["reviews"]["walk_rest"]["clips"][0]["end"] = 1
        self.data["actions"]["walk"]["animation"] = {"order": [1, 0, 1], "durations_ms": [40, 120, 80], "loop": 2}
        response = self.post("export", options={"format": "all", "actions": ["walk"]})
        self.assertEqual(response.status_code, 200, response.text[:100])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertIn("sprites/walk/walk_00.png", archive.namelist())
            self.assertIn("spritesheets/test_walk.json", archive.namelist())
            first = Image.open(io.BytesIO(archive.read("sprites/walk/walk_00.png"))).convert("RGBA")
            self.assertEqual(first.getpixel((8, 8)), (0, 0, 255, 255))
            metadata = json.loads(archive.read("spritesheets/test_walk.json"))
            self.assertEqual([frame["duration"] for frame in metadata["frames"].values()], [62, 62])
            preview = Image.open(io.BytesIO(archive.read("webp/test_walk.webp")))
            self.assertEqual(preview.info["loop"], 2)
            self.assertEqual(preview.n_frames, 3)
            for i, duration in enumerate([40, 120, 80]):
                preview.seek(i)
                preview.convert("RGBA")
                self.assertEqual(preview.info["duration"], duration)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_review_uses_bounded_repeats_even_when_action_loops_forever(self):
        self.apply()
        cfg = load_config(self.path)
        review = self.data["workbench"]["reviews"]["walk_rest"]
        steps = review_steps(cfg, review)
        self.assertEqual([step["frame"] for step in steps], [1, 2, 1, 2, 0])
        self.assertEqual([step["duration_ms"] for step in steps], [62] * 4 + [100])
        self.assertEqual([i for i, step in enumerate(steps) if step["boundary"]], [0, 2, 4])
        response = self.post("export", options={"format": "review", "review": review})
        self.assertEqual(response.status_code, 200, response.text[:100])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(len(json.loads(archive.read("review.animation.json"))["steps"]), 5)
            self.assertIn("review.webp", archive.namelist())

    def test_invalid_review_ranges_and_deleted_actions_cannot_be_saved(self):
        before = self.path.read_bytes()
        clip = self.data["workbench"]["reviews"]["walk_rest"]["clips"][0]
        for patch in ({"end": 9}, {"repeat": 0}, {"action": "missing"}):
            original = copy.deepcopy(clip)
            clip.update(patch)
            self.assertEqual(self.post("save").status_code, 400)
            clip.clear()
            clip.update(original)
        self.assertEqual(before, self.path.read_bytes())

    def test_stale_window_cannot_overwrite_disk_or_apply_pixels(self):
        self.path.write_text(json.dumps({**self.data, "notes": ["external change"]}), encoding="utf-8")
        before = self.path.read_bytes()
        for endpoint in ("save", "apply", "prepare", "migrate"):
            response = self.post(endpoint, source="walk.png")
            self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / "processed_sprites").exists())

    def test_file_traversal_path_changes_and_cross_origin_writes_are_rejected(self):
        self.assertEqual(self.client.get("/api/image", params={"kind": "processed", "ref": "../source/walk.png"}).status_code, 400)
        self.assertEqual(self.client.post("/api/save", json={"data": self.data, "revision": self.revision}).status_code, 403)
        self.assertEqual(self.client.post("/api/save", headers={"x-workbench-token": self.token, "origin": "https://example.com"},
                                         json={"data": self.data, "revision": self.revision}).status_code, 403)
        self.data["paths"] = {"source": "../elsewhere"}
        self.assertEqual(self.post("save").status_code, 400)

    def test_recuts_keep_region_identity_and_reject_removing_used_pose(self):
        self.apply()
        self.data["sources"]["walk.png"]["extract"] = {"method": "boxes", "boxes": [[16, 0, 24, 8], [0, 0, 8, 8]]}
        preview = self.post("preview", source="walk.png")
        self.assertEqual([frame["id"] for frame in preview.json()["frames"]], ["002", "000"])
        response = self.post("apply", source="walk.png")
        self.assertEqual(response.status_code, 400)
        self.assertIn("walk/001.png", response.json()["error"])
        self.assertTrue((self.root / "processed_sprites/walk/001.png").exists())

    def test_cli_extract_keeps_ids_established_by_the_workbench(self):
        self.apply()
        self.data["sources"]["walk.png"]["extract"] = {"method": "boxes", "boxes": [[16, 0, 24, 8], [0, 0, 8, 8], [8, 0, 16, 8]]}
        self.apply()
        cfg = load_config(self.path)
        extract_source(cfg, "walk.png")
        inventory = json.loads((self.root / "source_sprites/walk/_stage.json").read_text())
        self.assertEqual(inventory["files"], ["002.png", "000.png", "001.png"])
        process_source(cfg, "walk.png")
        # CLI processing must retain provenance even if its raw cache is removed.
        import shutil
        cache = (self.root / "source_sprites").resolve()
        self.assertTrue(cache.is_relative_to(self.root.resolve()))
        shutil.rmtree(cache)
        response = self.post("preview", source="walk.png")
        self.assertEqual([f["id"] for f in response.json()["frames"]], ["002", "000", "001"])
        processed = (self.root / "processed_sprites").resolve()
        self.assertTrue(processed.is_relative_to(self.root.resolve()))
        shutil.rmtree(processed)
        # Identity mappings live in the recipe, so a clean clone also rebuilds.
        extract_source(cfg, "walk.png")
        inventory = json.loads((self.root / "source_sprites/walk/_stage.json").read_text())
        self.assertEqual(inventory["files"], ["002.png", "000.png", "001.png"])

    def test_migration_preserves_manual_final_pixels_and_repeated_frame_slots(self):
        self.apply()
        final = self.root / "sprites/walk"
        final.mkdir(parents=True)
        for i in range(3):
            Image.new("RGBA", (16, 16), "purple" if i != 1 else "yellow").save(final / f"walk_{i:02d}.png")
        before = {p.name: p.read_bytes() for p in final.iterdir()}
        response = self.post("migrate")
        self.assertEqual(response.status_code, 200, response.text)
        snapshot = response.json()
        self.assertEqual(snapshot["imported"], 3)
        refs = snapshot["data"]["actions"]["walk"]["sprites"]
        self.assertTrue(all(ref.startswith("_approved/walk/") for ref in refs))
        for i, ref in enumerate(refs):
            self.assertEqual((self.root / "processed_sprites" / ref).read_bytes(), before[f"walk_{i:02d}.png"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in final.iterdir()})

    def test_prepare_does_not_overwrite_manual_processed_images(self):
        self.apply()
        image_path = self.root / "processed_sprites/walk/000.png"
        Image.new("RGBA", (16, 16), "purple").save(image_path)
        before = image_path.read_bytes()
        response = self.post("prepare")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(image_path.read_bytes(), before)

    def test_portable_project_export_can_be_reopened_after_original_is_gone(self):
        self.apply()
        response = self.post("export", options={"format": "project"})
        self.assertEqual(response.status_code, 200)
        restored = self.root / "restored"
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            archive.extractall(restored)
        self.source.rename(self.root / "old_source")
        reopened = Project(restored / "pipeline.json")
        self.assertEqual(len(reopened.state()["assets"]), 3)
        content, _, _ = reopened.export(reopened.state()["data"], {"format": "frames", "actions": ["walk"]})
        self.assertGreater(len(content), 0)

    def test_source_and_processed_imports_reject_duplicates_and_wrong_canvas(self):
        image = png_bytes(Image.new("RGBA", (16, 16), "yellow"))
        content = base64.b64encode(image).decode()
        response = self.post("upload", kind="processed", filename="approved.png", content=content)
        self.assertEqual(response.status_code, 200, response.text)
        self.revision = response.json()["revision"]
        self.assertTrue((self.root / "processed_sprites/imports/approved.png").exists())
        self.assertEqual(self.post("upload", kind="processed", filename="approved.png", content=content).status_code, 400)
        self.assertEqual(self.post("upload", kind="source", filename="../bad.png", content=content).status_code, 400)
        self.assertEqual(self.post("upload", kind="source", filename="walk.jpg", content=content).status_code, 400)
        wrong = base64.b64encode(png_bytes(Image.new("RGBA", (5, 5), "red"))).decode()
        self.assertEqual(self.post("upload", kind="processed", filename="small.png", content=wrong).status_code, 400)

    def test_saved_recipe_marks_existing_processed_results_as_stale(self):
        self.apply()
        self.data["sources"]["walk.png"]["process"] = {"offset": [1, 0]}
        self.assertEqual(self.post("save").status_code, 200)
        snapshot = self.client.get("/api/project").json()
        self.assertTrue(snapshot["sources"][0]["stale"])


class SliceIdentityTests(unittest.TestCase):
    def test_new_region_does_not_steal_deleted_pose_id(self):
        previous = [{"file": "000.png", "source_box": [0, 0, 8, 8]}, {"file": "001.png", "source_box": [10, 0, 18, 8]}]
        self.assertEqual(preserve_slice_ids([(10, 0, 18, 8), (40, 0, 48, 8)], previous), ["001", "002"])


if __name__ == "__main__":
    unittest.main()

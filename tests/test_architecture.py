"""Enforce dependency direction and the compatibility import contract."""

import importlib
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from typing import get_type_hints

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from check_sprite_architecture import check


class ArchitectureTests(unittest.TestCase):
    def test_package_boundaries_and_runtime_cycles(self):
        self.assertEqual(check(TOOLS / "sprite_pipeline"), [])

    def test_checker_detects_backwards_import_and_cycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sprite_pipeline"
            (root / "domain").mkdir(parents=True)
            (root / "application").mkdir()
            (root / "domain/a.py").write_text(
                "from sprite_pipeline.application.b import run\n", encoding="utf-8"
            )
            (root / "application/b.py").write_text(
                "from sprite_pipeline.domain.a import run\n", encoding="utf-8"
            )
            errors = check(root)
            self.assertTrue(any("forbidden dependency" in e for e in errors))
            self.assertTrue(any("Runtime import cycle" in e for e in errors))

    def test_public_annotations_resolve_and_facades_export_real_symbols(self):
        root = TOOLS / "sprite_pipeline"
        for path in root.rglob("*.py"):
            name = "sprite_pipeline." + ".".join(path.relative_to(root).with_suffix("").parts)
            module = importlib.import_module(name)
            with self.subTest(module=name):
                for symbol in getattr(module, "__all__", []):
                    self.assertTrue(hasattr(module, symbol), symbol)
                for value in vars(module).values():
                    if inspect.isfunction(value) and value.__module__ == name:
                        get_type_hints(value)
                    elif inspect.isclass(value) and value.__module__ == name:
                        get_type_hints(value)
                        for method in vars(value).values():
                            if inspect.isfunction(method):
                                get_type_hints(method)

    def test_old_project_entrypoint_is_the_shared_application_facade(self):
        from sprite_pipeline.application.project import Project as ApplicationProject
        from sprite_pipeline.workbench import Project

        self.assertIs(Project, ApplicationProject)


if __name__ == "__main__":
    unittest.main()

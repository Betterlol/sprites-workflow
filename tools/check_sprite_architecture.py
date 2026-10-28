"""Check package dependency direction and runtime import cycles (stdlib only)."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

LAYERS = {
    "domain": {"domain"},
    "imaging": {"domain", "imaging"},
    "storage": {"domain", "storage"},
    "application": {"domain", "imaging", "storage", "application"},
    "interfaces": {"domain", "imaging", "storage", "application", "interfaces"},
}


def imports(tree: ast.AST):
    """Type-only annotations do not form runtime import cycles."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If) and (
            isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING"
            or isinstance(node.test, ast.Attribute)
            and node.test.attr == "TYPE_CHECKING"
        ):
            for child in node.orelse:
                yield from imports(child)
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        yield from imports(node)


def check(root: Path) -> list[str]:
    graph, problems = {}, []
    local_scripts = {p.stem for p in root.parent.glob("*.py")}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if len(relative.parts) < 2:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    problems.append(
                        f"{relative}: implementation belongs in a responsibility package"
                    )
            continue  # Legacy compatibility facades only point into packages.
        layer = relative.parts[0]
        module = "sprite_pipeline." + ".".join(relative.with_suffix("").parts)
        if module.endswith(".__init__"):
            module = module.removesuffix(".__init__")
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        targets = set()
        for node in imports(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                target = ("." * node.level) + (node.module or "")
                target = importlib.util.resolve_name(target, package) if node.level else target
                dependencies = [target]
                dependencies += [target + "." + alias.name for alias in node.names]
            else:
                dependencies = [alias.name for alias in node.names]
            for target in dependencies:
                if target.startswith("sprite_pipeline."):
                    parts = target.split(".")
                    if parts[1] not in LAYERS.get(layer, set()):
                        problems.append(f"{module}:{node.lineno}: forbidden dependency {target}")
                    targets.add(target)
                elif target.split(".")[0] in local_scripts:
                    problems.append(
                        f"{module}:{node.lineno}: depends on external tool script {target}"
                    )
        graph[module] = targets
    visited, active = set(), []

    def visit(module):
        if module in active:
            problems.append(
                "Runtime import cycle: " + " -> ".join(active[active.index(module) :] + [module])
            )
            return
        if module in visited:
            return
        active.append(module)
        for target in sorted(graph[module] & graph.keys()):
            visit(target)
        active.pop()
        visited.add(module)

    for module in graph:
        visit(module)
    return sorted(set(problems))


if __name__ == "__main__":
    failures = check(Path(__file__).resolve().parent / "sprite_pipeline")
    print("\n".join(failures) if failures else "Sprite package boundaries and runtime imports: OK")
    raise SystemExit(bool(failures))

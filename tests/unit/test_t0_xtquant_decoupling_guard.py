from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_ROOT = REPO_ROOT / "src" / "strategy"
ALLOWED_DYNAMIC_IMPORT_FILE = (
    STRATEGY_ROOT / "strategies" / "t0" / "strategy_engine.py"
)


def _iter_strategy_python_files() -> list[Path]:
    targets = [
        STRATEGY_ROOT / "core",
        STRATEGY_ROOT / "strategies" / "t0",
    ]
    files: list[Path] = []
    for target in targets:
        files.extend(sorted(target.rglob("*.py")))
    return files


def test_strategy_layers_have_no_static_xtquant_imports() -> None:
    violations: list[str] = []
    for file_path in _iter_strategy_python_files():
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "xtquant" or alias.name.startswith("xtquant."):
                        violations.append(f"{file_path}: static import '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "xtquant" or module.startswith("xtquant."):
                    violations.append(f"{file_path}: from import '{module}'")

    assert not violations, "\n".join(violations)


def test_dynamic_xtquant_loading_is_confined_to_strategy_engine() -> None:
    pattern = re.compile(r"import_module\((['\"])xtquant\1\)")
    matched_files: list[Path] = []

    for file_path in _iter_strategy_python_files():
        content = file_path.read_text(encoding="utf-8")
        if pattern.search(content):
            matched_files.append(file_path)

    assert matched_files == [ALLOWED_DYNAMIC_IMPORT_FILE], (
        "xtquant dynamic loading must be centralized in strategy_engine.py, "
        f"found: {[str(path) for path in matched_files]}"
    )

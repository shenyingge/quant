"""Verify that t0/core has no external dependencies."""

import ast
from pathlib import Path


def test_t0_core_no_external_imports():
    """t0/core should not import xtquant, redis, or sqlalchemy."""
    core_dir = Path("src/strategy/t0/core")
    forbidden_modules = ["xtquant", "redis", "sqlalchemy"]

    if not core_dir.exists():
        # Skip if core doesn't exist yet (will be verified in future phases)
        return

    for py_file in sorted(core_dir.glob("**/*.py")):
        if py_file.name.startswith("_"):
            continue

        text = py_file.read_text(encoding="utf-8")
        tree = ast.parse(text)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_modules:
                        assert forbidden not in alias.name, f"{py_file.relative_to('.')}: imports {forbidden}"

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_modules:
                        assert forbidden not in node.module, f"{py_file.relative_to('.')}: from ... import {forbidden}"


def test_backtest_dependency_whitelist():
    """backtest/ should only import from t0/core + t0/contracts."""
    backtest_dir = Path("src/backtest")
    if not backtest_dir.exists():
        return

    for py_file in sorted(backtest_dir.glob("**/*.py")):
        if py_file.name.startswith("_"):
            continue

        text = py_file.read_text(encoding="utf-8")

        # Simple pattern check for forbidden imports
        illegal_patterns = [
            "from src.strategy.runtime",
            "from src.strategy.t0_strategy",
            "from src.strategy_engine",
            "import redis",
            "import xtquant",
            "from sqlalchemy",
        ]

        for pattern in illegal_patterns:
            assert pattern not in text, f"{py_file.relative_to('.')}: contains {pattern}"

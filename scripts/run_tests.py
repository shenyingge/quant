#!/usr/bin/env python3
"""Legacy direct-file test runner for the reorganized tests tree."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = PROJECT_ROOT / "tests"

DEFAULT_TEST_FILES = [
    "live/test_redis_integration.py",
    "live/test_passorder.py",
    "live/test_concurrent_trading.py",
    "live/test_stress_trading.py",
    "unit/test_auto_cancel.py",
    "unit/test_order_timeout.py",
    "unit/test_constants.py",
    "unit/test_status_logic_fix.py",
    "unit/test_notification_fix.py",
]


def resolve_test_path(test_file: str) -> Path:
    candidate = Path(test_file)
    if candidate.is_absolute():
        return candidate

    for base in (TEST_ROOT, PROJECT_ROOT):
        resolved = base / candidate
        if resolved.exists():
            return resolved

    return TEST_ROOT / candidate


def run_single_test(test_file: str) -> bool:
    test_path = resolve_test_path(test_file)
    print(f"\n{'=' * 60}")
    print(f"Running test: {test_path.relative_to(PROJECT_ROOT)}")
    print(f"{'=' * 60}")

    if not test_path.exists():
        print(f"Missing test file: {test_path}")
        return False

    result = subprocess.run(
        [sys.executable, str(test_path)],
        capture_output=False,
        check=False,
        cwd=PROJECT_ROOT,
    )
    return result.returncode == 0


def run_all_tests() -> bool:
    print("QMT test smoke suite")
    print("=" * 60)

    results: dict[str, bool] = {}
    for test_file in DEFAULT_TEST_FILES:
        results[test_file] = run_single_test(test_file)

    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")

    success_count = 0
    for test_file, success in results.items():
        status = "PASS" if success else "FAIL"
        print(f"{status:>4} - {test_file}")
        if success:
            success_count += 1

    total_tests = len(results)
    print(f"\nTotal: {success_count}/{total_tests} passed")
    return success_count == total_tests


def run_pytest() -> bool:
    try:
        import pytest
    except ImportError:
        print("pytest is not installed. Run `uv sync --group dev` first.")
        return False

    pytest_args = [
        str(TEST_ROOT),
        "-v",
        "--tb=short",
        "--color=yes",
    ]
    return pytest.main(pytest_args) == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run direct-file smoke tests or pytest.")
    parser.add_argument("--test", "-t", help="Test path relative to the tests directory.")
    parser.add_argument("--pytest", action="store_true", help="Run pytest against tests/.")
    parser.add_argument("--list", "-l", action="store_true", help="List available test files.")
    args = parser.parse_args()

    if args.list:
        for test_file in sorted(TEST_ROOT.rglob("test_*.py")):
            print(test_file.relative_to(TEST_ROOT).as_posix())
        return

    if args.test:
        raise SystemExit(0 if run_single_test(args.test) else 1)

    if args.pytest:
        raise SystemExit(0 if run_pytest() else 1)

    raise SystemExit(0 if run_all_tests() else 1)


if __name__ == "__main__":
    main()

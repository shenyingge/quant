# Tests

The `tests/` tree is organized by test type instead of keeping dozens of files
flat in the root directory.

## Layout

```text
tests/
├── conftest.py
├── fixtures/
├── unit/
├── integration/
├── contract/
└── live/
```

Guidelines:

- Put pure Python or mock-heavy checks in `tests/unit/`.
- Put real database or service integration checks in `tests/integration/`.
- Put interface compatibility checks in `tests/contract/`.
- Put tests that require a live QMT session in `tests/live/`.
- Keep the `tests/` root limited to shared fixtures and this README.

## Common Commands

Run the default pytest suite:

```bash
uv run pytest
```

Run only unit tests:

```bash
uv run pytest tests/unit -v
```

Run only integration tests:

```bash
uv run pytest tests/integration -v
```

List direct-file smoke tests:

```bash
uv run python scripts/run_tests.py --list
```

Run one direct-file smoke test:

```bash
uv run python scripts/run_tests.py --test unit/test_notification_fix.py
```

## Notes

- `pytest.ini` already excludes `live_qmt` and `manual` markers by default.
- Historical test reports and retired ad-hoc notes were moved to `docs/archive/testing/`.
- If a test needs the repository root on `sys.path`, use `Path(__file__).resolve().parents[2]` from files under `tests/unit/`.

# Migrations

Migration files in `migrations/versions/` now follow this rule:

- File name format: `YYYYMMDD_HHMMSS_<8-char-hash>_slug.py`
- Revision id format for new migrations: `YYYYMMDD_HHMMSS_<8-char-hash>`

Create new revisions directly with Alembic when needed:

```powershell
.\.venv\Scripts\python.exe -m alembic revision --rev-id 20260405_120000_ab12cd34 -m "describe change"
.\.venv\Scripts\python.exe -m alembic revision --rev-id 20260405_120000_ab12cd34 -m "describe change" --autogenerate
```

Important:

- Keep the `rev-id` and the file name prefix aligned.
- Generate the hash from `YYYYMMDD_HHMMSS:slug` and keep 8 hex characters.
- If any database has already been stamped with the old revision ids, its
  `alembic_version` row must be updated before running Alembic again.

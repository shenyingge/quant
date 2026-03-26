#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Download stock minute history from QMT local cache/data service using a stock list
stored in the Meta DB, save one parquet per stock, package as zip, and upload to NAS.
"""

import argparse
import asyncio
import json
import shlex
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import asyncpg
import paramiko
from xtquant import xtdata

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.data_manager.storage import MarketDataStorage


@dataclass
class StockRecord:
    ts_code: str
    symbol: str
    name: str
    list_status: str
    list_date: Optional[str]
    delist_date: Optional[str]


def default_start_date() -> str:
    today = date.today()
    return f"{today.year - 1}0101"


def default_end_date() -> str:
    return date.today().strftime("%Y%m%d")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read stock codes from Meta DB gold.stock_basic, download 1-minute history "
            "from last year to today, save one parquet per stock, zip the bundle, and upload to NAS."
        )
    )
    parser.add_argument("--start-date", default=default_start_date(), help="YYYYMMDD")
    parser.add_argument("--end-date", default=default_end_date(), help="YYYYMMDD")
    parser.add_argument("--schema", default=settings.meta_db_schema or "gold")
    parser.add_argument(
        "--output-root",
        default=str(PROJECT_ROOT / "data" / "minute_history_exports"),
        help="Directory to hold bundle directories and zip files",
    )
    parser.add_argument(
        "--remote-subdir",
        default="minute_history",
        help="Subdirectory under NS_SCP_REMOTE_DIR for uploaded zip files",
    )
    parser.add_argument(
        "--zip-name",
        default="",
        help="Optional zip file name, for example 2025-AUG-DEC.zip",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of stocks")
    parser.add_argument(
        "--codes",
        default="",
        help="Comma-separated ts_code list to override DB enumeration",
    )
    parser.add_argument(
        "--listed-only",
        action="store_true",
        help="Only process list_status='L' rows from stock_basic",
    )
    parser.add_argument(
        "--skip-zip",
        action="store_true",
        help="Skip zip creation and only keep per-stock parquet files",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip NAS upload",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download and overwrite parquet files even if they already exist",
    )
    return parser


def ensure_meta_db_config() -> None:
    missing = [
        key
        for key, value in {
            "META_DB_HOST": settings.meta_db_host,
            "META_DB_NAME": settings.meta_db_name,
            "META_DB_USER": settings.meta_db_user,
            "META_DB_PASSWORD": settings.meta_db_password,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing Meta DB config: {', '.join(missing)}")


async def fetch_stock_records(
    schema: str, listed_only: bool, codes: Iterable[str]
) -> List[StockRecord]:
    ensure_meta_db_config()
    conn = await asyncpg.connect(
        host=settings.meta_db_host,
        port=settings.meta_db_port,
        database=settings.meta_db_name,
        user=settings.meta_db_user,
        password=settings.meta_db_password,
        timeout=10,
    )
    try:
        codes = [code.strip().upper() for code in codes if code.strip()]
        where_clauses = []
        args: List[object] = []

        if listed_only:
            where_clauses.append("list_status = 'L'")

        if codes:
            where_clauses.append(f"ts_code = ANY(${len(args) + 1})")
            args.append(codes)

        where_sql = f"where {' and '.join(where_clauses)}" if where_clauses else ""
        query = f"""
            select ts_code, symbol, name, list_status, list_date, delist_date
            from {schema}.stock_basic
            {where_sql}
            order by ts_code
        """
        rows = await conn.fetch(query, *args)
        return [StockRecord(**dict(row)) for row in rows]
    finally:
        await conn.close()


def normalize_result(data, code: str):
    if data is None:
        return None
    if isinstance(data, dict):
        return data.get(code)
    return data


def download_single_stock(
    storage: MarketDataStorage,
    parquet_dir: Path,
    stock: StockRecord,
    start_date: str,
    end_date: str,
    overwrite: bool,
) -> Tuple[bool, str]:
    file_path = parquet_dir / f"{stock.ts_code}.parquet"
    if file_path.exists() and file_path.stat().st_size > 0 and not overwrite:
        return True, "skipped_existing"

    xtdata.download_history_data(stock.ts_code, "1m", start_date, end_date)
    local_data = xtdata.get_local_data(
        stock_list=[stock.ts_code],
        period="1m",
        start_time=start_date,
        end_time=end_date,
    )
    raw_df = normalize_result(local_data, stock.ts_code)
    if raw_df is None or raw_df.empty:
        return False, "no_data"

    standardized = storage.standardize_market_data(raw_df, stock.ts_code)
    standardized.to_parquet(file_path, engine="pyarrow", compression="snappy")
    return True, f"rows={len(standardized)}"


def create_zip_file(bundle_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(
        zip_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as zf:
        for file_path in sorted(bundle_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(bundle_dir))


def resolve_ssh_target(alias_or_host: str) -> Dict[str, object]:
    result: Dict[str, object] = {"hostname": alias_or_host}
    ssh_config_path = Path.home() / ".ssh" / "config"
    if not ssh_config_path.exists():
        return result

    with ssh_config_path.open("r", encoding="utf-8") as fh:
        ssh_config = paramiko.SSHConfig()
        ssh_config.parse(fh)
    info = ssh_config.lookup(alias_or_host)

    if info.get("hostname"):
        result["hostname"] = info["hostname"]
    if info.get("user"):
        result["username"] = info["user"]
    if info.get("port"):
        result["port"] = int(info["port"])
    if info.get("identityfile"):
        identity_files = info["identityfile"]
        if identity_files:
            result["identityfile"] = str(Path(identity_files[0]).expanduser())
    return result


def shell_quote(path: str) -> str:
    return shlex.quote(path)


def upload_zip_to_nas(zip_path: Path, remote_subdir: str) -> str:
    target = resolve_ssh_target(settings.ns_host)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = {
        "hostname": target["hostname"],
        "username": target.get("username"),
        "port": target.get("port", 22),
        "timeout": 20,
    }
    identity_file = target.get("identityfile")
    if identity_file:
        connect_kwargs["pkey"] = paramiko.RSAKey.from_private_key_file(str(identity_file))

    ssh.connect(**connect_kwargs)
    try:
        stdin, stdout, _ = ssh.exec_command('printf %s "$HOME"')
        home_dir = stdout.read().decode().strip()
        remote_base = settings.ns_scp_remote_dir
        if remote_base.startswith("~/"):
            remote_base = f"{home_dir}/{remote_base[2:]}"
        elif remote_base == "~":
            remote_base = home_dir

        remote_dir = f"{remote_base.rstrip('/')}/{remote_subdir.strip('/')}"
        remote_file = f"{remote_dir}/{zip_path.name}"

        ssh.exec_command(f"mkdir -p {shell_quote(remote_dir)}")[1].channel.recv_exit_status()

        sftp = ssh.open_sftp()
        try:
            sftp.put(str(zip_path), remote_file)
        finally:
            sftp.close()
        return remote_file
    finally:
        ssh.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    bundle_name = f"stock_minute_1m_{args.start_date}_{args.end_date}"
    output_root = Path(args.output_root)
    bundle_dir = output_root / bundle_name
    parquet_dir = bundle_dir / "parquet"
    parquet_dir.mkdir(parents=True, exist_ok=True)

    codes = [item.strip() for item in args.codes.split(",") if item.strip()]
    stocks = asyncio.run(fetch_stock_records(args.schema, args.listed_only, codes))
    if args.limit:
        stocks = stocks[: args.limit]

    if not stocks:
        raise RuntimeError("No stocks matched the current filters.")

    storage_tmp_dir = bundle_dir / "storage_tmp"
    storage = MarketDataStorage(str(storage_tmp_dir))
    results = []
    success_count = 0
    failure_count = 0

    for idx, stock in enumerate(stocks, start=1):
        ok, detail = download_single_stock(
            storage=storage,
            parquet_dir=parquet_dir,
            stock=stock,
            start_date=args.start_date,
            end_date=args.end_date,
            overwrite=args.overwrite,
        )
        record = {
            **asdict(stock),
            "ok": ok,
            "detail": detail,
            "parquet_path": str((parquet_dir / f"{stock.ts_code}.parquet").resolve()),
        }
        results.append(record)
        if ok:
            success_count += 1
        else:
            failure_count += 1
        print(f"[{idx}/{len(stocks)}] {stock.ts_code} {stock.name}: {detail}")

    manifest = {
        "bundle_name": bundle_name,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "schema": args.schema,
        "listed_only": args.listed_only,
        "total": len(stocks),
        "success": success_count,
        "failed": failure_count,
        "results": results,
    }
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    zip_name = args.zip_name.strip() or f"{bundle_name}.zip"
    if not zip_name.lower().endswith(".zip"):
        zip_name = f"{zip_name}.zip"
    zip_path = output_root / zip_name
    if not args.skip_zip:
        create_zip_file(bundle_dir, zip_path)
        print(f"zip_created={zip_path}")

    if not args.skip_upload and not args.skip_zip:
        remote_file = upload_zip_to_nas(zip_path, args.remote_subdir)
        print(f"uploaded_to={remote_file}")

    shutil.rmtree(storage_tmp_dir, ignore_errors=True)

    print(
        json.dumps(
            {
                "bundle_dir": str(bundle_dir),
                "zip_path": str(zip_path) if not args.skip_zip else "",
                "total": len(stocks),
                "success": success_count,
                "failed": failure_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if failure_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

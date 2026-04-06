#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分钟历史行情导出工具。

从 Meta DB 读取股票列表，使用 QMT 本地缓存或数据服务下载分钟行情，
按股票保存为 parquet，打包为 zip，并可选上传到 NAS。
"""

import argparse
import asyncio
import json
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from xtquant import xtdata

from src.infrastructure.config import settings
from src.data_manager.storage import MarketDataStorage
from src.infrastructure.db.meta_db import validate_meta_db_config
from src.infrastructure.sync.remote_sync import sync_file_via_rsync, sync_tree_via_rsync

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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


def normalize_trade_date(value: str) -> str:
    candidate = (value or "").strip().lower()
    if not candidate or candidate == "today":
        return date.today().strftime("%Y%m%d")
    if len(candidate) != 8 or not candidate.isdigit():
        raise ValueError(f"无效的交易日期: {value}，应为 YYYYMMDD 或 today。")
    return candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "从 Meta DB 的 gold.stock_basic 读取股票代码，下载 QMT 本地 1 分钟历史行情，"
            "按股票保存 parquet，打包 zip，并可选上传到 NAS。"
        )
    )
    parser.add_argument("--start-date", default=default_start_date(), help="YYYYMMDD")
    parser.add_argument("--end-date", default=default_end_date(), help="YYYYMMDD")
    parser.add_argument(
        "--trade-date",
        default="",
        help="单日交易日期快捷参数，支持 YYYYMMDD 或 today。",
    )
    parser.add_argument("--schema", default=settings.meta_db_schema or "gold")
    parser.add_argument(
        "--output-root",
        default=str(PROJECT_ROOT / "data" / "minute_history_exports"),
        help="保存导出目录和 zip 文件的根目录",
    )
    parser.add_argument(
        "--remote-subdir",
        default="minute_history",
        help="上传 zip 时使用的 NAS 子目录，位于 NS_SCP_REMOTE_DIR 之下",
    )
    parser.add_argument(
        "--zip-name",
        default="",
        help="可选 zip 文件名，例如 2025-AUG-DEC.zip",
    )
    parser.add_argument("--limit", type=int, default=None, help="限制处理的股票数量")
    parser.add_argument(
        "--codes",
        default="",
        help="逗号分隔的 ts_code 列表，指定后将覆盖数据库股票列表",
    )
    parser.add_argument(
        "--listed-only",
        action="store_true",
        help="仅处理 stock_basic 中 list_status='L' 的股票",
    )
    parser.add_argument(
        "--skip-zip",
        action="store_true",
        help="跳过 zip 打包，仅保留逐股 parquet 文件",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="跳过 NAS 上传",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="即使 parquet 已存在也重新下载并覆盖",
    )
    return parser


def resolve_date_range(args: argparse.Namespace) -> Tuple[str, str]:
    trade_date = getattr(args, "trade_date", "")
    if trade_date:
        single_trade_date = normalize_trade_date(trade_date)
        return single_trade_date, single_trade_date
    return args.start_date, args.end_date


def build_bundle_name(start_date: str, end_date: str) -> str:
    if start_date == end_date:
        return f"stock_minute_1m_{start_date}"
    return f"stock_minute_1m_{start_date}_{end_date}"


def ensure_meta_db_config() -> None:
    validate_meta_db_config(
        required_keys=("META_DB_HOST", "META_DB_NAME", "META_DB_USER", "META_DB_PASSWORD")
    )


async def fetch_stock_records(
    schema: str, listed_only: bool, codes: Iterable[str]
) -> List[StockRecord]:
    import asyncpg

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


def upload_zip_to_nas(zip_path: Path, remote_subdir: str) -> str:
    return sync_file_via_rsync(
        file=zip_path,
        remote_subdir=remote_subdir,
        remote_base=settings.ns_scp_remote_dir,
        alias_or_host=settings.ns_host,
        timeout=20,
    )


def build_remote_upload_subdir(
    remote_subdir: str, start_date: str, end_date: str, bundle_name: str, skip_zip: bool
) -> str:
    if skip_zip:
        suffix = start_date if start_date == end_date else bundle_name
        return f"{remote_subdir.strip('/')}/{suffix}".strip("/")
    return remote_subdir


def run_export(args: argparse.Namespace) -> int:
    start_date, end_date = resolve_date_range(args)
    bundle_name = build_bundle_name(start_date, end_date)
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
            start_date=start_date,
            end_date=end_date,
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
        "trade_date": start_date if start_date == end_date else "",
        "start_date": start_date,
        "end_date": end_date,
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
    remote_upload_subdir = build_remote_upload_subdir(
        args.remote_subdir, start_date, end_date, bundle_name, args.skip_zip
    )
    if not args.skip_zip:
        create_zip_file(bundle_dir, zip_path)
        print(f"zip_created={zip_path}")

    if not args.skip_upload:
        if args.skip_zip:
            remote_files = sync_tree_via_rsync(
                local_root=bundle_dir,
                remote_subdir=remote_upload_subdir,
                remote_base=settings.ns_scp_remote_dir,
                alias_or_host=settings.ns_host,
                timeout=20,
            )
            print(f"uploaded_dir={remote_upload_subdir}")
            print(f"uploaded_files={len(remote_files)}")
        else:
            remote_file = upload_zip_to_nas(zip_path, remote_upload_subdir)
            print(f"uploaded_to={remote_file}")

    shutil.rmtree(storage_tmp_dir, ignore_errors=True)

    print(
        json.dumps(
            {
                "bundle_dir": str(bundle_dir),
                "zip_path": str(zip_path) if not args.skip_zip else "",
                "start_date": start_date,
                "end_date": end_date,
                "total": len(stocks),
                "success": success_count,
                "failed": failure_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if failure_count == 0 else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_export(args)


if __name__ == "__main__":
    raise SystemExit(main())

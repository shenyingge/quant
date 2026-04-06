from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime
from typing import Iterable, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.infrastructure.meta_db import get_meta_db_sync_url
from src.infrastructure.logger_config import configured_logger as logger
from src.market_data.ingestion.minute_history_exporter import (
    StockRecord,
    fetch_stock_records,
    normalize_result,
    normalize_trade_date,
    resolve_date_range,
)
from src.market_data.ingestion.minute_history_models import (
    MINUTE_BAR_SCHEMA,
    MinuteBarBase,
    StockMinuteBar,
)


def default_bootstrap_start_date() -> str:
    today = date.today()
    return f"{today.year}0101"


def default_end_date() -> str:
    return date.today().strftime("%Y%m%d")


class MinuteHistoryIngestor:
    def __init__(self, *, schema: str = MINUTE_BAR_SCHEMA, source: str = "qmt_1m"):
        self.schema = schema
        self.source = source

    def _engine(self):
        return create_engine(get_meta_db_sync_url(), pool_pre_ping=True)

    def ensure_table(self) -> None:
        engine = self._engine()
        try:
            with engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"'))
                MinuteBarBase.metadata.create_all(bind=conn)
        finally:
            engine.dispose()

    def _fetch_stock_records_sync(
        self, listed_only: bool, codes: Iterable[str]
    ) -> list[StockRecord]:
        return asyncio.run(fetch_stock_records(self.schema, listed_only, codes))

    def _download_minute_dataframe(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        from xtquant import xtdata

        xtdata.download_history_data(stock_code, "1m", start_date, end_date)
        local_data = xtdata.get_local_data(
            stock_list=[stock_code],
            period="1m",
            start_time=start_date,
            end_time=end_date,
        )
        raw_df = normalize_result(local_data, stock_code)
        if raw_df is None:
            return pd.DataFrame()
        return raw_df

    def _build_rows_from_dataframe(self, symbol: str, frame: pd.DataFrame) -> list[dict]:
        if frame is None or frame.empty:
            return []

        working = frame.copy()
        if not isinstance(working.index, pd.DatetimeIndex):
            for candidate in ("time", "datetime", "dt", "bar_time"):
                if candidate in working.columns:
                    working[candidate] = pd.to_datetime(working[candidate], errors="coerce")
                    working = working.dropna(subset=[candidate]).set_index(candidate)
                    break

        if not isinstance(working.index, pd.DatetimeIndex):
            return []

        working = working.sort_index()
        rows: list[dict] = []
        for bar_time, row in working.iterrows():
            close_value = float(row.get("close", 0.0) or 0.0)
            volume_value = float(row.get("volume", 0.0) or 0.0)
            amount_value = float(row.get("amount", close_value * volume_value) or 0.0)

            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": bar_time.date(),
                    "bar_time": bar_time.to_pydatetime().replace(tzinfo=None),
                    "open": float(row.get("open", close_value) or close_value),
                    "high": float(row.get("high", close_value) or close_value),
                    "low": float(row.get("low", close_value) or close_value),
                    "close": close_value,
                    "volume": volume_value,
                    "amount": amount_value,
                    "source": self.source,
                    "ingested_at": datetime.utcnow(),
                }
            )
        return rows

    def _upsert_rows(self, rows: list[dict]) -> int:
        if not rows:
            return 0

        table = StockMinuteBar.__table__
        engine = self._engine()
        try:
            with engine.begin() as conn:
                if conn.dialect.name == "postgresql":
                    stmt = pg_insert(table).values(rows)
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_stock_minute_1m_symbol_bar_time",
                        set_={
                            "trade_date": stmt.excluded.trade_date,
                            "open": stmt.excluded.open,
                            "high": stmt.excluded.high,
                            "low": stmt.excluded.low,
                            "close": stmt.excluded.close,
                            "volume": stmt.excluded.volume,
                            "amount": stmt.excluded.amount,
                            "source": stmt.excluded.source,
                            "ingested_at": stmt.excluded.ingested_at,
                        },
                    )
                    result = conn.execute(stmt)
                    return result.rowcount if result.rowcount is not None else len(rows)

                for row in rows:
                    conn.execute(
                        table.delete().where(
                            (table.c.symbol == row["symbol"]) & (table.c.bar_time == row["bar_time"])
                        )
                    )
                    conn.execute(table.insert().values(**row))
                return len(rows)
        finally:
            engine.dispose()

    def ingest_range(
        self,
        *,
        start_date: str,
        end_date: str,
        listed_only: bool,
        codes: Optional[list[str]] = None,
        limit: Optional[int] = None,
    ) -> dict:
        self.ensure_table()
        stocks = self._fetch_stock_records_sync(listed_only, codes or [])
        if limit:
            stocks = stocks[:limit]

        inserted_rows = 0
        success_stocks = 0
        failed_stocks = 0
        empty_stocks = 0

        for stock in stocks:
            try:
                symbol = stock.ts_code
                frame = self._download_minute_dataframe(stock.ts_code, start_date, end_date)
                rows = self._build_rows_from_dataframe(symbol, frame)
                if not rows:
                    empty_stocks += 1
                    continue

                inserted_rows += self._upsert_rows(rows)
                success_stocks += 1
            except Exception as exc:
                failed_stocks += 1
                logger.warning("Minute ingest failed for {}: {}", getattr(stock, "ts_code", ""), exc)

        return {
            "schema": self.schema,
            "table": f"{self.schema}.stock_minute_bars_1m",
            "start_date": start_date,
            "end_date": end_date,
            "total_stocks": len(stocks),
            "success_stocks": success_stocks,
            "empty_stocks": empty_stocks,
            "failed_stocks": failed_stocks,
            "inserted_rows": inserted_rows,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 QMT 1 分钟历史行情写入 Meta DB")
    parser.add_argument("--start-date", default=default_bootstrap_start_date(), help="YYYYMMDD")
    parser.add_argument("--end-date", default=default_end_date(), help="YYYYMMDD")
    parser.add_argument("--trade-date", default="", help="单日交易日期，YYYYMMDD 或 today")
    parser.add_argument("--schema", default=MINUTE_BAR_SCHEMA)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--codes", default="", help="逗号分隔 ts_code 列表")
    parser.add_argument("--listed-only", action="store_true")
    return parser


def run_ingest(args: argparse.Namespace) -> int:
    start_date, end_date = resolve_date_range(args)
    start_date = normalize_trade_date(start_date)
    end_date = normalize_trade_date(end_date)

    codes = [item.strip() for item in (args.codes or "").split(",") if item.strip()]
    ingestor = MinuteHistoryIngestor(schema=args.schema)
    summary = ingestor.ingest_range(
        start_date=start_date,
        end_date=end_date,
        listed_only=bool(args.listed_only),
        codes=codes,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed_stocks"] == 0 else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_ingest(args)


if __name__ == "__main__":
    raise SystemExit(main())

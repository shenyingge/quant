"""Market data gateway adapters for live and test-only compatibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class MarketDataGateway(Protocol):
    def fetch_market_data(
        self,
        *,
        stock_list: list[str],
        period: str,
        count: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        dividend_type: str = "front",
    ) -> Any:
        ...

    def fetch_full_tick(self, stock_list: list[str]) -> Any:
        ...

    def download_history_data(
        self,
        stock_code: str,
        period: str,
        start_time: str,
        end_time: str,
    ) -> None:
        ...

    def fetch_local_data(
        self,
        *,
        stock_list: list[str],
        period: str,
        start_time: str,
        end_time: str,
    ) -> Any:
        ...


@dataclass
class XTQuantMarketDataGateway:
    """Live gateway backed by xtquant.xtdata."""

    xtdata_client: Any

    def fetch_market_data(
        self,
        *,
        stock_list: list[str],
        period: str,
        count: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        dividend_type: str = "front",
    ) -> Any:
        kwargs: dict[str, Any] = {
            "stock_list": stock_list,
            "period": period,
            "dividend_type": dividend_type,
        }
        if count is not None:
            kwargs["count"] = count
        if start_time is not None:
            kwargs["start_time"] = start_time
        if end_time is not None:
            kwargs["end_time"] = end_time
        return self.xtdata_client.get_market_data(**kwargs)

    def fetch_full_tick(self, stock_list: list[str]) -> Any:
        return self.xtdata_client.get_full_tick(stock_list)

    def download_history_data(
        self,
        stock_code: str,
        period: str,
        start_time: str,
        end_time: str,
    ) -> None:
        self.xtdata_client.download_history_data(stock_code, period, start_time, end_time)

    def fetch_local_data(
        self,
        *,
        stock_list: list[str],
        period: str,
        start_time: str,
        end_time: str,
    ) -> Any:
        return self.xtdata_client.get_local_data(
            stock_list=stock_list,
            period=period,
            start_time=start_time,
            end_time=end_time,
        )


class NullMarketDataGateway:
    """No-op gateway used by tests or environments without a live data source."""

    def fetch_market_data(
        self,
        *,
        stock_list: list[str],
        period: str,
        count: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        dividend_type: str = "front",
    ) -> Any:
        return None

    def fetch_full_tick(self, stock_list: list[str]) -> Any:
        return None

    def download_history_data(
        self,
        stock_code: str,
        period: str,
        start_time: str,
        end_time: str,
    ) -> None:
        return None

    def fetch_local_data(
        self,
        *,
        stock_list: list[str],
        period: str,
        start_time: str,
        end_time: str,
    ) -> Any:
        return None

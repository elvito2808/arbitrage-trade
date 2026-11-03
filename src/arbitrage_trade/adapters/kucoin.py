"""Minimal public KuCoin ticker adapter. No API key or trading endpoint is used."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..core import MarketQuote


class AdapterError(RuntimeError):
    """Raised when an exchange response cannot be used."""


class KuCoinAdapter:
    name = "kucoin"
    BASE_URL = "https://api.kucoin.com"

    def __init__(self, timeout: float = 10.0) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = timeout

    def get_quote(self, symbol: str) -> MarketQuote:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol cannot be empty")
        normalized = symbol.strip().upper().replace("/", "-")
        query = urlencode({"symbol": normalized})
        request = Request(
            f"{self.BASE_URL}/api/v1/market/orderbook/level1?{query}",
            headers={"Accept": "application/json", "User-Agent": "arbitrage-trade/0.1"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdapterError(f"KuCoin public market request failed: {type(exc).__name__}") from exc

        if not isinstance(payload, dict) or payload.get("code") != "200000":
            code = payload.get("code") if isinstance(payload, dict) else None
            raise AdapterError(f"Unexpected KuCoin response code: {code}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AdapterError("KuCoin response data must be an object")
        try:
            timestamp = int(data["time"]) if data.get("time") is not None else None
            return MarketQuote(
                symbol=normalized,
                bid=data["bestBid"],
                ask=data["bestAsk"],
                timestamp_ms=timestamp,
                source=self.name,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AdapterError("KuCoin ticker payload is missing valid bid/ask values") from exc

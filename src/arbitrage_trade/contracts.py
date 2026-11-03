"""Venue-agnostic contracts for CEX, DEX, network and market-data sources."""
from typing import Any, Protocol, runtime_checkable

from .core import MarketQuote, SwapQuote
from .domain import Market, PriceQuote


@runtime_checkable
class CEXAdapter(Protocol):
    name: str
    def get_quote(self, symbol: str) -> MarketQuote: ...


@runtime_checkable
class DEXAdapter(Protocol):
    name: str
    chain_id: int
    def get_quote(self, token_in: str, token_out: str, amount_in: str) -> SwapQuote: ...


@runtime_checkable
class NetworkClient(Protocol):
    def chain_id(self) -> int: ...
    def call(self, method: str, params: list[Any]) -> Any: ...


@runtime_checkable
class MarketDataSource(Protocol):
    name: str
    def get_market(self, market_id: str) -> Market: ...
    def get_price_quote(self, market: Market) -> PriceQuote: ...

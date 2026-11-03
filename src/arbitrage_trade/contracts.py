"""Adapter contracts shared by centralized and decentralized venues."""

from typing import Protocol, runtime_checkable

from .core import MarketQuote, SwapQuote


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

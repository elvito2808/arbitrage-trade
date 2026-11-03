"""Core numeric and market data primitives; floats are intentionally avoided."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TypeAlias

DecimalLike: TypeAlias = Decimal | str | int


def to_decimal(value: DecimalLike) -> Decimal:
    """Convert an API/user numeric value without introducing binary float error."""
    if isinstance(value, (bool, float)):
        raise TypeError("Use Decimal, str, or int; float values are not accepted")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc
    if not result.is_finite():
        raise ValueError("Decimal value must be finite")
    return result


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """Best bid/ask quote for a centralized order book."""

    symbol: str
    bid: Decimal
    ask: Decimal
    timestamp_ms: int | None = None
    source: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "bid", to_decimal(self.bid))
        object.__setattr__(self, "ask", to_decimal(self.ask))
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if self.bid <= 0 or self.ask <= 0:
            raise ValueError("bid and ask must be positive")
        if self.ask < self.bid:
            raise ValueError("ask cannot be lower than bid")
        if self.timestamp_ms is not None and self.timestamp_ms < 0:
            raise ValueError("timestamp_ms cannot be negative")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def spread_percent(self) -> Decimal:
        return (self.spread / self.ask) * Decimal("100")


@dataclass(frozen=True, slots=True)
class SwapQuote:
    """Exact-input DEX quote; amounts are raw token base units, not human units."""

    token_in: str
    token_out: str
    amount_in: int
    amount_out: int
    chain_id: int
    source: str
    timestamp_ms: int

    def __post_init__(self) -> None:
        if self.amount_in <= 0 or self.amount_out <= 0:
            raise ValueError("swap quote amounts must be positive")
        if self.chain_id <= 0:
            raise ValueError("chain_id must be positive")
        if self.timestamp_ms < 0:
            raise ValueError("timestamp_ms cannot be negative")

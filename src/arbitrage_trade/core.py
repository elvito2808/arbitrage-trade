"""Core numeric and market data primitives; floats are intentionally avoided."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TypeAlias

DecimalLike: TypeAlias = Decimal | str | int


def to_decimal(value: DecimalLike) -> Decimal:
    """Convert an API/user numeric value without introducing binary float error."""
    if isinstance(value, bool) or isinstance(value, float):
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

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def spread_percent(self) -> Decimal:
        return (self.spread / self.ask) * Decimal("100")

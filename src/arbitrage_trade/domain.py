"""Venue-independent domain models with explicit units and timestamps."""
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import re

from .core import to_decimal


@dataclass(frozen=True, slots=True)
class Asset:
    symbol: str
    chain_id: int | None = None
    contract_address: str | None = None
    decimals: int | None = None

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.strip():
            raise ValueError("asset symbol must be non-empty and normalized")
        if self.chain_id is not None and self.chain_id <= 0:
            raise ValueError("chain_id must be positive")
        if self.decimals is not None and not 0 <= self.decimals <= 255:
            raise ValueError("decimals must be between 0 and 255")
        if self.contract_address is not None:
            if self.chain_id is None:
                raise ValueError("contract_address requires chain_id")
            if not isinstance(self.contract_address, str) or not re.fullmatch(
                r"0x[0-9a-fA-F]{40}", self.contract_address
            ):
                raise ValueError("contract_address must be a 20-byte 0x-prefixed hex address")
            object.__setattr__(self, "contract_address", self.contract_address.lower())


@dataclass(frozen=True, slots=True)
class Market:
    venue: str
    market_id: str
    base: Asset
    quote: Asset
    market_type: str

    def __post_init__(self) -> None:
        if not self.venue or not self.market_id or not self.market_type:
            raise ValueError("venue, market_id and market_type are required")
        if self.base == self.quote:
            raise ValueError("base and quote assets must differ")


@dataclass(frozen=True, slots=True)
class PriceQuote:
    market: Market
    bid: Decimal
    ask: Decimal
    observed_at: datetime
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    source: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "bid", to_decimal(self.bid))
        object.__setattr__(self, "ask", to_decimal(self.ask))
        if self.bid <= 0 or self.ask < self.bid:
            raise ValueError("quote requires positive, non-inverted bid/ask")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        for field in ("bid_size", "ask_size"):
            value = getattr(self, field)
            if value is not None:
                value = to_decimal(value)
                if value < 0:
                    raise ValueError(f"{field} cannot be negative")
                object.__setattr__(self, field, value)


@dataclass(frozen=True, slots=True)
class ArbitrageOpportunity:
    buy_quote: PriceQuote
    sell_quote: PriceQuote
    base_quantity: Decimal
    detected_at: datetime
    identifier: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_quantity", to_decimal(self.base_quantity))
        if self.base_quantity <= 0:
            raise ValueError("base_quantity must be positive")
        if self.buy_quote.market.base != self.sell_quote.market.base:
            raise ValueError("opportunity base assets must match")
        if self.buy_quote.market.quote != self.sell_quote.market.quote:
            raise ValueError("opportunity quote assets must match")
        if self.buy_quote.market == self.sell_quote.market:
            raise ValueError("buy and sell markets must differ")
        if self.detected_at.tzinfo is None:
            raise ValueError("detected_at must be timezone-aware")
        if not self.identifier:
            raise ValueError("identifier is required")


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    market: Market
    side: OrderSide
    quantity: Decimal
    status: OrderStatus = OrderStatus.PENDING
    client_order_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", to_decimal(self.quantity))
        if not self.order_id:
            raise ValueError("order_id is required")
        try:
            side = self.side if isinstance(self.side, OrderSide) else OrderSide(self.side.lower())
        except (AttributeError, ValueError) as exc:
            raise ValueError("side must be buy or sell") from exc
        object.__setattr__(self, "side", side)
        if self.quantity <= 0:
            raise ValueError("order quantity must be positive")


@dataclass(frozen=True, slots=True)
class TradeResult:
    order: Order
    filled_quantity: Decimal
    average_price: Decimal | None
    fee_paid: Decimal | None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "filled_quantity", to_decimal(self.filled_quantity))
        if self.filled_quantity < 0 or self.filled_quantity > self.order.quantity:
            raise ValueError("filled_quantity must be within order quantity")
        for field in ("average_price", "fee_paid"):
            value = getattr(self, field)
            if value is not None:
                value = to_decimal(value)
                if value < 0 or (field == "average_price" and value == 0 and self.filled_quantity):
                    raise ValueError(f"{field} must be non-negative and valid")
                object.__setattr__(self, field, value)
        if self.completed_at is not None and self.completed_at.tzinfo is None:
            raise ValueError("completed_at must be timezone-aware")


def utc_now() -> datetime:
    return datetime.now(UTC)

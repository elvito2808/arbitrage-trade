"""Conservative net-profit evaluation; unknown costs and incomplete data reject."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from .core import to_decimal
from .domain import ArbitrageOpportunity


class RejectionReason(StrEnum):
    INCOMPLETE_DATA = "incomplete_data"
    STALE_QUOTE = "stale_quote"
    INSUFFICIENT_VOLUME = "insufficient_volume"
    UNKNOWN_COST = "unknown_cost"
    NON_POSITIVE_NET = "non_positive_net"
    LIMIT_EXCEEDED = "limit_exceeded"


@dataclass(frozen=True, slots=True)
class Cost:
    """Known cost in quote currency; zero must be explicitly supplied."""
    component_id: str
    amount: Decimal
    category: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", to_decimal(self.amount))
        if not self.component_id or not self.category or self.amount < 0:
            raise ValueError("cost requires an id/category and non-negative amount")


@dataclass(frozen=True, slots=True)
class ProfitabilityInput:
    opportunity: ArbitrageOpportunity
    gross_proceeds: Decimal | None
    capital_required: Decimal | None
    trading_costs: tuple[Cost, ...] | None
    transfer_costs: tuple[Cost, ...] | None
    slippage_cost: Decimal | None
    evaluated_at: datetime
    max_quote_age_seconds: Decimal = Decimal("5")
    min_net_profit: Decimal = Decimal("0")
    max_capital: Decimal | None = None

    def __post_init__(self) -> None:
        fields = (
            "gross_proceeds", "capital_required", "slippage_cost",
            "max_quote_age_seconds", "min_net_profit", "max_capital",
        )
        for field in fields:
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, to_decimal(value))
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware")
        if self.max_quote_age_seconds < 0:
            raise ValueError("max_quote_age_seconds cannot be negative")


@dataclass(frozen=True, slots=True)
class ProfitabilityResult:
    accepted: bool
    net_profit: Decimal | None
    rejection_reasons: tuple[RejectionReason, ...]
    total_costs: Decimal | None


def evaluate_profitability(data: ProfitabilityInput) -> ProfitabilityResult:
    if data.trading_costs is None or data.transfer_costs is None or data.slippage_cost is None:
        return ProfitabilityResult(False, None, (RejectionReason.UNKNOWN_COST,), None)
    if data.gross_proceeds is None or data.capital_required is None:
        return ProfitabilityResult(False, None, (RejectionReason.INCOMPLETE_DATA,), None)

    reasons: list[RejectionReason] = []
    if data.gross_proceeds < 0 or data.capital_required < 0 or data.slippage_cost < 0:
        reasons.append(RejectionReason.INCOMPLETE_DATA)

    buy_age = (data.evaluated_at - data.opportunity.buy_quote.observed_at).total_seconds()
    sell_age = (data.evaluated_at - data.opportunity.sell_quote.observed_at).total_seconds()
    if buy_age < 0 or sell_age < 0 or max(buy_age, sell_age) > float(data.max_quote_age_seconds):
        reasons.append(RejectionReason.STALE_QUOTE)

    quantity = data.opportunity.base_quantity
    buy_size = data.opportunity.buy_quote.ask_size
    sell_size = data.opportunity.sell_quote.bid_size
    if buy_size is None or sell_size is None or buy_size < quantity or sell_size < quantity:
        reasons.append(RejectionReason.INSUFFICIENT_VOLUME)

    costs = data.trading_costs + data.transfer_costs
    component_ids = [cost.component_id for cost in costs]
    if len(component_ids) != len(set(component_ids)):
        reasons.append(RejectionReason.INCOMPLETE_DATA)
    total_costs = sum((cost.amount for cost in costs), Decimal("0")) + data.slippage_cost
    if data.max_capital is not None and data.capital_required > data.max_capital:
        reasons.append(RejectionReason.LIMIT_EXCEEDED)

    net = data.gross_proceeds - data.capital_required - total_costs
    if net <= data.min_net_profit:
        reasons.append(RejectionReason.NON_POSITIVE_NET)
    unique_reasons = tuple(dict.fromkeys(reasons))
    return ProfitabilityResult(not unique_reasons, net, unique_reasons, total_costs)


class OpportunityScorer(Protocol):
    def score(self, result: ProfitabilityResult) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class NetProfitScorer:
    def score(self, result: ProfitabilityResult) -> Decimal:
        if not result.accepted or result.net_profit is None:
            return Decimal("-Infinity")
        return result.net_profit


@dataclass(frozen=True, slots=True)
class NetProfitRatioScorer:
    denominator: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "denominator", to_decimal(self.denominator))
        if self.denominator <= 0:
            raise ValueError("denominator must be positive")

    def score(self, result: ProfitabilityResult) -> Decimal:
        if not result.accepted or result.net_profit is None:
            return Decimal("-Infinity")
        return result.net_profit / self.denominator

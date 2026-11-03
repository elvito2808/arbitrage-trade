"""Conservative net-profit evaluation; unknown or cross-currency costs reject."""
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
    """Known cost denominated in the opportunity quote asset."""
    component_id: str
    amount: Decimal
    category: str
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", to_decimal(self.amount))
        if not self.component_id or not self.category or not self.currency:
            raise ValueError("cost id, category and currency are required")
        if self.amount < 0:
            raise ValueError("cost amount cannot be negative")


@dataclass(frozen=True, slots=True)
class ProfitabilityInput:
    opportunity: ArbitrageOpportunity
    trading_costs: tuple[Cost, ...] | None
    transfer_costs: tuple[Cost, ...] | None
    slippage_cost: Cost | None
    evaluated_at: datetime
    max_quote_age_seconds: Decimal = Decimal("5")
    min_net_profit: Decimal = Decimal("0")
    max_capital: Decimal | None = None

    def __post_init__(self) -> None:
        for field in ("max_quote_age_seconds", "min_net_profit", "max_capital"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, to_decimal(value))
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware")
        if self.max_quote_age_seconds < 0 or self.min_net_profit < 0:
            raise ValueError("age and minimum profit limits cannot be negative")
        if self.max_capital is not None and self.max_capital < 0:
            raise ValueError("max_capital cannot be negative")

    @property
    def gross_proceeds(self) -> Decimal:
        return self.opportunity.sell_quote.bid * self.opportunity.base_quantity

    @property
    def capital_required(self) -> Decimal:
        return self.opportunity.buy_quote.ask * self.opportunity.base_quantity


@dataclass(frozen=True, slots=True)
class ProfitabilityResult:
    accepted: bool
    net_profit: Decimal | None
    rejection_reasons: tuple[RejectionReason, ...]
    total_costs: Decimal | None
    capital_required: Decimal


def evaluate_profitability(data: ProfitabilityInput) -> ProfitabilityResult:
    if data.trading_costs is None or data.transfer_costs is None or data.slippage_cost is None:
        return ProfitabilityResult(False, None, (RejectionReason.UNKNOWN_COST,), None, data.capital_required)

    reasons: list[RejectionReason] = []
    quote_currency = data.opportunity.sell_quote.market.quote.symbol
    costs = data.trading_costs + data.transfer_costs + (data.slippage_cost,)
    if any(cost.currency != quote_currency for cost in costs):
        reasons.append(RejectionReason.INCOMPLETE_DATA)

    component_ids = [cost.component_id for cost in costs]
    if len(component_ids) != len(set(component_ids)):
        reasons.append(RejectionReason.INCOMPLETE_DATA)
    if RejectionReason.INCOMPLETE_DATA in reasons:
        # Cross-currency sums and duplicate components have no meaningful total.
        return ProfitabilityResult(
            False, None, tuple(dict.fromkeys(reasons)), None, data.capital_required
        )
    total_costs = sum((cost.amount for cost in costs), Decimal("0"))

    buy_age = (data.evaluated_at - data.opportunity.buy_quote.observed_at).total_seconds()
    sell_age = (data.evaluated_at - data.opportunity.sell_quote.observed_at).total_seconds()
    if buy_age < 0 or sell_age < 0 or max(buy_age, sell_age) > float(data.max_quote_age_seconds):
        reasons.append(RejectionReason.STALE_QUOTE)

    quantity = data.opportunity.base_quantity
    buy_size = data.opportunity.buy_quote.ask_size
    sell_size = data.opportunity.sell_quote.bid_size
    if buy_size is None or sell_size is None or buy_size < quantity or sell_size < quantity:
        reasons.append(RejectionReason.INSUFFICIENT_VOLUME)

    if data.max_capital is not None and data.capital_required > data.max_capital:
        reasons.append(RejectionReason.LIMIT_EXCEEDED)

    net = data.gross_proceeds - data.capital_required - total_costs
    if net <= data.min_net_profit:
        reasons.append(RejectionReason.NON_POSITIVE_NET)
    unique_reasons = tuple(dict.fromkeys(reasons))
    return ProfitabilityResult(
        not unique_reasons, net, unique_reasons, total_costs, data.capital_required
    )


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
    def score(self, result: ProfitabilityResult) -> Decimal:
        if (
            not result.accepted
            or result.net_profit is None
            or result.capital_required is None
            or result.capital_required <= 0
        ):
            return Decimal("-Infinity")
        return result.net_profit / result.capital_required

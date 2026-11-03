from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from arbitrage_trade.domain import (
    ArbitrageOpportunity,
    Asset,
    Market,
    Order,
    OrderStatus,
    PriceQuote,
    TradeResult,
)
from arbitrage_trade.economics import (
    Cost,
    NetProfitScorer,
    ProfitabilityInput,
    RejectionReason,
    evaluate_profitability,
)

NOW = datetime(2026, 11, 3, tzinfo=UTC)
QUOTE = "USDT"


def setup_opportunity(*, age=0, ask_size="5", bid_size="5", sell_bid="102"):
    base, quote = Asset("BTC"), Asset(QUOTE)
    buy_market = Market("cex-a", "BTC-USDT", base, quote, "spot")
    sell_market = Market("cex-b", "BTC-USDT", base, quote, "spot")
    buy = PriceQuote(
        buy_market, "99", "100", NOW - timedelta(seconds=age), ask_size=ask_size
    )
    sell = PriceQuote(
        sell_market, sell_bid, "103", NOW - timedelta(seconds=age), bid_size=bid_size
    )
    return ArbitrageOpportunity(buy, sell, Decimal("1"), NOW, "opp-1")


def valid_input(**overrides):
    values = dict(
        opportunity=setup_opportunity(),
        trading_costs=(
            Cost("buy-fee", "0.1", "trading", QUOTE),
            Cost("sell-fee", "0.1", "trading", QUOTE),
        ),
        transfer_costs=(Cost("network-fee", "0.2", "transfer", QUOTE),),
        slippage_cost=Cost("slippage", "0.3", "slippage", QUOTE),
        evaluated_at=NOW,
    )
    values.update(overrides)
    return ProfitabilityInput(**values)


def test_domain_models_validate_and_preserve_optional_decimals():
    asset = Asset("TOK", chain_id=32769)
    assert asset.decimals is None
    market = Market("venue", "TOK-USD", asset, Asset("USD"), "spot")
    order = Order("o1", market, "buy", "2", OrderStatus.PENDING)
    result = TradeResult(order, "1", "10", "0.01")
    assert result.filled_quantity == Decimal("1")
    with pytest.raises(ValueError):
        Asset("TOK", decimals=256)


def test_net_profit_is_derived_from_quotes_and_explicit_costs():
    data = valid_input()
    result = evaluate_profitability(data)
    assert data.gross_proceeds == Decimal("102")
    assert data.capital_required == Decimal("100")
    assert result.accepted
    assert result.net_profit == Decimal("1.3")
    assert result.total_costs == Decimal("0.7")


def test_unknown_fee_or_slippage_never_defaults_to_zero():
    for kwargs in (
        {"trading_costs": None},
        {"transfer_costs": None},
        {"slippage_cost": None},
    ):
        result = evaluate_profitability(valid_input(**kwargs))
        assert not result.accepted
        assert RejectionReason.UNKNOWN_COST in result.rejection_reasons


def test_stale_quotes_are_rejected():
    result = evaluate_profitability(valid_input(opportunity=setup_opportunity(age=6)))
    assert RejectionReason.STALE_QUOTE in result.rejection_reasons


def test_insufficient_or_unknown_volume_is_rejected():
    for opportunity in (
        setup_opportunity(ask_size="0.5"),
        setup_opportunity(ask_size=None),
    ):
        result = evaluate_profitability(valid_input(opportunity=opportunity))
        assert RejectionReason.INSUFFICIENT_VOLUME in result.rejection_reasons


def test_duplicate_fee_component_is_rejected_to_prevent_double_counting():
    fee = Cost("same", "0.1", "trading", QUOTE)
    result = evaluate_profitability(valid_input(trading_costs=(fee,), transfer_costs=(fee,)))
    assert RejectionReason.INCOMPLETE_DATA in result.rejection_reasons


def test_cross_currency_cost_is_rejected():
    fee = Cost("foreign-fee", "0.1", "trading", "BTC")
    result = evaluate_profitability(valid_input(trading_costs=(fee,)))
    assert RejectionReason.INCOMPLETE_DATA in result.rejection_reasons


def test_non_positive_net_and_capital_limit_are_rejected():
    loss = evaluate_profitability(valid_input(opportunity=setup_opportunity(sell_bid="99")))
    assert RejectionReason.NON_POSITIVE_NET in loss.rejection_reasons
    limit = evaluate_profitability(valid_input(max_capital="50"))
    assert RejectionReason.LIMIT_EXCEEDED in limit.rejection_reasons


def test_ranker_only_scores_accepted_opportunities():
    accepted = evaluate_profitability(valid_input())
    rejected = evaluate_profitability(
        valid_input(opportunity=setup_opportunity(sell_bid="99"))
    )
    scorer = NetProfitScorer()
    assert scorer.score(accepted) == Decimal("1.3")
    assert scorer.score(rejected).is_infinite()


def test_profitability_limits_must_be_non_negative():
    with pytest.raises(ValueError):
        valid_input(min_net_profit="-1")
    with pytest.raises(ValueError):
        valid_input(max_capital="-1")

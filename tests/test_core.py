import pytest

from arbitrage_trade.core import MarketQuote, to_decimal


def test_decimal_conversion_is_exact():
    assert to_decimal("0.1") + to_decimal("0.2") == to_decimal("0.3")


def test_float_is_rejected():
    with pytest.raises(TypeError):
        to_decimal(0.1)


def test_quote_spread():
    quote = MarketQuote("BTC-USDT", "99", "101")
    assert quote.spread == to_decimal("2")
    assert quote.spread_percent == to_decimal("200") / to_decimal("101")


def test_inverted_quote_is_rejected():
    with pytest.raises(ValueError):
        MarketQuote("BTC-USDT", "101", "99")


from arbitrage_trade.core import SwapQuote


def test_swap_quote_preserves_raw_token_units():
    quote = SwapQuote(
        token_in="0x" + "1" * 40,
        token_out="0x" + "2" * 40,
        amount_in=10**18,
        amount_out=250_000_000,
        chain_id=32769,
        source="plunderswap",
        timestamp_ms=1,
    )
    assert quote.amount_in == 10**18
    assert quote.amount_out == 250_000_000


def test_swap_quote_rejects_non_positive_amounts():
    with pytest.raises(ValueError):
        SwapQuote("A", "B", 0, 10, 32769, "test", 1)


def test_decimal_rejects_boolean_and_non_finite_values():
    with pytest.raises(TypeError):
        to_decimal(True)
    with pytest.raises(ValueError):
        to_decimal("NaN")
    with pytest.raises(ValueError):
        to_decimal("Infinity")

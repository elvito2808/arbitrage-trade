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

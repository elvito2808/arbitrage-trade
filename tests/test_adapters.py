import json

import pytest

from arbitrage_trade.adapters.kucoin import AdapterError, KuCoinAdapter
from arbitrage_trade.adapters.plunderswap import (
    PlunderSwapAdapter,
    PlunderSwapConfig,
    PlunderSwapRPCError,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def test_kucoin_parses_public_level_one_ticker(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse({
            "code": "200000",
            "data": {"bestBid": "99.25", "bestAsk": "99.50", "time": 123456},
        })

    monkeypatch.setattr("arbitrage_trade.adapters.kucoin.urlopen", fake_urlopen)
    quote = KuCoinAdapter(timeout=3).get_quote("btc/usdt")

    assert quote.symbol == "BTC-USDT"
    assert str(quote.bid) == "99.25"
    assert str(quote.ask) == "99.50"
    assert quote.timestamp_ms == 123456
    assert "symbol=BTC-USDT" in captured["url"]
    assert captured["timeout"] == 3


def test_kucoin_rejects_api_error(monkeypatch):
    monkeypatch.setattr(
        "arbitrage_trade.adapters.kucoin.urlopen",
        lambda *args, **kwargs: FakeResponse({"code": "400100", "msg": "bad symbol"}),
    )
    with pytest.raises(AdapterError):
        KuCoinAdapter().get_quote("NOT-A-PAIR")


def test_kucoin_rejects_empty_symbol():
    with pytest.raises(ValueError):
        KuCoinAdapter().get_quote("  ")


def _abi_amounts(values):
    # ABI encoding for uint256[] return: offset, length, elements.
    return "0x" + f"{32:064x}" + f"{len(values):064x}" + "".join(
        f"{value:064x}" for value in values
    )


def test_plunderswap_v2_quote_is_read_only_and_decodes_raw_units():
    calls = []

    def rpc(method, params):
        calls.append((method, params))
        if method == "eth_chainId":
            return "0x8001"
        if method == "eth_call":
            return _abi_amounts([10**18, 250_000_000])
        raise AssertionError(f"Unexpected RPC method: {method}")

    adapter = PlunderSwapAdapter(rpc_transport=rpc)
    quote = adapter.get_quote(
        "0x" + "1" * 40,
        "0x" + "2" * 40,
        "1000000000000000000",
    )

    assert quote.amount_in == 10**18
    assert quote.amount_out == 250_000_000
    assert quote.chain_id == 32769
    assert quote.source == "plunderswap"
    assert [method for method, _ in calls] == ["eth_chainId", "eth_call"]
    assert calls[1][1][0]["to"] == adapter.config.router_address
    assert calls[1][1][1] == "latest"


def test_plunderswap_rejects_wrong_chain_before_quote():
    adapter = PlunderSwapAdapter(rpc_transport=lambda method, params: "0x1")
    with pytest.raises(PlunderSwapRPCError, match="Wrong network"):
        adapter.get_quote("0x" + "1" * 40, "0x" + "2" * 40, "1")


@pytest.mark.parametrize(
    "token_in,token_out,amount",
    [
        ("bad", "0x" + "2" * 40, "1"),
        ("0x" + "1" * 40, "0x" + "1" * 40, "1"),
        ("0x" + "1" * 40, "0x" + "2" * 40, "1.5"),
        ("0x" + "1" * 40, "0x" + "2" * 40, "0"),
    ],
)
def test_plunderswap_rejects_invalid_quote_inputs(token_in, token_out, amount):
    adapter = PlunderSwapAdapter(rpc_transport=lambda method, params: "0x8001")
    with pytest.raises(ValueError):
        adapter.get_quote(token_in, token_out, amount)


def test_plunderswap_config_validates_addresses():
    with pytest.raises(ValueError):
        PlunderSwapConfig(router_address="not-an-address")


def test_plunderswap_rejects_malformed_abi_result():
    adapter = PlunderSwapAdapter(rpc_transport=lambda method, params: (
        "0x8001" if method == "eth_chainId" else "0x1234"
    ))
    with pytest.raises(PlunderSwapRPCError, match="truncated"):
        adapter.get_quote("0x" + "1" * 40, "0x" + "2" * 40, "1")


def test_kucoin_retries_transient_network_failure(monkeypatch):
    from urllib.error import URLError

    calls = {"count": 0}

    def flaky_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise URLError("temporary disconnect")
        return FakeResponse({
            "code": "200000",
            "data": {"bestBid": "10", "bestAsk": "11", "time": 123},
        })

    monkeypatch.setattr("arbitrage_trade.adapters.kucoin.urlopen", flaky_urlopen)
    quote = KuCoinAdapter(retry_attempts=2, retry_base_delay=0).get_quote("AAA-USDT")
    assert quote.bid == 10
    assert calls["count"] == 2


def test_plunderswap_retries_transient_network_failure(monkeypatch):
    from urllib.error import URLError

    calls = {"count": 0}

    def flaky_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise URLError("temporary disconnect")
        body = json.loads(request.data.decode())
        if body["method"] == "eth_chainId":
            return FakeResponse({"jsonrpc": "2.0", "id": 1, "result": "0x8001"})
        return FakeResponse({
            "jsonrpc": "2.0",
            "id": 1,
            "result": _abi_amounts([1, 2]),
        })

    monkeypatch.setattr("arbitrage_trade.adapters.plunderswap.urlopen", flaky_urlopen)
    adapter = PlunderSwapAdapter(
        config=PlunderSwapConfig(retry_attempts=2, retry_base_delay=0)
    )
    quote = adapter.get_quote("0x" + "1" * 40, "0x" + "2" * 40, "1")
    assert quote.amount_out == 2
    assert calls["count"] == 3

import json

import pytest

from arbitrage_trade.adapters.kucoin import (
    AdapterError,
    KuCoinAdapter,
    map_market_quote_to_price_quote,
)
from arbitrage_trade.adapters.plunderswap import (
    PlunderSwapAdapter,
    PlunderSwapConfig,
    PlunderSwapRPCError,
)
from arbitrage_trade.core import MarketQuote
from arbitrage_trade.domain import Asset, Market


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
            "data": {
                "bestBid": "99.25",
                "bestAsk": "99.50",
                "bestBidSize": "2.5",
                "bestAskSize": "3.5",
                "time": 123456,
            },
        })

    monkeypatch.setattr("arbitrage_trade.adapters.kucoin.urlopen", fake_urlopen)
    quote = KuCoinAdapter(timeout=3).get_quote("btc/usdt")

    assert quote.symbol == "BTC-USDT"
    assert str(quote.bid) == "99.25"
    assert str(quote.ask) == "99.50"
    assert quote.timestamp_ms == 123456
    assert quote.bid_size == 2.5
    assert quote.ask_size == 3.5
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


@pytest.mark.parametrize(
    "result",
    [
        "0x" + "g" * 256,
        "0x" + f"{64:064x}" + f"{2:064x}" + f"{1:064x}" + f"{2:064x}",
        "0x" + f"{32:064x}" + f"{1:064x}" + f"{1:064x}" + f"{2:064x}",
        "0x" + f"{32:064x}" + f"{2:064x}" + f"{1:064x}" + f"{2:064x}" + f"{3:064x}",
    ],
)
def test_plunderswap_rejects_noncanonical_or_non_hex_abi_data(result):
    with pytest.raises(PlunderSwapRPCError):
        PlunderSwapAdapter._decode_amounts_out(result)


@pytest.mark.parametrize(
    "envelope",
    [
        {"jsonrpc": "1.0", "id": 1, "result": "0x8001"},
        {"jsonrpc": "2.0", "id": 2, "result": "0x8001"},
    ],
)
def test_plunderswap_rejects_mismatched_json_rpc_envelope(monkeypatch, envelope):
    monkeypatch.setattr(
        "arbitrage_trade.adapters.plunderswap.urlopen",
        lambda *args, **kwargs: FakeResponse(envelope),
    )
    adapter = PlunderSwapAdapter()
    with pytest.raises(PlunderSwapRPCError, match="invalid version or request id"):
        adapter._rpc("eth_chainId", [])


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



def test_plunderswap_reads_bytecode_and_token_decimals():
    calls = []

    def rpc(method, params):
        calls.append((method, params))
        if method == "eth_getCode":
            return "0x60006000"
        if method == "eth_call":
            return "0x" + f"{18:064x}"
        raise AssertionError(f"Unexpected RPC method: {method}")

    adapter = PlunderSwapAdapter(rpc_transport=rpc)
    address = "0x" + "1" * 40
    assert adapter.get_contract_code(address) == "0x60006000"
    assert adapter.get_token_decimals(address) == 18
    assert calls[0][0] == "eth_getCode"
    assert calls[1][1][0]["data"] == "0x313ce567"


def test_plunderswap_rejects_invalid_decimals_response():
    adapter = PlunderSwapAdapter(rpc_transport=lambda method, params: "0x12")
    with pytest.raises(PlunderSwapRPCError, match="malformed ABI"):
        adapter.get_token_decimals("0x" + "1" * 40)


def test_kucoin_rejects_invalid_ticker_payload(monkeypatch):
    monkeypatch.setattr(
        "arbitrage_trade.adapters.kucoin.urlopen",
        lambda *args, **kwargs: FakeResponse({
            "code": "200000",
            "data": {"bestBid": "not-a-price", "bestAsk": "1", "time": "bad"},
        }),
    )
    with pytest.raises(AdapterError):
        KuCoinAdapter().get_quote("AAA-USDT")


def test_plunderswap_verifies_configured_v2_deployments_read_only():
    methods = []

    def rpc(method, params):
        methods.append(method)
        if method == "eth_chainId":
            return "0x8001"
        if method == "eth_getCode":
            return "0x60006000"
        raise AssertionError(f"Unexpected RPC method: {method}")

    adapter = PlunderSwapAdapter(rpc_transport=rpc)
    assert adapter.check_deployment_code_presence() == {"router": True, "factory": True}
    assert methods == ["eth_chainId", "eth_getCode", "eth_getCode"]


def test_plunderswap_deployment_check_rejects_empty_bytecode():
    def rpc(method, params):
        if method == "eth_chainId":
            return "0x8001"
        return "0x"

    adapter = PlunderSwapAdapter(rpc_transport=rpc)
    with pytest.raises(PlunderSwapRPCError, match="no deployed bytecode"):
        adapter.check_deployment_code_presence()


@pytest.mark.parametrize("bytecode", ["0xzz", "0x600", "0x12xz", ""])
def test_plunderswap_rejects_malformed_bytecode_hex(bytecode):
    adapter = PlunderSwapAdapter(rpc_transport=lambda method, params: bytecode)
    with pytest.raises(PlunderSwapRPCError, match="malformed bytecode hex"):
        adapter.get_contract_code("0x" + "1" * 40)


def test_kucoin_mapper_requires_timestamp_and_both_sizes():
    market = Market("kucoin", "BTC-USDT", Asset("BTC"), Asset("USDT"), "spot")
    missing_time = MarketQuote("BTC-USDT", "99", "100", bid_size="2", ask_size="3")
    with pytest.raises(AdapterError, match="timestamp"):
        map_market_quote_to_price_quote(missing_time, market)
    missing_size = MarketQuote("BTC-USDT", "99", "100", timestamp_ms=123, bid_size="2")
    with pytest.raises(AdapterError, match="size"):
        map_market_quote_to_price_quote(missing_size, market)


def test_kucoin_mapper_creates_domain_price_quote():
    market = Market("kucoin", "BTC-USDT", Asset("BTC"), Asset("USDT"), "spot")
    source = MarketQuote(
        "BTC-USDT", "99", "100", timestamp_ms=1_000,
        bid_size="2", ask_size="3", source="kucoin",
    )
    quote = map_market_quote_to_price_quote(source, market)
    assert quote.market is market
    assert str(quote.bid) == "99"
    assert str(quote.ask_size) == "3"
    assert quote.observed_at.timestamp() == 1


def test_plunderswap_rpc_method_allowlist_blocks_write_methods():
    adapter = PlunderSwapAdapter(rpc_transport=lambda method, params: "unexpected")
    with pytest.raises(ValueError, match="not allowed"):
        adapter._rpc("eth_sendRawTransaction", ["0xdead"])
    assert PlunderSwapAdapter.ALLOWED_RPC_METHODS == {
        "eth_chainId", "eth_getCode", "eth_call"
    }


def test_plunderswap_json_rpc_error_is_not_mistaken_for_result(monkeypatch):
    monkeypatch.setattr(
        "arbitrage_trade.adapters.plunderswap.urlopen",
        lambda *args, **kwargs: FakeResponse({
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32000, "message": "execution reverted"},
        }),
    )
    with pytest.raises(PlunderSwapRPCError, match="execution reverted"):
        PlunderSwapAdapter()._rpc("eth_call", [])


@pytest.mark.parametrize("status", [429, 500, 503])
def test_plunderswap_retries_http_429_and_5xx(monkeypatch, status):
    from urllib.error import HTTPError

    calls = {"count": 0}

    def flaky(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError(request.full_url, status, "temporary", {}, None)
        return FakeResponse({"jsonrpc": "2.0", "id": 1, "result": "0x8001"})

    monkeypatch.setattr("arbitrage_trade.adapters.plunderswap.urlopen", flaky)
    adapter = PlunderSwapAdapter(config=PlunderSwapConfig(retry_attempts=2, retry_base_delay=0))
    assert adapter._rpc("eth_chainId", []) == "0x8001"
    assert calls["count"] == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_plunderswap_does_not_retry_http_4xx(monkeypatch, status):
    from urllib.error import HTTPError

    calls = {"count": 0}

    def failing(request, timeout):
        calls["count"] += 1
        raise HTTPError(request.full_url, status, "client error", {}, None)

    monkeypatch.setattr("arbitrage_trade.adapters.plunderswap.urlopen", failing)
    adapter = PlunderSwapAdapter(config=PlunderSwapConfig(retry_attempts=3, retry_base_delay=0))
    with pytest.raises(PlunderSwapRPCError, match=f"HTTP {status}"):
        adapter._rpc("eth_chainId", [])
    assert calls["count"] == 1


@pytest.mark.parametrize("status", [429, 500, 503])
def test_kucoin_retries_http_429_and_5xx(monkeypatch, status):
    from urllib.error import HTTPError

    calls = {"count": 0}

    def flaky(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError(request.full_url, status, "temporary", {}, None)
        return FakeResponse({
            "code": "200000",
            "data": {"bestBid": "10", "bestAsk": "11", "time": 123},
        })

    monkeypatch.setattr("arbitrage_trade.adapters.kucoin.urlopen", flaky)
    quote = KuCoinAdapter(retry_attempts=2, retry_base_delay=0).get_quote("AAA-USDT")
    assert quote.bid == 10
    assert calls["count"] == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_kucoin_does_not_retry_http_4xx(monkeypatch, status):
    from urllib.error import HTTPError

    calls = {"count": 0}

    def failing(request, timeout):
        calls["count"] += 1
        raise HTTPError(request.full_url, status, "client error", {}, None)

    monkeypatch.setattr("arbitrage_trade.adapters.kucoin.urlopen", failing)
    with pytest.raises(AdapterError, match=f"HTTP {status}"):
        KuCoinAdapter(retry_attempts=3, retry_base_delay=0).get_quote("AAA-USDT")
    assert calls["count"] == 1


def test_kucoin_mapper_rejects_market_venue_and_asset_symbol_mismatch():
    quote = MarketQuote(
        "BTC-USDT", "99", "100", timestamp_ms=1_000,
        bid_size="2", ask_size="3", source="kucoin",
    )
    wrong_venue = Market("other", "BTC-USDT", Asset("BTC"), Asset("USDT"), "spot")
    wrong_base = Market("kucoin", "ETH-USDT", Asset("ETH"), Asset("USDT"), "spot")
    wrong_quote = Market("kucoin", "BTC-USDC", Asset("BTC"), Asset("USDC"), "spot")
    with pytest.raises(AdapterError, match="venue"):
        map_market_quote_to_price_quote(quote, wrong_venue)
    with pytest.raises(AdapterError, match="base/quote"):
        map_market_quote_to_price_quote(quote, wrong_base)
    with pytest.raises(AdapterError, match="base/quote"):
        map_market_quote_to_price_quote(quote, wrong_quote)


@pytest.mark.parametrize("timestamp_ms", [0, -1, 10**30])
def test_kucoin_mapper_rejects_invalid_timestamp(timestamp_ms):
    market = Market("kucoin", "BTC-USDT", Asset("BTC"), Asset("USDT"), "spot")
    quote = MarketQuote(
        "BTC-USDT", "99", "100", timestamp_ms=timestamp_ms,
        bid_size="2", ask_size="3", source="kucoin",
    )
    with pytest.raises(AdapterError, match="timestamp"):
        map_market_quote_to_price_quote(quote, market)


def test_kucoin_get_quote_to_domain_price_quote_end_to_end(monkeypatch):
    monkeypatch.setattr(
        "arbitrage_trade.adapters.kucoin.urlopen",
        lambda *args, **kwargs: FakeResponse({
            "code": "200000",
            "data": {
                "bestBid": "99.25",
                "bestAsk": "99.50",
                "bestBidSize": "2.5",
                "bestAskSize": "3.5",
                "time": 1_700_000_000_000,
            },
        }),
    )
    market = Market("kucoin", "BTC-USDT", Asset("BTC"), Asset("USDT"), "spot")
    raw_quote = KuCoinAdapter().get_quote("BTC-USDT")
    domain_quote = map_market_quote_to_price_quote(raw_quote, market)
    assert domain_quote.market is market
    assert domain_quote.bid_size == 2.5
    assert domain_quote.ask_size == 3.5
    assert domain_quote.observed_at.timestamp() == 1_700_000_000


def test_plunderswap_rejects_json_rpc_response_without_result(monkeypatch):
    monkeypatch.setattr(
        "arbitrage_trade.adapters.plunderswap.urlopen",
        lambda *args, **kwargs: FakeResponse({"jsonrpc": "2.0", "id": 1}),
    )
    with pytest.raises(PlunderSwapRPCError, match="no result"):
        PlunderSwapAdapter()._rpc("eth_chainId", [])


@pytest.mark.parametrize("payload", [None, [], "not-an-object", 42])
def test_plunderswap_rejects_non_object_json_rpc_payload(monkeypatch, payload):
    monkeypatch.setattr(
        "arbitrage_trade.adapters.plunderswap.urlopen",
        lambda *args, **kwargs: FakeResponse(payload),
    )
    with pytest.raises(PlunderSwapRPCError, match="must be an object"):
        PlunderSwapAdapter()._rpc("eth_chainId", [])


@pytest.mark.parametrize("status", [429, 500, 503])
def test_plunderswap_http_retry_exhaustion_is_bounded(monkeypatch, status):
    from urllib.error import HTTPError

    calls = {"count": 0}

    def always_failing(request, timeout):
        calls["count"] += 1
        raise HTTPError(request.full_url, status, "still unavailable", {}, None)

    monkeypatch.setattr("arbitrage_trade.adapters.plunderswap.urlopen", always_failing)
    adapter = PlunderSwapAdapter(
        config=PlunderSwapConfig(retry_attempts=2, retry_base_delay=0)
    )
    with pytest.raises(PlunderSwapRPCError, match="TransientHTTPError"):
        adapter._rpc("eth_chainId", [])
    assert calls["count"] == 2

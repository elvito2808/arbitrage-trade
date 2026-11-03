import pytest

from arbitrage_trade.adapters.plunderswap import (
    AdapterNotConfigured,
    PlunderSwapAdapter,
    PlunderSwapConfig,
)


def test_plunderswap_requires_verified_configuration():
    adapter = PlunderSwapAdapter()
    with pytest.raises(AdapterNotConfigured):
        adapter.get_quote("0x" + "1" * 40, "0x" + "2" * 40, "1")


def test_plunderswap_config_validates_network_and_addresses():
    config = PlunderSwapConfig(
        rpc_url="https://rpc.example.invalid",
        chain_id=32769,
        router_address="0x" + "a" * 40,
    )
    assert config.chain_id == 32769


def test_plunderswap_rejects_malformed_router_address():
    with pytest.raises(ValueError):
        PlunderSwapConfig(
            rpc_url="https://rpc.example.invalid",
            chain_id=1,
            router_address="not-an-address",
        )

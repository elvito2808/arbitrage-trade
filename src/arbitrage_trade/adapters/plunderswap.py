"""PlunderSwap/Zilliqa EVM adapter boundary.

The deployment addresses and supported router version must be supplied from
verified official deployment metadata. This adapter intentionally refuses to
invent addresses or return fabricated quotes.
"""

from dataclasses import dataclass


class AdapterNotConfigured(RuntimeError):
    """Raised until verified chain and contract metadata is provided."""


@dataclass(frozen=True, slots=True)
class PlunderSwapConfig:
    rpc_url: str
    chain_id: int
    router_address: str
    factory_address: str | None = None

    def __post_init__(self) -> None:
        if not self.rpc_url.startswith(("https://", "http://")):
            raise ValueError("rpc_url must be an HTTP(S) endpoint")
        if self.chain_id <= 0:
            raise ValueError("chain_id must be positive")
        for label, address in (("router", self.router_address), ("factory", self.factory_address)):
            if address is not None and (
                len(address) != 42 or not address.startswith("0x")
            ):
                raise ValueError(f"{label}_address must be a 20-byte hex address")


class PlunderSwapAdapter:
    name = "plunderswap"

    def __init__(self, config: PlunderSwapConfig | None = None) -> None:
        self.config = config

    def get_quote(self, token_in: str, token_out: str, amount_in: str):
        if self.config is None:
            raise AdapterNotConfigured(
                "Provide verified Zilliqa EVM RPC, chain ID and PlunderSwap router metadata"
            )
        raise AdapterNotConfigured(
            "Quote execution is pending verified ABI/router selection and read-only RPC tests"
        )

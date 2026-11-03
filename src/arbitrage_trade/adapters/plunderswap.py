"""Read-only PlunderSwap v2 quote adapter for Zilliqa EVM.

Only JSON-RPC eth_chainId and eth_call are used. No wallet, private key,
transaction submission, signing, token approval, or transfer path exists.
The router address and network defaults are copied from PlunderSwap's official
developer documentation; callers can override them for controlled environments.
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..core import SwapQuote
from ..resilience import TransientHTTPError, retry_call


class AdapterNotConfigured(RuntimeError):
    """Raised when verified deployment metadata is not available."""


class PlunderSwapRPCError(RuntimeError):
    """Raised when the public JSON-RPC endpoint returns an error."""


_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_UINT_RE = re.compile(r"^[0-9]+$")
# Uniswap-v2-compatible selector: getAmountsOut(uint256,address[])
_GET_AMOUNTS_OUT_SELECTOR = "d06ca61f"


@dataclass(frozen=True, slots=True)
class PlunderSwapConfig:
    rpc_url: str = "https://api.zilliqa.com"
    chain_id: int = 32769
    router_address: str = "0x33C6a20D2a605da9Fd1F506ddEd449355f0564fe"
    factory_address: str = "0xf42d1058f233329185A36B04B7f96105afa1adD2"
    timeout: float = 10.0
    retry_attempts: int = 3
    retry_base_delay: float = 0.1

    def __post_init__(self) -> None:
        if not self.rpc_url.startswith(("https://", "http://")):
            raise ValueError("rpc_url must be an HTTP(S) endpoint")
        if self.chain_id <= 0:
            raise ValueError("chain_id must be positive")
        if not _ADDRESS_RE.fullmatch(self.router_address):
            raise ValueError("router_address must be a 20-byte hex address")
        if not _ADDRESS_RE.fullmatch(self.factory_address):
            raise ValueError("factory_address must be a 20-byte hex address")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.retry_attempts < 1 or self.retry_base_delay < 0:
            raise ValueError("invalid retry configuration")


RPCTransport = Callable[[str, list[Any]], Any]


class PlunderSwapAdapter:
    name = "plunderswap"

    def __init__(
        self,
        config: PlunderSwapConfig | None = None,
        rpc_transport: RPCTransport | None = None,
    ) -> None:
        self.config = config or PlunderSwapConfig()
        self._rpc_transport = rpc_transport

    @property
    def chain_id(self) -> int:
        return self.config.chain_id

    def _rpc(self, method: str, params: list[Any]) -> Any:
        if self._rpc_transport is not None:
            return self._rpc_transport(method, params)
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        ).encode("utf-8")
        request = Request(
            self.config.rpc_url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        def read_payload():
            try:
                with urlopen(request, timeout=self.config.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code == 429 or 500 <= exc.code <= 599:
                    raise TransientHTTPError(f"JSON-RPC HTTP {exc.code}") from exc
                raise PlunderSwapRPCError(f"JSON-RPC HTTP {exc.code}") from exc

        try:
            payload = retry_call(
                read_payload,
                retryable=(TransientHTTPError, URLError, TimeoutError, OSError),
                max_attempts=self.config.retry_attempts,
                base_delay=self.config.retry_base_delay,
            )
        except PlunderSwapRPCError:
            raise
        except (TransientHTTPError, URLError, TimeoutError, OSError,
                UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlunderSwapRPCError(
                f"Zilliqa JSON-RPC request failed: {type(exc).__name__}"
            ) from exc
        if not isinstance(payload, dict):
            raise PlunderSwapRPCError("JSON-RPC response must be an object")
        if payload.get("error"):
            error = payload["error"]
            message = (
                error.get("message", "unknown RPC error")
                if isinstance(error, dict)
                else "unknown RPC error"
            )
            raise PlunderSwapRPCError(f"JSON-RPC {method} failed: {message}")
        if "result" not in payload:
            raise PlunderSwapRPCError(f"JSON-RPC {method} response has no result")
        return payload["result"]

    def get_contract_code(self, address: str) -> str:
        """Return deployed bytecode via eth_getCode; empty code means no contract."""
        address = self._validate_address(address, "address")
        code = self._rpc("eth_getCode", [address, "latest"])
        if not isinstance(code, str) or not code.startswith("0x") or len(code) % 2:
            raise PlunderSwapRPCError("eth_getCode returned malformed bytecode")
        return code

    def get_token_decimals(self, token_address: str) -> int:
        """Read ERC-20 decimals without converting any quote amounts."""
        token_address = self._validate_address(token_address, "token_address")
        result = self._rpc(
            "eth_call",
            [{"to": token_address, "data": "0x313ce567"}, "latest"],
        )
        if not isinstance(result, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", result):
            raise PlunderSwapRPCError("decimals() returned malformed ABI data")
        decimals = int(result, 16)
        if decimals > 255:
            raise PlunderSwapRPCError("decimals() returned a value outside uint8")
        return decimals

    @staticmethod
    def _validate_address(value: str, label: str) -> str:
        if not isinstance(value, str) or not _ADDRESS_RE.fullmatch(value):
            raise ValueError(f"{label} must be a 20-byte 0x-prefixed hex address")
        return value

    @staticmethod
    def _encode_get_amounts_out(amount_in: int, token_in: str, token_out: str) -> str:
        # ABI: selector + amountIn + offset-to-path + array length + address words.
        path = [token_in, token_out]
        words = [f"{amount_in:064x}", f"{64:064x}", f"{len(path):064x}"]
        words.extend(address[2:].lower().rjust(64, "0") for address in path)
        return "0x" + _GET_AMOUNTS_OUT_SELECTOR + "".join(words)

    @staticmethod
    def _decode_amounts_out(result: str) -> list[int]:
        if not isinstance(result, str) or not result.startswith("0x"):
            raise PlunderSwapRPCError("eth_call returned malformed ABI data")
        raw = result[2:]
        if len(raw) % 64 or len(raw) < 128:
            raise PlunderSwapRPCError("eth_call returned truncated ABI data")
        try:
            offset = int(raw[:64], 16)
            if offset % 32:
                raise ValueError("unaligned ABI offset")
            start = offset * 2
            length = int(raw[start : start + 64], 16)
            values_start = start + 64
            values_end = values_start + length * 64
            if length < 2 or values_end > len(raw):
                raise ValueError("invalid ABI array length")
            return [int(raw[i : i + 64], 16) for i in range(values_start, values_end, 64)]
        except (ValueError, IndexError) as exc:
            raise PlunderSwapRPCError("eth_call returned invalid getAmountsOut ABI data") from exc

    def get_quote(self, token_in: str, token_out: str, amount_in: str) -> SwapQuote:
        token_in = self._validate_address(token_in, "token_in")
        token_out = self._validate_address(token_out, "token_out")
        if token_in.lower() == token_out.lower():
            raise ValueError("token_in and token_out must be different")
        if not isinstance(amount_in, str) or not _UINT_RE.fullmatch(amount_in):
            raise ValueError("amount_in must be a positive integer string in raw token units")
        raw_amount_in = int(amount_in)
        if raw_amount_in <= 0 or raw_amount_in >= 2**256:
            raise ValueError("amount_in must fit uint256 and be positive")

        actual_chain_id = self._rpc("eth_chainId", [])
        try:
            actual_chain_id_int = (
                int(actual_chain_id, 16)
                if isinstance(actual_chain_id, str)
                else int(actual_chain_id)
            )
        except (TypeError, ValueError) as exc:
            raise PlunderSwapRPCError("eth_chainId returned an invalid value") from exc
        if actual_chain_id_int != self.config.chain_id:
            raise PlunderSwapRPCError(
                "Wrong network: "
                f"configured chain_id={self.config.chain_id}, "
                f"RPC chain_id={actual_chain_id_int}"
            )

        calldata = self._encode_get_amounts_out(raw_amount_in, token_in, token_out)
        result = self._rpc(
            "eth_call",
            [{"to": self.config.router_address, "data": calldata}, "latest"],
        )
        amounts = self._decode_amounts_out(result)
        if len(amounts) != 2 or amounts[0] != raw_amount_in or amounts[1] <= 0:
            raise PlunderSwapRPCError("Router returned an unexpected exact-input quote")
        return SwapQuote(
            token_in=token_in,
            token_out=token_out,
            amount_in=amounts[0],
            amount_out=amounts[1],
            chain_id=actual_chain_id_int,
            source=self.name,
            timestamp_ms=int(time.time() * 1000),
        )

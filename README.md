# Arbitrage Trade

Python foundation for read-only centralized-exchange and DEX market analysis.

## Implemented foundation

- Decimal-only CEX price primitives and explicit raw-unit DEX quote records.
- Typed CEX, DEX, and network adapter protocols.
- KuCoin Spot level-1 best bid/ask adapter using its public unauthenticated REST endpoint.
- PlunderSwap V2 exact-input quote adapter using Zilliqa EVM JSON-RPC `eth_chainId` and `eth_call`.
- Persian numbered CLI with a public KuCoin ticker lookup.
- Offline unit tests and GitHub Actions CI.

## Requirements and setup

Python 3.11 or newer.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv\\Scripts\\Activate.ps1
python -m pip install -e ".[dev]"
pytest
ruff check .
arbitrage-trade
```

## Read-only operation and units

The application does not place exchange orders, sign or submit blockchain transactions,
approve tokens, or transfer assets. KuCoin access uses public market data and needs no
API credentials. PlunderSwap quotes call only `eth_chainId` and `eth_call` against the
documented V2 router. The PlunderSwap adapter accepts `amount_in` as an integer string
in raw token base units and returns raw output base units; it does not guess token
decimals. Callers must obtain and apply verified token decimals before comparing
human-readable prices or calculating executable arbitrage.

The adapter checks the RPC's EVM chain ID against the configured chain ID before each
quote. Default mainnet configuration is based on the official PlunderSwap developer
documentation. Override RPC/deployment configuration only with independently verified
metadata.

## Security boundaries

- No API keys, private keys, seed phrases, wallet integrations, transaction signing,
  transaction submission, approvals, or transfer methods are implemented.
- Do not commit secrets or put them in logs.
- RPC endpoints and contract addresses are configuration inputs; verify endpoint
  authenticity and deployed bytecode/ABI before production use.
- Quotes are indicative snapshots, not guaranteed execution prices. They exclude
  gas, slippage tolerance, transfer taxes, token decimals conversion, latency, and
  settlement risk.

## Official integration references

- KuCoin Spot Get Ticker: https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-ticker
- PlunderSwap developer contracts: https://docs.plunderswap.com/developers/
- PlunderSwap V2 Router interface: https://docs.plunderswap.com/developers/v2-contracts/router-v2/
- Zilliqa EVM endpoints and chain IDs: https://dev.zilliqa.com/zilliqa2/endpoints/

## Current limitations / next work

- CI tests use deterministic mocked HTTP and JSON-RPC responses; no live endpoint
  connectivity or real liquidity/quote validation is claimed.
- V3 quote routing, token metadata/decimals discovery, fee/gas estimation, cross-venue
  normalization, stale-quote controls, and profitability calculations remain future work.
- Before production use, independently verify router deployment/ABI and RPC chain
  identity, add integration tests against a controlled endpoint, and review rate limits.

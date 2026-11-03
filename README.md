# Arbitrage Trade

Python foundation for read-only centralized-exchange and DEX market analysis.

## Current capabilities

- Decimal-only primitives and explicit raw-unit DEX quote records.
- Venue-independent models: Asset, Market, PriceQuote, ArbitrageOpportunity, Order, OrderStatus and TradeResult.
- Standardized CEX, DEX, network and market-data protocols.
- Conservative net-profit evaluator: missing costs are rejected; trading, transfer and slippage costs are counted once; stale quotes, insufficient depth, non-positive net profit and capital-limit breaches are rejected.
- Configurable scoring strategies: net profit and net-profit ratio.
- Duplicate-safe market, adapter and network registries.
- Bounded retry/backoff helper and secret-redaction logging filter.
- KuCoin public Spot level-1 ticker (including available top-of-book sizes) and PlunderSwap V2 read-only quote adapter.
- Read-only PlunderSwap helpers for deployed bytecode (`eth_getCode`) and ERC-20 `decimals()` metadata (`eth_call`); these do not convert raw quote amounts automatically.

## Setup

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
mypy src/arbitrage_trade
pytest
arbitrage-trade
```

## Calculation and units

All monetary calculations use Decimal. Unknown trading fees, transfer costs or slippage are not zero: any missing required cost rejects an evaluation. A zero cost is valid only when explicitly supplied. Each cost carries a currency and component identifier; the evaluator rejects cross-currency costs and duplicate component IDs across trading, transfer and slippage costs. Gross proceeds and capital are derived directly from the sell bid, buy ask and opportunity quantity, so they cannot be silently supplied in a different unit. No FX conversion is performed.

Quotes require timezone-aware timestamps and executable depth on both legs. Missing or insufficient size rejects an opportunity. Quotes older than the configured maximum age (default five seconds) are rejected. The KuCoin level-1 adapter exposes best bid/ask sizes when supplied by the API. This is only top-of-book depth, not a full order-book liquidity guarantee.

Asset decimals are optional metadata. Raw token base-unit amounts are never converted to display units without verified decimals.

## Safety

No exchange order placement, wallet, private-key handling, transaction signing/submission, token approval or asset transfer is implemented. KuCoin uses public market data; PlunderSwap uses only eth_chainId and eth_call. Never commit secrets or log credentials. Redaction is defense-in-depth, not a universal secret detector.

## Official references

- KuCoin ticker: https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-ticker
- PlunderSwap contracts: https://docs.plunderswap.com/developers/
- PlunderSwap V2 router: https://docs.plunderswap.com/developers/v2-contracts/router-v2/
- Zilliqa EVM endpoints: https://dev.zilliqa.com/zilliqa2/endpoints/

## Limitations

- Tests are deterministic and mock-based. No live KuCoin or RPC connectivity, contract bytecode verification, pool existence or liquidity is claimed.
- PlunderSwap V2 only; V3 is not implemented.
- Automated token metadata registry and conversion helpers, gas/fee schedule discovery, FX normalization and execution simulation are not implemented. The adapter can query decimals, but callers must persist and validate that metadata before any display-unit conversion.
- KuCoin and PlunderSwap read-only HTTP calls use bounded retries for transient network failures and HTTP 429/5xx responses. JSON-RPC application errors and malformed payloads are not retried.
- No orders or settlement handling.

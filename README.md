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
- KuCoin public Spot level-1 ticker and PlunderSwap V2 read-only quote adapters.

## Setup

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check .
arbitrage-trade
```

## Calculation and units

All monetary calculations use Decimal. Unknown trading fees, transfer costs or slippage are not zero: any missing required cost rejects an evaluation. A zero cost is valid only when explicitly supplied. Cost component identifiers must be unique across trading and transfer costs to prevent duplicate counting. Gross proceeds, capital and every cost must already use the same quote-currency denomination; no FX conversion is performed.

Quotes require timezone-aware timestamps and executable depth on both legs. Missing or insufficient size rejects an opportunity. Quotes older than the configured maximum age (default five seconds) are rejected. The KuCoin level-1 adapter currently supplies bid/ask but not depth sizes, so its output alone cannot pass the profitability gate.

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
- Token decimals discovery, gas/fee schedule discovery, FX normalization and execution simulation are not implemented.
- Retry/backoff and redaction are reusable helpers but adapter network calls are not yet wired through retry_call; automatic adapter retries are not claimed.
- No orders or settlement handling.

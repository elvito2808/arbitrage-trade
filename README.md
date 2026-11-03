# Arbitrage Trade

A Python foundation for read-only cross-exchange and DEX market analysis.

## Current scope

- Decimal-safe market primitives.
- Typed CEX, DEX, and network adapter contracts.
- Public, unauthenticated KuCoin level-1 ticker adapter.
- PlunderSwap adapter configuration boundary for Zilliqa EVM; quote execution remains blocked pending verified deployment metadata and ABI selection.
- Persian numbered CLI.

## Setup

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv\\Scripts\\Activate.ps1
python -m pip install -e .
python -m pip install pytest
pytest
arbitrage-trade
```

## Safety

This project is read-only. It does not place orders, submit or sign blockchain
transactions, or transfer assets. Never commit API keys, private keys, seed
phrases, or other secrets. Public KuCoin market data requires no API key.

PlunderSwap contract addresses, chain ID, router ABI/version, and RPC details
must be verified against authoritative deployment documentation before quote
support is implemented.

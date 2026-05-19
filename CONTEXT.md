# Trading System Modernization

This context defines the shared language for modernizing the Binance Futures trading system without confusing internal system validation with exchange integration.

## Language

**Deterministic Local Loop**:
A local validation loop that uses controlled fake market/account data through the real system boundaries to prove the internal trading system can run predictably.
_Avoid_: paper trading, Binance testnet, mock-only test

**Binance Testnet Adapter**:
An exchange-integration validation path that connects the system to Binance Futures testnet after the internal local loop is stable.
_Avoid_: local loop, production Binance, paper trading

**Dry Run**:
A non-trading mode where strategy decisions produce observable order intent without placing real Binance orders.
_Avoid_: paper trading, simulated fill, backtest

**Order Intent**:
A strategy's proposed trading action before it is accepted by risk checks or sent to an exchange.
_Avoid_: order, trade, fill

## Relationships

- A **Deterministic Local Loop** may produce **Order Intent** through **Dry Run**.
- A **Binance Testnet Adapter** validates exchange integration after the **Deterministic Local Loop** is stable.
- An **Order Intent** is not an order, trade, or fill.

## Example dialogue

> **Dev:** "Should Phase 2 use Binance testnet immediately?"
> **Domain expert:** "No. First prove the **Deterministic Local Loop**. Then add the **Binance Testnet Adapter** to validate the external exchange boundary."

## Flagged ambiguities

- "dry run" was initially used to include local fake data, database persistence, dashboard display, and Binance testnet. Resolution: **Dry Run** only means no real orders; **Deterministic Local Loop** and **Binance Testnet Adapter** name the validation path.

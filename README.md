# kalshi_backtest — research-only backtests (no orders, not even paper)

Strategies: **A** mutually-exclusive outcome mispricing; **B** weather (KXHIGH*) forecast edge.
Universe: 7 daily-high series (NY, CHI, MIA, LAX, AUS, DEN, PHIL), events closing 2026-04-01 → 2026-10-12 (1,372 events, 8,230 markets).
See `reports/REPORT.md` for the existing results write-up.

## Setup

```bash
python3 -m pip install requests
```

Public Kalshi and Open-Meteo endpoints only; no auth or `.env` is required.

## Regenerate data

Raw market JSON, forecasts, and fetch logs are not checked in (`data/` is gitignored). Recreate them from the repo root, in this order:

1. **Kalshi settled markets + hourly candlesticks** — `src/fetch.py`  
   Writes `data/KXHIGH{NY,CHI,MIA,LAX,AUS,DEN,PHIL}.json` (creates `data/` if missing). Skips a series whose file already exists.

   ```bash
   python3 src/fetch.py
   ```

2. **Open-Meteo previous-run forecasts** — `src/fetch_forecast.py`  
   Writes `data/forecasts.json` (creates `data/` if missing).

   ```bash
   python3 src/fetch_forecast.py
   ```

Scripts resolve `data/` and `reports/` from the repo root (the parent of `src/`), so they still work if you invoke them from another working directory.

## Run the backtest

Needs the files from both fetch steps:

```bash
python3 src/backtest.py
```

Writes (creates `reports/` if missing):

- `reports/results.json` — headline stats for A and B variants
- `reports/strategyA_raw_opportunities.json`
- `reports/strategyA_trades.json`
- `reports/strategyB_trades_base.json` (h8 / margin 0.05 / d1)

Full pipeline:

```bash
python3 src/fetch.py && python3 src/fetch_forecast.py && python3 src/backtest.py
```

## What history Kalshi actually exposes (checked 2026-10-13, all public, no auth needed)
| Data | Available? | Endpoint |
|---|---|---|
| Settled markets + result + expiration_value | Yes | `/events` (recent), `/historical/markets` (settled before cutoff, currently 2026-08-14) |
| Trade prints (price, size, taker side) | Yes | `/markets/trades`, `/historical/trades` |
| Hourly/minute candlesticks incl. yes_bid / yes_ask OHLC | Yes | `/series/{s}/markets/{t}/candlesticks`, `/historical/markets/{t}/candlesticks` |
| **Historical order book (depth)** | **No.** `/markets/{t}/orderbook` is live-only snapshot | — |

## Limitations (read before trusting any number)
1. **No historical depth.** Entry price = hourly candle **close** of yes_ask (buy YES) or 1−yes_bid (buy NO). Size capped at 10% of that hour's traded volume. Real fill size/price may be worse.
2. **Leg asynchrony (A).** The 6 legs' candle closes are last quotes within the hour, not a simultaneous snapshot; "arbs" may be stale. Hours with crossed candle data (bid>ask) are excluded (15 found, incl. one fake 79% "arb").
3. **Forecast proxy (B).** Real NWS/NDFD point-forecast archives were not used; we use Open-Meteo *Previous Runs* archive (model run ~24h/48h before each hour), daily max over the local day at the settlement station's coordinates. Bias/σ are learned from trailing 30 days of (settled value − forecast). Decision at 08:00 local on event day (no look-ahead) or 00:00 (d1 at 00:00 has slight leakage risk; d2 is clean).
4. Fees: taker `ceil_cent(0.07·C·P·(1−P))` per leg/order. No maker rebates modelled.
5. Portfolio 10% drawdown-from-peak stop on realized equity (positions are same-day, held to settlement); after trigger: halt, no new trades. `_NOSTOP` variants shown for diagnosis only.
6. Only weather events tested for A; other mutually-exclusive event families (elections, econ ranges) not yet scanned.
Credentials in `/home/box/agent-data/secrets/kalshi/` were NOT needed or used.

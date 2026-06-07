# NSE AI Paper Trader

Beginner-friendly NSE cash-equity paper-trading dashboard with news scanning, sentiment labels, strategy scoring, and strict fake-money risk controls.

This project never places real orders. It uses fake capital only.

## Version 1.1 Features

- Live auto-refresh watchlist table
- NSE corporate announcements scanner with safe fallback data
- News sentiment classifier: positive, negative, neutral, ignore
- Auto-generated watchlist from companies mentioned in announcements
- Strategy scoring engine:
  - news catalyst breakout
  - volume spike
  - VWAP trend
  - previous day high breakout
  - opening range breakout
- Paper trading only
- No real orders
- Yahoo/mock quote fallback when a live feed is not connected

The dashboard shows:

- stock
- latest news
- sentiment
- LTP
- trigger price
- stop loss
- target
- signal
- confidence score
- reason for trade
- previous close
- change %
- quote source
- quote status

## Risk Rules

- Fake capital: Rs. 1,00,000
- Daily profit target: Rs. 2,500
- Stop trading after daily profit reaches Rs. 2,500
- Max daily loss: Rs. 1,200
- Stop trading if daily loss reaches Rs. 1,200
- Stop loss per trade: 0.2% to 0.5%
- Max loss per trade: Rs. 400
- Max trades per day: 5
- Max open positions: 2
- Force square-off at 3:20 PM IST
- Paper trading only; no real broker order code exists

## Strategies

- VWAP breakout
- Opening range breakout
- Volume breakout
- RSI reversal
- Previous day high/low breakout

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run dashboard.py --server.fileWatcherType none
```

On Streamlit Cloud, set:

```text
Main file path: dashboard.py
```

The app can run directly as a dashboard. The demo paper session writes fake trades, signals, rejected trades, stop losses, targets, square-offs, and end-of-day P&L to `data/paper_trading.db`.

## Beginner Notes

The dashboard has two different parts:

1. **V1.1 scanner and scoring table**  
   This scans announcements, classifies sentiment, fetches fallback quotes, and scores possible setups.

2. **Demo paper session**  
   This runs a simulated paper session. It is not live trading.

For true live tick data, use a broker/data feed such as Kite, but the app still stays paper-only unless real order code is deliberately added.

## Monday Live Monitoring Setup

This project is still paper-only. For real-time monitoring you must supply live 1-minute candles from a market-data source. The app can consume a growing CSV file with these columns:

```text
timestamp,symbol,open,high,low,close,volume
2026-06-08 09:15:00,INFY,1490.00,1492.00,1488.50,1491.25,125000
```

Start the dashboard:

```bash
streamlit run dashboard.py
```

Run a real-time demo replay:

```bash
python scripts/run_live_session.py --mode demo --reset --seconds-per-minute 1
```

Run against a live-updating CSV file:

```bash
python scripts/run_live_session.py --mode csv --reset --csv data/live_candles.csv --symbols RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK --day 2026-06-08
```

Run against NSE live quotes directly:

```bash
python scripts/run_live_session.py --mode nse --reset --symbols RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK --day 2026-06-08 --poll-seconds 60
```

If NSE blocks automated public requests, use Yahoo's NSE symbols:

```bash
python scripts/run_live_session.py --mode yahoo --reset --symbols RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK --day 2026-06-08 --poll-seconds 60
```

NSE/Yahoo quotes update during market hours. For production-grade accuracy, use the CSV mode with a licensed broker/data feed.

Keep both terminals open. The dashboard auto-refreshes and shows live equity, open positions, unrealized P&L, risk status, event log, and closed trades.

## Kite Connect Paper-Only Live Trial

This mode uses Zerodha Kite only for live market data. It does not place real orders.

Set Kite credentials for the current terminal:

```bash
pip install -r requirements-kite.txt
export KITE_API_KEY="your_api_key"
export KITE_ACCESS_TOKEN="your_access_token"
```

To generate the daily `KITE_ACCESS_TOKEN`:

```bash
export KITE_API_KEY="your_api_key"
export KITE_API_SECRET="your_api_secret"
python scripts/kite_login_helper.py
python scripts/kite_login_helper.py --request-token "request_token_from_redirect_url"
```

Optional: provide instrument tokens manually to avoid resolving them through the Kite instruments API:

```bash
export KITE_SYMBOL_TOKENS="INFY:408065,RELIANCE:738561,TCS:2953217,HDFCBANK:341249,ICICIBANK:1270529"
```

Start the dashboard:

```bash
streamlit run dashboard.py
```

Start the Kite live paper session:

```bash
python scripts/run_live_session.py --mode kite --reset --symbols INFY,RELIANCE,TCS,HDFCBANK,ICICIBANK --day 2026-06-08
```

The dashboard will show the live ticker, fake positions, paper P&L, rejected signals, stop losses, targets, and end-of-day P&L.

## Project Structure

```text
paper_trading_simulator/
  config.py              Risk and trading settings
  models.py              Shared dataclasses
  market_data.py         Market data interface and simulated provider
  indicators.py          VWAP, RSI, volume helpers
  logger.py              SQLite trade logger
  portfolio.py           Cash, positions, and P&L tracker
  risk.py                Risk checks and position sizing
  execution.py           Paper-only execution engine
  engine.py              Main intraday simulator
  strategies/            Modular strategies
dashboard.py             Streamlit dashboard
scripts/run_simulation.py CLI runner
tests/test_risk.py       Simple risk tests
```

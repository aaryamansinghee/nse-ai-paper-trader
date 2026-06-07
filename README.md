# NSE AI Paper Trader

Beginner-friendly NSE cash-equity paper-trading dashboard with news scanning, sentiment labels, strategy scoring, and strict fake-money risk controls.

This project never places real orders. It uses fake capital only.

## Version 1.1 Features

- Live auto-refresh watchlist table
- Green/red Moneycontrol-style price movement coloring
- NSE corporate announcements scanner with no fake-news fallback
- Separate live NSE corporate announcement feed
- Announcement feed refreshes every 60 seconds
- Auto-adds only NSE announcement stocks to the watchlist when LTP is between Rs. 200 and Rs. 1,000 by default
- News sentiment classifier: positive, negative, neutral, ignore
- Announcement quality engine: actionable, routine, unclear, or risky
- Strategy selector based on the announcement catalyst
- Auto-generated watchlist from NSE corporate announcements only
- Strategy scoring engine:
  - news catalyst breakout
  - volume spike
  - VWAP trend
  - previous day high breakout
  - opening range breakout
- Paper trading only
- No real orders
- Clear quote-unavailable status when a live quote is not connected
- Optional live fake auto-trading engine while the dashboard is open
- Historical actual-price backtest using recent Yahoo NSE 1-minute candles
- Auto-trading restricted to eligible NSE announcement stocks only
- Wait-for-trigger entry logic so the app does not buy immediately on a headline
- Early-exit target logic so the app aims to exit before stretched targets

The dashboard shows:

- stock
- company
- latest news
- live NSE announcement feed
- sentiment
- LTP
- trigger price
- stop loss
- target
- signal
- confidence score
- announcement category
- quality score
- preferred strategy
- reason for trade
- announcement eligible
- AI decision: TRADE_READY, WAIT_FOR_TRIGGER, WAIT, or REJECT
- previous close
- change %
- quote source
- quote status
- open fake positions
- realized and unrealized paper P&L
- fake execution reason and event log
- backtest trades using actual historical intraday candles when available

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

1. **Live NSE corporate announcement feed**  
   This checks recent NSE corporate announcements every minute. If a stock has a trusted quote and its LTP is between the selected price range, it is automatically added to the watchlist.
   The dashboard shows an NSE announcement connection health panel. If it says `FAILED`, the model does not have reliable announcement input and should not be used for auto paper trading.

2. **Live watchlist and scoring table**  
   This uses the auto-added NSE announcement stocks by default. Manual symbols are off by default and are for viewing only.

3. **Live paper trading engine**  
   This can create fake buy trades only inside the dashboard when you turn on `Enable fake auto-trading`. It only trades NSE announcement stocks marked `TRADE_READY`. It never sends real broker orders.

4. **Synthetic demo paper session**  
   This is only for testing the old simulator with fake generated prices. It is not live NSE data.

5. **Historical actual-price backtest**  
   This replays recent Yahoo NSE 1-minute candles through the same strategy, risk, stop-loss, target, and square-off rules.

For true live tick data, use a broker/data feed such as Kite. The app still stays paper-only unless real order code is deliberately added.

## Actual Historical Backtesting

Use the `Backtest with actual historical NSE prices` section in the dashboard.

Steps:

1. Choose the stocks.
2. Choose a real NSE trading day.
3. Click `Run actual-price backtest`.
4. Read:
   - Backtest Trades
   - Backtest Open Positions
   - Backtest Portfolio Snapshots
   - Backtest Signal And Execution Log

Important date example: **June 6, 2026 is a Saturday**, so NSE cash equity was closed. Use **June 5, 2026** for the nearest trading session.

Yahoo usually provides 1-minute candles only for recent days. If the date is too old, a weekend, a holiday, or Yahoo blocks the request, the dashboard will tell you that no candles were found.

## Monday 9:15 AM Paper Trading Checklist

1. Open the deployed Streamlit app before 9:15 AM IST.
2. Keep `Auto-refresh watchlist` turned on.
3. Set refresh seconds to 5 or 10.
4. Check `NSE announcement connection`.
   - `OK` means the deployed app fetched rows from the NSE announcement API.
   - `FAILED` means NSE blocked or rejected the automated request. Do not rely on auto-trading until this is fixed.
5. Check the quote status column.
   - `Updating` means the app is receiving current-session data.
   - `Market closed / last session` means it is still showing old data.
   - `Quote unavailable` means the source is blocked or missing and the row is not trusted for auto paper entries.
6. Turn on `Enable fake auto-trading` in the sidebar only when you are ready to paper trade.
7. Keep the browser tab open during the session.
8. Watch:
   - Open Fake Positions
   - Closed Fake Trades
   - Fake Execution Log
   - Fake total P&L

The paper trading engine uses Rs. 1,00,000 fake cash, max 5 trades, max 2 open positions, max Rs. 400 planned loss per trade, Rs. 2,500 daily target, Rs. 1,200 daily loss limit, and force square-off at 3:20 PM IST.

## AI Intraday Decision Rules

The fake auto-trader can only enter a trade when all of these are true:

- The stock came from the NSE corporate announcement feed.
- The stock passed the auto-add price filter, Rs. 200 to Rs. 1,000 by default.
- The announcement quality score is at least 20.
- The announcement sentiment is positive.
- The quote source is trusted.
- The quote status is actively `Updating`.
- The strategy confidence score is at least 75.
- The price has reached the trigger price.

The system does not auto-trade manually typed stocks. Backtesting also uses the auto-added announcement stocks by default, so names like Reliance, Infosys, or TCS will not appear unless they came from fresh NSE announcements and passed the price filter.

The app waits for a higher trigger instead of entering immediately. Example: if a stock is near Rs. 250, the system may wait around Rs. 252 before fake entry if the score is strong enough.

Targets are intentionally early. If a move looks stretched toward Rs. 273 to Rs. 275, the app tries to plan an earlier paper exit instead of waiting for the full stretched move.

No strategy can guarantee profit or breakeven. Intraday trading can lose money even when news, price, and volume look favorable. This app is designed to reduce avoidable mistakes, block stale data, enforce risk limits, and stay paper-only unless real order code is deliberately added later.

## Announcement Quality Engine

The app does not treat all positive words equally. It classifies announcements into categories:

- `order/deal win`: high-quality catalyst, preferred strategy `news catalyst breakout`
- `regulatory approval`: actionable catalyst, preferred strategy `VWAP reclaim`
- `business expansion`: actionable catalyst, preferred strategy `volume spike continuation`
- `fund raise/buyback/bonus`: medium catalyst, preferred strategy `opening range breakout`
- `strong financial update`: medium catalyst, preferred strategy `previous day high breakout`
- `routine compliance`: ignored
- `investor meet/transcript`: usually ignored or watched only
- `governance/legal risk`: rejected

Only genuinely actionable categories can become `TRADE_READY`.

Important: Streamlit Cloud runs this fake execution while the dashboard session is alive. For a stronger always-on setup, run the Kite live paper session locally or on a VPS and keep the dashboard open for monitoring.

## NSE Announcement Access

The system depends on NSE corporate announcements. The official announcements page is:

```text
https://www.nseindia.com/companies-listing/corporate-filings-announcements
```

The app fetches the underlying NSE announcement API with browser-like headers and session cookies. NSE may still block cloud/server requests. The dashboard therefore shows:

- `NSE announcement connection`
- `Rows fetched`
- `Last fetch`

If connection is `FAILED`, the app should not auto-trade. To fix that, use one of these safer routes:

- Run the app locally on your machine and check whether NSE allows the request from your IP.
- Use Kite or another licensed market/news data source.
- Use an approved backend/proxy that can legally and reliably fetch NSE announcements.

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

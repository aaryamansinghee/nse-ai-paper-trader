# NSE AI Paper Trader

Beginner-friendly NSE cash-equity paper-trading dashboard with news scanning, sentiment labels, strategy scoring, and strict fake-money risk controls.

This project never places real orders. It uses fake capital only.

## Version 1.1 Features

- Live auto-refresh watchlist table
- Green/red Moneycontrol-style price movement coloring
- Pluggable announcement providers: NSE, broker CSV, manual CSV upload, RSS/news, and mock testing
- Separate live corporate announcement feed
- Announcement feed refreshes every 60 seconds
- Auto-adds only announcement stocks to the watchlist when LTP is between Rs. 200 and Rs. 1,000 by default
- News sentiment classifier: positive, negative, neutral, ignore
- Announcement quality engine: actionable, routine, unclear, or risky
- Strategy selector based on the announcement catalyst
- Auto-generated watchlist from the active announcement provider
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
- Five-day paper trial journal: stored fake trades, win rate, profit factor, average win/loss, net fake P&L, and downloadable logs

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
- source used
- last successful announcement fetch
- provider status
- open fake positions
- realized and unrealized paper P&L
- fake execution reason and event log
- backtest trades using actual historical intraday candles when available
- five-day paper trial metrics and CSV exports

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

1. **Live corporate announcement feed**  
   This checks the selected announcement provider every minute. If a stock has a trusted quote and its LTP is between the selected price range, it is automatically added to the watchlist.
   The dashboard shows `Source Used`, `Last Successful Fetch`, `Number of Announcements`, and `Provider Status`.

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
4. Check `Provider Status` and `Source Used`.
   - `OK` means at least one announcement provider returned usable rows.
   - `FALLBACK NEEDED` means the selected provider chain returned no usable rows. Do not rely on auto-trading until a provider is working.
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
- The time is not after 2:30 PM IST for fresh entries.

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

## Weighted AI Scoring

Every announcement stock is scored out of 100 before paper trading. The score is split into explainable parts:

- Catalyst quality: 35 points
- News sentiment: 15 points
- Liquidity and tradable range: 15 points
- Market structure: 20 points
- Risk/reward: 15 points

The dashboard shows these point columns:

- `catalyst pts`
- `sentiment pts`
- `liquidity pts`
- `market pts`
- `risk pts`

The fake trading engine only considers rows that reach `BUY WATCH` and then become `TRADE_READY`. A stock can have positive news and still be rejected if liquidity is weak, quote data is stale, the price has not crossed the trigger, or the stop/target setup is poor.

Important: Streamlit Cloud runs this fake execution while the dashboard session is alive. For a stronger always-on setup, run the Kite live paper session locally or on a VPS and keep the dashboard open for monitoring.

## Five-Day Paper Trial Protocol

Run the app paper-only from Monday to Friday before considering any real-money experiment.

Each day:

1. Confirm `Provider Status` is `OK` and `Number of Announcements` is above 0.
2. Confirm quote status is `Updating` for any eligible stock.
3. Keep manual symbols off unless only viewing.
4. Turn on `Enable fake auto-trading` only during market hours.
5. Download:
   - today's closed fake trades CSV
   - today's fake execution log CSV
   - five-day trade journal CSV
   - five-day decision journal CSV
6. Record:
   - total fake P&L
   - win rate
   - profit factor
   - average win
   - average loss
   - biggest mistake/rejection reason

Do not move to real money just because one or two days are green. The five-day trial is mainly for finding bugs, stale data, bad filters, and bad trade reasons. Treat the system as not ready for real money unless all of these are true:

- NSE announcements are fetched reliably every day.
- The watchlist contains only fresh NSE announcement stocks inside the Rs. 200-Rs. 1,000 filter.
- Every fake trade has a clear reason, trigger, stop loss, and target.
- No fake trade is opened from stale quotes, manual symbols, or old news.
- Daily loss never breaches the paper risk limit.
- The five-day journal is positive or close to breakeven with an explainable win rate and profit factor.

Even after a strong paper week, start with a much longer paper trial before using real money. This app is designed for learning and controlled paper testing, not guaranteed profit.

## Announcement Provider Access

The system depends on fresh corporate announcements. Direct automated NSE website access may return `403 Forbidden` on Streamlit Cloud. The app therefore uses a provider architecture:

- `Auto fallback`: tries NSE, then configured manual/broker/RSS sources.
- `NSE only`: tries NSE directly. This may fail on Streamlit Cloud.
- `Manual upload`: lets you upload one or many announcement CSV files.
- `RSS/news`: reads configured RSS feeds and extracts stock symbols from news text.
- `Broker`: reads a broker/exported CSV path configured by `BROKER_ANNOUNCEMENTS_CSV`.
- `Mock testing`: uses test announcements so the rest of the app can be checked without live data.

For manual upload, you can select multiple NSE sub-segment CSV files at once. The app merges them, removes duplicates, and builds one announcement feed. Use CSV columns like:

```text
symbol,company,headline,details,date,link
ABC,ABC Limited,ABC wins large order,Large order win from customer,2026-06-08 09:20:00,
```

The dashboard does not crash if NSE returns 403. It shows a warning and tries fallback providers. If all providers fail, the app blocks auto paper-trading because the announcement input is not reliable.

- `Source Used`
- `Last Successful Fetch`
- `Number of Announcements`
- `Provider Status`

If all providers fail, use one of these safer routes:

- Run the app locally on your machine and check whether NSE allows the request from your IP.
- Use Kite or another licensed market/news data source.
- Upload the NSE announcements CSV manually from the NSE website.
- Use an approved backend/proxy that can legally and reliably fetch announcements.

## Monday Live Monitoring Setup

This project is still paper-only. For real-time monitoring you must supply live 1-minute candles from a market-data source. The dashboard first fetches NSE announcements, filters stocks between Rs. 200 and Rs. 1,000, then builds the watchlist automatically. Do not start the live paper runner with a manual large-cap basket unless you are testing only.

The app can consume a growing CSV file with these columns:

```text
timestamp,symbol,open,high,low,close,volume
2026-06-08 09:15:00,ABC,642.00,648.00,639.50,646.25,325000
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
python scripts/run_live_session.py --mode csv --reset --csv data/live_candles.csv --symbols SYMBOLS_FROM_AUTO_WATCHLIST --day 2026-06-08
```

Run against NSE live quotes directly, using only the symbols auto-added by the announcement scanner:

```bash
python scripts/run_live_session.py --mode nse --reset --symbols SYMBOLS_FROM_AUTO_WATCHLIST --day 2026-06-08 --poll-seconds 60
```

If NSE blocks automated public quote requests, use Yahoo's NSE symbols for the same auto-watchlist:

```bash
python scripts/run_live_session.py --mode yahoo --reset --symbols SYMBOLS_FROM_AUTO_WATCHLIST --day 2026-06-08 --poll-seconds 60
```

Replace `SYMBOLS_FROM_AUTO_WATCHLIST` with the comma-separated stocks shown in the dashboard after NSE announcements load. The paper engine will still reject any stock that is not announcement-eligible, not positive, outside Rs. 200-Rs. 1,000, stale, or below trigger.

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

Optional: provide instrument tokens manually for the current auto-watchlist to avoid resolving them through the Kite instruments API:

```bash
export KITE_SYMBOL_TOKENS="ABC:123456,XYZ:234567"
```

Start the dashboard:

```bash
streamlit run dashboard.py
```

Start the Kite live paper session:

```bash
python scripts/run_live_session.py --mode kite --reset --symbols SYMBOLS_FROM_AUTO_WATCHLIST --day 2026-06-08
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

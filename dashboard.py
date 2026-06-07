from datetime import date
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from paper_trading_simulator.announcements import NSECorporateAnnouncementsScanner, symbols_from_announcements
from paper_trading_simulator.config import TradingConfig
from paper_trading_simulator.engine import IntradaySimulator
from paper_trading_simulator.logger import SQLiteTradeLogger
from paper_trading_simulator.market_data import (
    SimulatedNSEMarketDataProvider,
    YahooNSELiveQuoteMarketDataProvider,
    default_symbols,
    mock_latest_candle,
)
from paper_trading_simulator.scoring import score_trade_setup
from paper_trading_simulator.sentiment import classify_sentiment


st.set_page_config(page_title="NSE AI Paper Trader", layout="wide")

config = TradingConfig()
db_path = Path(config.database_path)


def quote_status(timestamp, volume: int | float | None, source: str) -> str:
    if source.startswith("Mock"):
        return "Mock fallback - not live"
    if pd.isna(timestamp):
        return "No quote"
    quote_day = pd.Timestamp(timestamp).date()
    if quote_day != date.today():
        return "Market closed / last session"
    if volume is not None and volume == 0:
        return "Stale flat candle"
    return "Updating"


def price_change(candle) -> tuple[float | None, float | None]:
    if not candle or candle.previous_close in (None, 0):
        return None, None
    change = round(candle.close - candle.previous_close, 2)
    change_pct = round((change / candle.previous_close) * 100, 2)
    return change, change_pct


@st.cache_data(ttl=300)
def load_announcements(days: int, limit: int):
    scanner = NSECorporateAnnouncementsScanner()
    return scanner.fetch_recent(days=days, limit=limit)


@st.cache_data(ttl=30)
def load_latest_quotes(symbols: tuple[str, ...]):
    provider = YahooNSELiveQuoteMarketDataProvider(poll_seconds=60)
    quotes = {}
    for symbol in symbols:
        try:
            candle = provider.fetch_latest_candle(symbol)
            if candle:
                quotes[symbol] = {
                    "candle": candle,
                    "source": "Yahoo Finance NSE (.NS)",
                }
            else:
                quotes[symbol] = {
                    "candle": mock_latest_candle(symbol),
                    "source": "Mock fallback - not live",
                }
        except Exception:
            quotes[symbol] = {
                "candle": mock_latest_candle(symbol),
                "source": "Mock fallback - not live",
            }
    return quotes


def read_table(table_name: str) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    order_by = {
        "events": "id DESC",
        "trades": "id DESC",
        "portfolio_snapshots": "id DESC",
        "open_positions": "symbol ASC",
        "latest_ticks": "symbol ASC",
        "ticks": "id DESC",
    }.get(table_name)
    if order_by is None:
        return pd.DataFrame()
    with sqlite3.connect(db_path) as connection:
        try:
            return pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY {order_by}", connection)
        except (pd.errors.DatabaseError, sqlite3.OperationalError):
            return pd.DataFrame()


st.title("NSE AI Paper Trader V1.1")
st.caption("Auto-refresh watchlist, announcement scanner, sentiment, and paper-only trade scoring. No real orders.")

auto_refresh = st.sidebar.checkbox("Auto-refresh watchlist", value=True)
refresh_seconds = st.sidebar.slider("Refresh seconds", min_value=5, max_value=60, value=10, step=5)
if auto_refresh:
    components.html(f"<meta http-equiv='refresh' content='{refresh_seconds}'>", height=0)

st.sidebar.markdown("### Watchlist Settings")
announcement_days = st.sidebar.slider("Announcement lookback days", min_value=1, max_value=10, value=3)
max_announcements = st.sidebar.slider("Max announcements", min_value=5, max_value=50, value=20, step=5)
manual_symbols_text = st.sidebar.text_area(
    "Manual symbols",
    value="RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK",
    help="Comma-separated NSE symbols.",
)

st.info(
    "This is the auto-refresh watchlist. It reloads announcements and quote sources. "
    "When the market is closed, rows show last-session data. If a source is blocked, rows are marked as mock fallback."
)

announcements = load_announcements(announcement_days, max_announcements)
announcement_symbols = symbols_from_announcements(announcements)
manual_symbols = [item.strip().upper() for item in manual_symbols_text.split(",") if item.strip()]
watchlist_symbols = list(dict.fromkeys(announcement_symbols + manual_symbols))
quotes = load_latest_quotes(tuple(watchlist_symbols))

score_rows = []
for announcement in announcements:
    sentiment = classify_sentiment(f"{announcement.headline} {announcement.details}")
    quote = quotes.get(announcement.symbol)
    candle = quote["candle"] if quote else None
    quote_source = quote["source"] if quote else "No quote"
    score = score_trade_setup(announcement, sentiment, candle, config.target_reward_multiple)
    change, change_pct = price_change(candle)
    score_rows.append(
        {
            "stock": score.symbol,
            "latest news": score.latest_news,
            "sentiment": score.sentiment,
            "LTP": score.ltp,
            "previous close": candle.previous_close if candle else None,
            "change %": change_pct,
            "trigger price": score.trigger_price,
            "stop loss": score.stop_loss,
            "target": score.target,
            "signal": score.signal,
            "confidence score": score.confidence_score,
            "reason for trade": score.reason_for_trade,
            "quote status": quote_status(candle.timestamp, candle.volume, quote_source) if candle else "No quote",
            "quote source": quote_source,
            "news source": score.source,
        }
    )

watchlist_rows = []
for symbol in watchlist_symbols:
    quote = quotes.get(symbol)
    candle = quote["candle"] if quote else mock_latest_candle(symbol)
    quote_source = quote["source"] if quote else "Mock fallback - not live"
    related_news = [item.headline for item in announcements if item.symbol == symbol]
    change, change_pct = price_change(candle)
    watchlist_rows.append(
        {
            "stock": symbol,
            "LTP": candle.close,
            "previous close": candle.previous_close,
            "change": change,
            "change %": change_pct,
            "day high": candle.high,
            "day low": candle.low,
            "volume": candle.volume,
            "timestamp": candle.timestamp,
            "status": quote_status(candle.timestamp, candle.volume, quote_source),
            "quote source": quote_source,
            "latest news": related_news[0] if related_news else "No recent announcement found",
        }
    )

top_left, top_right = st.columns(2)
with top_left:
    st.metric("Watchlist stocks", len(watchlist_rows))
with top_right:
    buy_watch_count = sum(1 for row in score_rows if row["signal"] == "BUY WATCH")
    st.metric("BUY WATCH signals", buy_watch_count)

st.subheader("Live Auto-Refresh Watchlist")
st.dataframe(pd.DataFrame(watchlist_rows), use_container_width=True, hide_index=True)

st.subheader("AI Strategy Scoring")
st.dataframe(pd.DataFrame(score_rows), use_container_width=True, hide_index=True)

with st.expander("Optional: synthetic demo paper session", expanded=False):
    st.warning("This demo uses synthetic prices for testing only. It is not live NSE data.")
    left, right = st.columns([1, 2])
    with left:
        symbol_options = list(dict.fromkeys(default_symbols() + watchlist_symbols))
        selected_defaults = [symbol for symbol in watchlist_symbols[:3] if symbol in symbol_options] or default_symbols()[:3]
        selected_symbols = st.multiselect("Symbols", symbol_options, default=selected_defaults)
        selected_day = st.date_input("Trading day", value=date.today())
        reset_logs = st.checkbox("Clear old logs before run", value=True)
        run_button = st.button("Run synthetic demo paper session", type="primary")
    with right:
        st.metric("Fake capital", "Rs. 1,00,000")
        st.metric("Daily profit target", "Rs. 2,500")
        st.metric("Max daily loss", "Rs. 1,200")

    if run_button:
        if not selected_symbols:
            st.warning("Choose at least one symbol.")
        else:
            logger = SQLiteTradeLogger(config.database_path)
            if reset_logs:
                logger.reset()
            provider = SimulatedNSEMarketDataProvider(config)
            simulator = IntradaySimulator(config, provider, logger)
            summary = simulator.run(selected_symbols, selected_day)
            st.success(f"Synthetic demo paper session complete. End-of-day P&L: Rs. {summary['total_pnl']:.2f}")

    events = read_table("events")
    trades = read_table("trades")
    open_positions = read_table("open_positions")
    latest_ticks = read_table("latest_ticks")

    st.subheader("Live ticker from external runner")
    st.dataframe(latest_ticks, use_container_width=True, hide_index=True)

    st.subheader("Open paper positions")
    st.dataframe(open_positions, use_container_width=True, hide_index=True)

    st.subheader("Event log")
    st.dataframe(events, use_container_width=True, hide_index=True)

    st.subheader("Closed demo trades")
    if not trades.empty:
        trades_to_show = trades.copy()
        trades_to_show["price_source"] = "DEMO synthetic prices"
        st.dataframe(trades_to_show, use_container_width=True, hide_index=True)
        chart_data = trades.sort_values("id").copy()
        chart_data["cumulative_pnl"] = chart_data["pnl"].cumsum()
        st.line_chart(chart_data, x="id", y="cumulative_pnl")
    else:
        st.dataframe(trades, use_container_width=True, hide_index=True)

from datetime import date, datetime, timedelta
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from paper_trading_simulator.announcement_quality import classify_announcement_quality
from paper_trading_simulator.announcements import build_announcement_provider, symbols_from_announcements
from paper_trading_simulator.config import TradingConfig
from paper_trading_simulator.engine import IntradaySimulator
from paper_trading_simulator.logger import SQLiteTradeLogger
from paper_trading_simulator.market_data import (
    HistoricalYahooNSEMarketDataProvider,
    SimulatedNSEMarketDataProvider,
    YahooNSELiveQuoteMarketDataProvider,
)
from paper_trading_simulator.live_paper import LivePaperTrader
from paper_trading_simulator.scoring import score_trade_setup
from paper_trading_simulator.sentiment import classify_sentiment


st.set_page_config(page_title="NSE AI Paper Trader", layout="wide")

config = TradingConfig()
db_path = Path(config.database_path)
paper_trader = LivePaperTrader(config)
trial_logger = SQLiteTradeLogger(config.database_path)


def quote_status(timestamp, volume: int | float | None, source: str) -> str:
    if source.startswith("Mock"):
        return "Mock fallback - not live"
    if pd.isna(timestamp):
        return "No quote"
    quote_day = pd.Timestamp(timestamp).date()
    ist_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if quote_day != ist_today:
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


def ai_intraday_decision(score, candle, quote_source: str, is_auto_added: bool) -> tuple[str, str]:
    if not is_auto_added:
        return "REJECT", "Only NSE announcement stocks that pass the price filter can be auto-traded"
    if score.announcement_quality_score < 20:
        return "REJECT", "Announcement quality is too weak for intraday auto-trading"
    if score.sentiment != "positive":
        return "REJECT", "Announcement is not positive enough for intraday auto-trading"
    if quote_source != "Yahoo Finance NSE (.NS)":
        return "REJECT", "Live quote is not trusted"
    if not candle or candle.close <= 0:
        return "REJECT", "No usable LTP"
    if score.confidence_score < 75:
        return "WAIT", "Positive news exists, but strategy confidence is below 75"
    if candle.close < score.trigger_price:
        return "WAIT_FOR_TRIGGER", f"Wait for breakout confirmation near Rs. {score.trigger_price:.2f}"
    return "TRADE_READY", "Positive NSE announcement, trusted quote, price filter passed, confidence strong, trigger reached"


@st.cache_data(ttl=60)
def load_announcement_result(
    days: int,
    limit: int,
    provider_mode: str,
    manual_csv_text: str,
    rss_urls: tuple[str, ...],
    enable_mock: bool,
):
    provider = build_announcement_provider(
        mode=provider_mode,
        manual_csv_text=manual_csv_text,
        rss_urls=rss_urls,
        enable_mock=enable_mock,
    )
    return provider.fetch(days=days, limit=limit)


@st.cache_data(ttl=10)
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
                    "candle": None,
                    "source": "Quote unavailable - not live",
                }
        except Exception:
            quotes[symbol] = {
                "candle": None,
                "source": "Quote unavailable - not live",
            }
    return quotes


def reset_live_paper_state() -> None:
    st.session_state.live_paper_state = paper_trader.create_state()


def previous_weekday(start_day: date) -> date:
    day = start_day
    while day.weekday() >= 5:
        day = day - timedelta(days=1)
    return day


def format_money(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"Rs. {float(value):,.2f}"


def format_plain_number(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):,.2f}"


def change_color(value) -> str:
    if value is None or pd.isna(value):
        return ""
    value = float(value)
    if value > 0:
        return "color: #047857; font-weight: 700; background-color: #ecfdf3"
    if value < 0:
        return "color: #b91c1c; font-weight: 700; background-color: #fff1f2"
    return "color: #374151"


def signal_color(value: str) -> str:
    if value == "BUY WATCH":
        return "color: #047857; font-weight: 800; background-color: #dcfce7"
    if value in {"IGNORE", "NO TRADE"}:
        return "color: #991b1b; font-weight: 700; background-color: #fee2e2"
    return "color: #92400e; font-weight: 700; background-color: #fef3c7"


def decision_color(value: str) -> str:
    if value == "TRADE_READY":
        return "color: #047857; font-weight: 800; background-color: #dcfce7"
    if value == "WAIT_FOR_TRIGGER":
        return "color: #1d4ed8; font-weight: 800; background-color: #dbeafe"
    if value == "WAIT":
        return "color: #92400e; font-weight: 700; background-color: #fef3c7"
    return "color: #991b1b; font-weight: 700; background-color: #fee2e2"


def pnl_color(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return change_color(value)


def yes_no_color(value: str) -> str:
    if value == "YES":
        return "color: #047857; font-weight: 800; background-color: #dcfce7"
    return "color: #991b1b; font-weight: 700; background-color: #fee2e2"


def style_watchlist(frame: pd.DataFrame):
    if frame.empty:
        return frame
    return (
        frame.style.map(change_color, subset=["change", "change %"])
        .format(
            {
                "LTP": format_money,
                "previous close": format_money,
                "change": format_plain_number,
                "change %": lambda value: "" if pd.isna(value) else f"{float(value):.2f}%",
                "day high": format_money,
                "day low": format_money,
                "volume": lambda value: "" if pd.isna(value) else f"{int(value):,}",
            }
        )
        .hide(axis="index")
    )


def style_announcement_feed(frame: pd.DataFrame):
    if frame.empty:
        return frame
    return (
        frame.style.map(yes_no_color, subset=["auto-added"])
        .map(change_color, subset=["change %"])
        .format(
            {
                "LTP": format_money,
                "change %": lambda value: "" if pd.isna(value) else f"{float(value):.2f}%",
            }
        )
        .hide(axis="index")
    )


def style_scores(frame: pd.DataFrame):
    if frame.empty:
        return frame
    return (
        frame.style.map(change_color, subset=["change %"])
        .map(signal_color, subset=["signal"])
        .map(decision_color, subset=["AI decision"])
        .format(
            {
                "LTP": format_money,
                "previous close": format_money,
                "change %": lambda value: "" if pd.isna(value) else f"{float(value):.2f}%",
                "trigger price": format_money,
                "stop loss": format_money,
                "target": format_money,
                "confidence score": lambda value: f"{int(value)}",
                "quality score": lambda value: f"{int(value)}",
            }
        )
        .hide(axis="index")
    )


def positions_frame(state) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "stock": position.symbol,
                "qty": position.quantity,
                "entry": position.entry_price,
                "LTP": position.latest_price,
                "stop loss": position.stop_loss,
                "target": position.target,
                "unrealized P&L": position.unrealized_pnl,
                "confidence": position.confidence_score,
                "why entered": position.reason,
                "entry time": position.entry_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for position in state.positions.values()
        ]
    )


def trades_frame(state) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "stock": trade.symbol,
                "qty": trade.quantity,
                "entry": trade.entry_price,
                "exit": trade.exit_price,
                "exit reason": trade.exit_reason,
                "P&L": trade.pnl,
                "why entered": trade.reason,
                "entry time": trade.entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                "exit time": trade.exit_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for trade in state.closed_trades
        ]
    )


def performance_summary(state) -> dict:
    trades = state.closed_trades
    winners = [trade for trade in trades if trade.pnl > 0]
    losers = [trade for trade in trades if trade.pnl < 0]
    gross_profit = sum(trade.pnl for trade in winners)
    gross_loss = abs(sum(trade.pnl for trade in losers))
    return {
        "closed_trades": len(trades),
        "win_rate": round((len(winners) / len(trades)) * 100, 2) if trades else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else (round(gross_profit, 2) if gross_profit else 0.0),
        "average_win": round(gross_profit / len(winners), 2) if winners else 0.0,
        "average_loss": round(sum(trade.pnl for trade in losers) / len(losers), 2) if losers else 0.0,
    }


def performance_summary_from_frame(frame: pd.DataFrame) -> dict:
    if frame.empty or "pnl" not in frame.columns:
        return {
            "closed_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "net_pnl": 0.0,
        }
    pnl = pd.to_numeric(frame["pnl"], errors="coerce").fillna(0)
    winners = pnl[pnl > 0]
    losers = pnl[pnl < 0]
    gross_profit = winners.sum()
    gross_loss = abs(losers.sum())
    return {
        "closed_trades": int(len(pnl)),
        "win_rate": round((len(winners) / len(pnl)) * 100, 2) if len(pnl) else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else (round(gross_profit, 2) if gross_profit else 0.0),
        "average_win": round(gross_profit / len(winners), 2) if len(winners) else 0.0,
        "average_loss": round(losers.sum() / len(losers), 2) if len(losers) else 0.0,
        "net_pnl": round(pnl.sum(), 2),
    }


def style_positions(frame: pd.DataFrame):
    if frame.empty:
        return frame
    return (
        frame.style.map(pnl_color, subset=["unrealized P&L"])
        .format(
            {
                "entry": format_money,
                "LTP": format_money,
                "stop loss": format_money,
                "target": format_money,
                "unrealized P&L": format_money,
            }
        )
        .hide(axis="index")
    )


def style_trades(frame: pd.DataFrame):
    if frame.empty:
        return frame
    return (
        frame.style.map(pnl_color, subset=["P&L"])
        .format({"entry": format_money, "exit": format_money, "P&L": format_money})
        .hide(axis="index")
    )


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
        "live_paper_events": "id DESC",
        "live_paper_trades": "id DESC",
    }.get(table_name)
    if order_by is None:
        return pd.DataFrame()
    with sqlite3.connect(db_path) as connection:
        try:
            return pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY {order_by}", connection)
        except (pd.errors.DatabaseError, sqlite3.OperationalError):
            return pd.DataFrame()


st.title("NSE AI Paper Trader V1.1")
st.caption("Auto-refresh watchlist, pluggable announcement providers, sentiment, and paper-only trade scoring. No real orders.")

auto_refresh = st.sidebar.checkbox("Auto-refresh watchlist", value=True)
refresh_seconds = st.sidebar.slider("Refresh seconds", min_value=5, max_value=60, value=10, step=5)
if auto_refresh:
    components.html(f"<meta http-equiv='refresh' content='{refresh_seconds}'>", height=0)

st.sidebar.markdown("### Watchlist Settings")
announcement_days = st.sidebar.slider("Announcement lookback days", min_value=1, max_value=10, value=1)
max_announcements = st.sidebar.slider("Max announcements", min_value=5, max_value=50, value=20, step=5)
provider_mode_label = st.sidebar.selectbox(
    "Announcement source",
    [
        "Auto fallback",
        "NSE only",
        "Manual upload",
        "RSS/news",
        "Broker",
        "Mock testing",
    ],
    index=0,
)
provider_mode = {
    "Auto fallback": "auto",
    "NSE only": "nse",
    "Manual upload": "manual",
    "RSS/news": "rss",
    "Broker": "broker",
    "Mock testing": "mock",
}[provider_mode_label]
uploaded_announcements = st.sidebar.file_uploader(
    "Manual announcements CSV",
    type=["csv"],
    help="Fallback input. Columns can include symbol, company, headline, details, date/time, link.",
)
manual_csv_text = ""
if uploaded_announcements is not None:
    manual_csv_text = uploaded_announcements.getvalue().decode("utf-8", errors="ignore")
rss_url_text = st.sidebar.text_area(
    "RSS/news URLs",
    value="",
    help="One RSS feed URL per line. Used in RSS/news mode or auto fallback.",
)
rss_urls = tuple(line.strip() for line in rss_url_text.splitlines() if line.strip())
enable_mock_announcements = provider_mode == "mock"
price_filter_min = st.sidebar.number_input("Auto-add minimum LTP", min_value=1, max_value=5000, value=200, step=25)
price_filter_max = st.sidebar.number_input("Auto-add maximum LTP", min_value=1, max_value=10000, value=1000, step=25)
include_manual_symbols = st.sidebar.checkbox(
    "Include manual symbols",
    value=False,
    help="Off by default. Auto-trading still only uses NSE announcement stocks.",
)
manual_symbols_text = st.sidebar.text_area(
    "Manual symbols for viewing only",
    value="",
    help="Comma-separated NSE symbols.",
)

st.sidebar.markdown("### Live Paper Trading")
auto_paper_trade = st.sidebar.toggle(
    "Enable fake auto-trading",
    value=False,
    help="Paper trading only. The app never sends broker orders.",
)
if st.sidebar.button("Reset fake trading day"):
    reset_live_paper_state()

if "live_paper_state" not in st.session_state:
    reset_live_paper_state()
if st.session_state.get("live_paper_day") != datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat():
    reset_live_paper_state()
    st.session_state.live_paper_day = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()

st.info(
    "This is the auto-refresh watchlist. It reloads announcement providers and quote sources. "
    "When the market is closed, rows show last-session data. If a provider is blocked, fallback sources are tried."
)

if price_filter_min > price_filter_max:
    st.error("Auto-add minimum LTP must be lower than maximum LTP.")
    st.stop()

announcement_result = load_announcement_result(
    announcement_days,
    max_announcements,
    provider_mode,
    manual_csv_text,
    rss_urls,
    enable_mock_announcements,
)
announcements = announcement_result.announcements
health_cols = st.columns(4)
health_cols[0].metric("Source Used", announcement_result.source_used)
last_success = announcement_result.last_successful_fetch.strftime("%H:%M:%S") if announcement_result.last_successful_fetch else "None"
health_cols[1].metric("Last Successful Fetch", last_success)
health_cols[2].metric("Number of Announcements", len(announcements))
health_cols[3].metric("Provider Status", "OK" if announcement_result.ok else "FALLBACK NEEDED")
if announcement_result.ok:
    st.success(announcement_result.message)
else:
    st.warning(announcement_result.message)
    st.caption(
        "If NSE returns 403 on Streamlit Cloud, the app will try configured fallback providers. "
        "Use manual CSV, RSS/news, broker data, or mock testing mode instead of relying only on direct NSE access."
    )
if announcement_result.provider_statuses:
    provider_status_df = pd.DataFrame(
        [
            {
                "provider": status.provider,
                "status": "OK" if status.ok else "FAILED",
                "rows": status.rows,
                "message": status.message,
                "fetched_at": status.fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
                "source": status.source_url,
            }
            for status in announcement_result.provider_statuses
        ]
    )
    with st.expander("Provider status details", expanded=not announcement_result.ok):
        st.dataframe(provider_status_df, use_container_width=True, hide_index=True)
if not announcements:
    st.warning(
        "No fresh announcements were fetched from the selected provider chain. "
        "Use manual CSV upload or mock testing mode to verify the rest of the paper-trading pipeline."
    )
announcement_symbols = symbols_from_announcements(announcements)
manual_symbols = [item.strip().upper() for item in manual_symbols_text.split(",") if item.strip()] if include_manual_symbols else []
announcement_quotes = load_latest_quotes(tuple(announcement_symbols))

announcement_feed_rows = []
auto_added_symbols = []
for announcement in announcements:
    quote = announcement_quotes.get(announcement.symbol)
    candle = quote["candle"] if quote else None
    quote_source = quote["source"] if quote else "No quote"
    change, change_pct = price_change(candle)
    sentiment = classify_sentiment(f"{announcement.headline} {announcement.details}")
    quality = classify_announcement_quality(announcement.headline, announcement.details)
    has_trusted_price = candle is not None and quote_source == "Yahoo Finance NSE (.NS)"
    price_is_in_range = bool(candle and price_filter_min <= candle.close <= price_filter_max)
    auto_added = has_trusted_price and price_is_in_range
    if auto_added and announcement.symbol not in auto_added_symbols:
        auto_added_symbols.append(announcement.symbol)
    if not has_trusted_price:
        filter_reason = "Not auto-added: trusted quote unavailable"
    elif not price_is_in_range:
        filter_reason = f"Not auto-added: LTP outside Rs. {price_filter_min}-{price_filter_max}"
    else:
        filter_reason = "Auto-added from NSE announcement"
    announcement_feed_rows.append(
        {
            "time": announcement.published_at,
            "stock": announcement.symbol,
            "company": announcement.company,
            "latest NSE announcement": announcement.headline,
            "sentiment": sentiment.label,
            "announcement category": quality.category,
            "quality score": quality.quality_score,
            "preferred strategy": quality.preferred_strategy,
            "LTP": candle.close if candle else None,
            "change %": change_pct,
            "auto-added": "YES" if auto_added else "NO",
            "reason": filter_reason,
            "quote status": quote_status(candle.timestamp, candle.volume, quote_source) if candle else "No quote",
            "source": announcement.source,
        }
    )

watchlist_symbols = list(dict.fromkeys(auto_added_symbols + manual_symbols))
quotes = load_latest_quotes(tuple(watchlist_symbols))

score_rows = []
for announcement in announcements:
    sentiment = classify_sentiment(f"{announcement.headline} {announcement.details}")
    quote = announcement_quotes.get(announcement.symbol)
    candle = quote["candle"] if quote else None
    quote_source = quote["source"] if quote else "No quote"
    score = score_trade_setup(announcement, sentiment, candle, config.target_reward_multiple)
    change, change_pct = price_change(candle)
    is_auto_added = announcement.symbol in auto_added_symbols
    ai_decision, ai_reason = ai_intraday_decision(score, candle, quote_source, is_auto_added)
    score_rows.append(
        {
            "stock": score.symbol,
            "latest news": score.latest_news,
            "sentiment": score.sentiment,
            "announcement category": score.announcement_category,
            "quality score": score.announcement_quality_score,
            "preferred strategy": score.preferred_strategy,
            "announcement eligible": "YES" if is_auto_added else "NO",
            "AI decision": ai_decision,
            "LTP": score.ltp,
            "previous close": candle.previous_close if candle else None,
            "change %": change_pct,
            "trigger price": score.trigger_price,
            "stop loss": score.stop_loss,
            "target": score.target,
                "signal": score.signal,
                "confidence score": score.confidence_score,
                "catalyst pts": score.catalyst_points,
                "sentiment pts": score.sentiment_points,
                "liquidity pts": score.liquidity_points,
                "market pts": score.market_structure_points,
                "risk pts": score.risk_reward_points,
                "reason for trade": f"{ai_reason}; {score.reason_for_trade}",
                "quote status": quote_status(candle.timestamp, candle.volume, quote_source) if candle else "No quote",
                "quote source": quote_source,
            "news source": score.source,
        }
    )

watchlist_rows = []
for symbol in watchlist_symbols:
    quote = quotes.get(symbol)
    candle = quote["candle"] if quote else None
    quote_source = quote["source"] if quote else "Quote unavailable - not live"
    if candle is None:
        continue
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

watchlist_df = pd.DataFrame(watchlist_rows)
score_df = pd.DataFrame(score_rows)

ist_now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
if auto_paper_trade:
    st.session_state.live_paper_state = paper_trader.process_setups(
        st.session_state.live_paper_state,
        score_rows,
        ist_now,
    )

live_state = st.session_state.live_paper_state
trial_logger.log_live_paper_state(st.session_state.live_paper_day, live_state)

top_left, top_middle, top_right = st.columns(3)
with top_left:
    st.metric("Watchlist stocks", len(watchlist_rows))
with top_middle:
    st.metric("Fake total P&L", f"Rs. {live_state.total_pnl():,.2f}")
with top_right:
    buy_watch_count = sum(1 for row in score_rows if row["signal"] == "BUY WATCH")
    st.metric("BUY WATCH signals", buy_watch_count)

st.subheader("Live Corporate Announcement Feed")
st.caption(
    f"Auto-refreshes every 60 seconds. Announcement stocks are auto-added only when trusted LTP is between "
    f"Rs. {price_filter_min} and Rs. {price_filter_max}. Manual symbols are off by default and are for viewing only."
)
announcement_feed_df = pd.DataFrame(announcement_feed_rows)
feed_col_1, feed_col_2, feed_col_3 = st.columns(3)
feed_col_1.metric("Announcements scanned", len(announcement_feed_rows))
feed_col_2.metric("Auto-added stocks", len(auto_added_symbols))
feed_col_3.metric("Price filter", f"Rs. {price_filter_min}-{price_filter_max}")
st.dataframe(style_announcement_feed(announcement_feed_df), use_container_width=True)

st.subheader("Live Auto-Refresh Watchlist")
st.dataframe(style_watchlist(watchlist_df), use_container_width=True)

st.subheader("AI Strategy Scoring")
st.caption(
    "Auto paper-trading is restricted to TRADE_READY rows only. These must be positive NSE announcement stocks, "
    "auto-added by the Rs. 200-Rs. 1,000 filter, with trusted quotes and trigger confirmation."
)
st.dataframe(style_scores(score_df), use_container_width=True)

st.subheader("Live Paper Trading Engine")
if auto_paper_trade:
    st.success("Fake auto-trading is ON. It only creates paper trades inside this dashboard.")
else:
    st.warning("Fake auto-trading is OFF. Turn it on from the sidebar before Monday's 9:15 AM session.")

status_text = live_state.stopped_reason or "Armed for market hours"
paper_cols = st.columns(5)
paper_cols[0].metric("Fake capital", "Rs. 1,00,000")
paper_cols[1].metric("Fake cash", f"Rs. {live_state.cash:,.2f}")
paper_cols[2].metric("Realized P&L", f"Rs. {live_state.realized_pnl():,.2f}")
paper_cols[3].metric("Unrealized P&L", f"Rs. {live_state.unrealized_pnl():,.2f}")
paper_cols[4].metric("Trades used", f"{live_state.trades_taken}/5")
st.caption(
    f"Status: {status_text}. Trading window: 9:15 AM to 3:30 PM IST. "
    "Force square-off: 3:20 PM IST. Daily target: Rs. 2,500. Max daily loss: Rs. 1,200."
)

position_df = positions_frame(live_state)
trade_df = trades_frame(live_state)
event_df = pd.DataFrame(live_state.event_log)
summary = performance_summary(live_state)
stored_trade_df = read_table("live_paper_trades")
stored_event_df = read_table("live_paper_events")
stored_summary = performance_summary_from_frame(stored_trade_df)

st.markdown("#### Today's Paper Metrics")
today_cols = st.columns(5)
today_cols[0].metric("Closed trades", summary["closed_trades"])
today_cols[1].metric("Win rate", f"{summary['win_rate']:.2f}%")
today_cols[2].metric("Profit factor", summary["profit_factor"])
today_cols[3].metric("Average win", f"Rs. {summary['average_win']:,.2f}")
today_cols[4].metric("Average loss", f"Rs. {summary['average_loss']:,.2f}")

st.markdown("#### Five-Day Trial Journal")
trial_cols = st.columns(6)
trial_cols[0].metric("Stored trades", stored_summary["closed_trades"])
trial_cols[1].metric("Stored win rate", f"{stored_summary['win_rate']:.2f}%")
trial_cols[2].metric("Profit factor", stored_summary["profit_factor"])
trial_cols[3].metric("Net fake P&L", f"Rs. {stored_summary['net_pnl']:,.2f}")
trial_cols[4].metric("Average win", f"Rs. {stored_summary['average_win']:,.2f}")
trial_cols[5].metric("Average loss", f"Rs. {stored_summary['average_loss']:,.2f}")
st.caption(
    "Use this stored journal after each live paper day. Do not judge the model from one trade; review the full Monday-Friday sample."
)

st.markdown("#### Open Fake Positions")
st.dataframe(style_positions(position_df), use_container_width=True)

st.markdown("#### Closed Fake Trades")
st.dataframe(style_trades(trade_df), use_container_width=True)

st.markdown("#### Fake Execution Log")
st.dataframe(event_df, use_container_width=True, hide_index=True)

download_cols = st.columns(2)
download_cols[0].download_button(
    "Download closed fake trades CSV",
    trade_df.to_csv(index=False).encode("utf-8"),
    file_name=f"closed_fake_trades_{st.session_state.live_paper_day}.csv",
    mime="text/csv",
    disabled=trade_df.empty,
)
download_cols[1].download_button(
    "Download fake execution log CSV",
    event_df.to_csv(index=False).encode("utf-8"),
    file_name=f"fake_execution_log_{st.session_state.live_paper_day}.csv",
    mime="text/csv",
    disabled=event_df.empty,
)

stored_download_cols = st.columns(2)
stored_download_cols[0].download_button(
    "Download five-day trade journal CSV",
    stored_trade_df.to_csv(index=False).encode("utf-8"),
    file_name="five_day_fake_trade_journal.csv",
    mime="text/csv",
    disabled=stored_trade_df.empty,
)
stored_download_cols[1].download_button(
    "Download five-day decision journal CSV",
    stored_event_df.to_csv(index=False).encode("utf-8"),
    file_name="five_day_fake_decision_journal.csv",
    mime="text/csv",
    disabled=stored_event_df.empty,
)

with st.expander("Backtest with actual historical NSE prices", expanded=True):
    st.info(
        "Use this to replay real historical intraday candles through the same paper-trading rules. "
        "Yahoo usually provides 1-minute NSE data only for recent days. Weekends and holidays will show no candles."
    )
    backtest_left, backtest_right = st.columns([1, 2])
    with backtest_left:
        backtest_symbol_options = auto_added_symbols
        backtest_defaults = auto_added_symbols[:5]
        backtest_symbols = st.multiselect(
            "Backtest auto-added announcement stocks only",
            backtest_symbol_options,
            default=backtest_defaults,
            key="historical_backtest_symbols",
        )
        backtest_day = st.date_input(
            "Backtest trading day",
            value=previous_weekday(date.today()),
            key="historical_backtest_day",
        )
        reset_backtest_logs = st.checkbox("Clear old logs before backtest", value=True, key="reset_backtest_logs")
        run_backtest = st.button("Run actual-price backtest", type="primary")
    with backtest_right:
        st.metric("Fake capital", "Rs. 1,00,000")
        st.metric("Data source", "Yahoo NSE historical 1-minute candles")
        st.caption(
            "Example: June 6, 2026 is Saturday, so it has no NSE cash-equity candles. "
            "Use Friday, June 5, 2026 for the nearest trading day."
        )

    if run_backtest:
        if not backtest_symbols:
            st.warning("No eligible NSE announcement stocks are available for backtesting yet.")
        elif pd.Timestamp(backtest_day).weekday() >= 5:
            st.error(f"{backtest_day.strftime('%B %d, %Y')} is a weekend. NSE cash equity was closed.")
        else:
            logger = SQLiteTradeLogger(config.database_path)
            if reset_backtest_logs:
                logger.reset()
            provider = HistoricalYahooNSEMarketDataProvider()
            simulator = IntradaySimulator(config, provider, logger)
            try:
                summary = simulator.run(backtest_symbols, backtest_day)
                st.success(
                    f"Actual-price backtest complete for {backtest_day.isoformat()}. "
                    f"End-of-day fake P&L: Rs. {summary['total_pnl']:.2f}"
                )
            except Exception as exc:
                st.error(str(exc))

    backtest_events = read_table("events")
    backtest_trades = read_table("trades")
    backtest_positions = read_table("open_positions")
    backtest_snapshots = read_table("portfolio_snapshots")

    st.markdown("#### Backtest Trades")
    if not backtest_trades.empty:
        shown_trades = backtest_trades.copy()
        shown_trades["price_source"] = "Yahoo NSE historical candles"
        st.dataframe(shown_trades, use_container_width=True, hide_index=True)
        pnl_chart = shown_trades.sort_values("id").copy()
        pnl_chart["cumulative_pnl"] = pnl_chart["pnl"].cumsum()
        st.line_chart(pnl_chart, x="id", y="cumulative_pnl")
    else:
        st.dataframe(backtest_trades, use_container_width=True, hide_index=True)

    st.markdown("#### Backtest Open Positions")
    st.dataframe(backtest_positions, use_container_width=True, hide_index=True)

    st.markdown("#### Backtest Portfolio Snapshots")
    st.dataframe(backtest_snapshots.head(30), use_container_width=True, hide_index=True)

    st.markdown("#### Backtest Signal And Execution Log")
    st.dataframe(backtest_events, use_container_width=True, hide_index=True)

with st.expander("Optional: synthetic demo paper session", expanded=False):
    st.warning("This demo uses synthetic prices for testing only. It is not live NSE data.")
    left, right = st.columns([1, 2])
    with left:
        symbol_options = watchlist_symbols
        selected_defaults = watchlist_symbols[:3]
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
            st.warning("No auto-added announcement symbols are available for this synthetic test.")
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

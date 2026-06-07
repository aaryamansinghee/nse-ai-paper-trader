from datetime import date
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from paper_trading_simulator.config import TradingConfig
from paper_trading_simulator.engine import IntradaySimulator
from paper_trading_simulator.logger import SQLiteTradeLogger
from paper_trading_simulator.market_data import SimulatedNSEMarketDataProvider, YahooNSELiveQuoteMarketDataProvider, default_symbols


st.set_page_config(page_title="NSE Paper Trading Simulator", layout="wide")

config = TradingConfig()
db_path = Path(config.database_path)

st.title("NSE Cash Equity Paper Trading Simulator")
st.caption("Paper trading only. No real orders can be placed from this app.")
st.info("Use `scripts/run_live_session.py --mode yahoo` or `--mode nse` for current NSE-listed quote monitoring. The button below runs a demo replay only.")

auto_refresh = st.sidebar.checkbox("Auto-refresh monitor", value=True)
refresh_seconds = st.sidebar.slider("Refresh seconds", min_value=5, max_value=60, value=10, step=5)
if auto_refresh:
    components.html(f"<meta http-equiv='refresh' content='{refresh_seconds}'>", height=0)

left, right = st.columns([1, 2])
with left:
    selected_symbols = st.multiselect("Symbols", default_symbols(), default=default_symbols()[:3])
    selected_day = st.date_input("Trading day", value=date.today())
    reset_logs = st.checkbox("Clear old logs before run", value=True)
    run_button = st.button("Run demo paper session", type="primary")

with right:
    st.metric("Fake capital", "Rs. 1,00,000")
    st.metric("Daily profit target", "Rs. 2,500")
    st.metric("Max daily loss", "Rs. 1,200")

if st.checkbox("Show latest NSE-listed prices", value=True):
    try:
        quote_provider = YahooNSELiveQuoteMarketDataProvider(poll_seconds=60)
        quote_rows = []
        for symbol in selected_symbols:
            candle = quote_provider.fetch_latest_candle(symbol)
            if candle:
                quote_rows.append(
                    {
                        "symbol": candle.symbol,
                        "timestamp": candle.timestamp,
                        "latest_price": candle.close,
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "volume": candle.volume,
                        "source": "Yahoo Finance NSE (.NS)",
                    }
                )
        st.dataframe(pd.DataFrame(quote_rows), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.warning(f"Could not fetch latest NSE-listed prices right now: {exc}")

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
        st.success(f"Demo paper session complete. End-of-day P&L: Rs. {summary['total_pnl']:.2f}")


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


events = read_table("events")
trades = read_table("trades")
snapshots = read_table("portfolio_snapshots")
open_positions = read_table("open_positions")
latest_ticks = read_table("latest_ticks")

if not snapshots.empty:
    latest = snapshots.iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Live equity", f"Rs. {latest['equity']:,.2f}")
    c2.metric("Total P&L", f"Rs. {latest['total_pnl']:,.2f}")
    c3.metric("Unrealized P&L", f"Rs. {latest['unrealized_pnl']:,.2f}")
    c4.metric("Open positions", int(latest["open_positions"]))
    c5.metric("Risk status", latest["risk_status"])
elif not events.empty:
    latest_pnl = events.loc[events["event_type"] == "END_OF_DAY_PNL", "pnl"]
    realized = trades["pnl"].sum() if not trades.empty else 0.0
    open_events = len(events[events["event_type"] == "FAKE_EXECUTION"])
    rejected = len(events[events["event_type"] == "REJECTED_TRADE"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest EOD P&L", f"Rs. {latest_pnl.iloc[0]:.2f}" if not latest_pnl.empty else "Rs. 0.00")
    c2.metric("Realized P&L", f"Rs. {realized:.2f}")
    c3.metric("Fake entries", open_events)
    c4.metric("Rejected trades", rejected)

st.subheader("Live ticker")
st.dataframe(latest_ticks, use_container_width=True, hide_index=True)

st.subheader("Open positions")
st.dataframe(open_positions, use_container_width=True, hide_index=True)

st.subheader("Event log")
st.dataframe(events, use_container_width=True, hide_index=True)

st.subheader("Closed trades")
st.dataframe(trades, use_container_width=True, hide_index=True)

if not trades.empty:
    chart_data = trades.sort_values("id").copy()
    chart_data["cumulative_pnl"] = chart_data["pnl"].cumsum()
    st.line_chart(chart_data, x="id", y="cumulative_pnl")

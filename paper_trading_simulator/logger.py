import sqlite3
from pathlib import Path
from typing import Iterable

from .models import ClosedTrade, Execution, Signal


class SQLiteTradeLogger:
    def __init__(self, database_path: str):
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._create_tables()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _create_tables(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    symbol TEXT,
                    strategy TEXT,
                    message TEXT NOT NULL,
                    price REAL,
                    quantity INTEGER,
                    pnl REAL
                );
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    exit_reason TEXT NOT NULL,
                    pnl REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cash REAL NOT NULL,
                    equity REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    total_pnl REAL NOT NULL,
                    open_positions INTEGER NOT NULL,
                    trades_taken INTEGER NOT NULL,
                    risk_status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS open_positions (
                    symbol TEXT PRIMARY KEY,
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss_price REAL NOT NULL,
                    target_price REAL NOT NULL,
                    latest_price REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    strategy TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    last_price REAL NOT NULL,
                    volume INTEGER,
                    source TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS latest_ticks (
                    symbol TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    last_price REAL NOT NULL,
                    volume INTEGER,
                    source TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS live_paper_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trading_day TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    symbol TEXT,
                    message TEXT NOT NULL,
                    price REAL,
                    quantity INTEGER,
                    pnl REAL,
                    UNIQUE(trading_day, timestamp, event_type, symbol, message, price, quantity, pnl)
                );
                CREATE TABLE IF NOT EXISTS live_paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trading_day TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    exit_reason TEXT NOT NULL,
                    pnl REAL NOT NULL,
                    reason TEXT NOT NULL,
                    UNIQUE(trading_day, symbol, entry_time, exit_time, exit_reason)
                );
                """
            )

    def reset(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM events")
            connection.execute("DELETE FROM trades")
            connection.execute("DELETE FROM portfolio_snapshots")
            connection.execute("DELETE FROM open_positions")
            connection.execute("DELETE FROM ticks")
            connection.execute("DELETE FROM latest_ticks")

    def reset_live_paper_journal(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM live_paper_events")
            connection.execute("DELETE FROM live_paper_trades")

    def log_event(self, timestamp, event_type: str, message: str, symbol: str | None = None, strategy: str | None = None, price: float | None = None, quantity: int | None = None, pnl: float | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO events (timestamp, event_type, symbol, strategy, message, price, quantity, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (timestamp.isoformat(), event_type, symbol, strategy, message, price, quantity, pnl),
            )

    def log_signal(self, signal: Signal) -> None:
        self.log_event(signal.timestamp, "SIGNAL", signal.reason, signal.symbol, signal.strategy, signal.price)

    def log_rejection(self, signal: Signal, reason: str) -> None:
        self.log_event(signal.timestamp, "REJECTED_TRADE", reason, signal.symbol, signal.strategy, signal.price)

    def log_execution(self, execution: Execution) -> None:
        self.log_event(execution.timestamp, "FAKE_EXECUTION", execution.reason, execution.symbol, execution.strategy, execution.price, execution.quantity)

    def log_closed_trade(self, trade: ClosedTrade) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trades (symbol, strategy, quantity, entry_price, exit_price, entry_time, exit_time, exit_reason, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.symbol,
                    trade.strategy,
                    trade.quantity,
                    trade.entry_price,
                    trade.exit_price,
                    trade.entry_time.isoformat(),
                    trade.exit_time.isoformat(),
                    trade.exit_reason.value,
                    trade.pnl,
                ),
            )
        self.log_event(trade.exit_time, trade.exit_reason.value, f"Closed trade with P&L Rs. {trade.pnl:.2f}", trade.symbol, trade.strategy, trade.exit_price, trade.quantity, trade.pnl)

    def log_portfolio_snapshot(self, timestamp, portfolio, trades_taken: int, risk_status: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO portfolio_snapshots (
                    timestamp, cash, equity, realized_pnl, unrealized_pnl, total_pnl,
                    open_positions, trades_taken, risk_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp.isoformat(),
                    portfolio.cash,
                    portfolio.equity(),
                    portfolio.realized_pnl(),
                    portfolio.unrealized_pnl(),
                    portfolio.total_pnl(),
                    len(portfolio.positions),
                    trades_taken,
                    risk_status,
                ),
            )
            connection.execute("DELETE FROM open_positions")
            for symbol, position in portfolio.positions.items():
                latest_price = portfolio.latest_prices.get(symbol, position.entry_price)
                connection.execute(
                    """
                    INSERT INTO open_positions (
                        symbol, quantity, entry_price, stop_loss_price, target_price,
                        latest_price, unrealized_pnl, entry_time, strategy
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol,
                        position.quantity,
                        position.entry_price,
                        position.stop_loss_price,
                        position.target_price,
                        latest_price,
                        position.unrealized_pnl(latest_price),
                        position.entry_time.isoformat(),
                        position.strategy,
                    ),
                )

    def log_tick(self, timestamp, symbol: str, last_price: float, volume: int | None, source: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ticks (timestamp, symbol, last_price, volume, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (timestamp.isoformat(), symbol, last_price, volume, source),
            )
            connection.execute(
                """
                INSERT INTO latest_ticks (symbol, timestamp, last_price, volume, source)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    timestamp = excluded.timestamp,
                    last_price = excluded.last_price,
                    volume = excluded.volume,
                    source = excluded.source
                """,
                (symbol, timestamp.isoformat(), last_price, volume, source),
            )

    def log_live_paper_state(self, trading_day: str, state) -> None:
        with self._connect() as connection:
            for event in state.event_log:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO live_paper_events (
                        trading_day, timestamp, event_type, symbol, message, price, quantity, pnl
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trading_day,
                        event.get("timestamp", ""),
                        event.get("event_type", ""),
                        event.get("stock", ""),
                        event.get("message", ""),
                        event.get("price"),
                        event.get("quantity"),
                        event.get("pnl"),
                    ),
                )
            for trade in state.closed_trades:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO live_paper_trades (
                        trading_day, symbol, quantity, entry_price, exit_price,
                        entry_time, exit_time, exit_reason, pnl, reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trading_day,
                        trade.symbol,
                        trade.quantity,
                        trade.entry_price,
                        trade.exit_price,
                        trade.entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                        trade.exit_time.strftime("%Y-%m-%d %H:%M:%S"),
                        trade.exit_reason,
                        trade.pnl,
                        trade.reason,
                    ),
                )

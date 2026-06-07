from collections import defaultdict
from datetime import date

import pandas as pd

from .config import TradingConfig
from .execution import PaperExecutionEngine
from .logger import SQLiteTradeLogger
from .market_data import LiveMarketDataProvider
from .portfolio import PortfolioTracker
from .risk import RiskManager
from .strategies import build_default_strategies


class IntradaySimulator:
    def __init__(self, config: TradingConfig, provider: LiveMarketDataProvider, logger: SQLiteTradeLogger):
        self.config = config
        self.provider = provider
        self.logger = logger
        self.portfolio = PortfolioTracker(config.fake_capital)
        self.risk_manager = RiskManager(config)
        self.execution = PaperExecutionEngine(self.portfolio, self.risk_manager)
        self.strategies = build_default_strategies()
        self.history: dict[str, list[dict]] = defaultdict(list)
        self.square_off_done = False

    def run(self, symbols: list[str], trading_day: date) -> dict:
        self.logger.log_event(
            timestamp=pd.Timestamp(trading_day).to_pydatetime(),
            event_type="START",
            message=f"Paper session started with Rs. {self.config.fake_capital:.2f}",
        )
        for candle in self.provider.stream(symbols, trading_day):
            self.portfolio.mark_price(candle.symbol, candle.close)
            self.history[candle.symbol].append(
                {
                    "timestamp": candle.timestamp,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            )

            closed_trade = self.execution.check_exits(candle.symbol, candle.low, candle.high, candle.close, candle.timestamp)
            if closed_trade:
                self.logger.log_closed_trade(closed_trade)

            if candle.timestamp.time() >= self.config.force_square_off_time:
                if not self.square_off_done:
                    for trade in self.execution.square_off_all(candle.timestamp):
                        self.logger.log_closed_trade(trade)
                    self.square_off_done = True
                    self.logger.log_event(candle.timestamp, "SQUARE_OFF_COMPLETE", "All positions force squared off at 3:20 PM IST")
                continue

            if self.risk_manager.should_stop_trading(self.portfolio):
                self.logger.log_event(candle.timestamp, "TRADING_STOPPED", self.risk_manager.trading_stopped_reason or "Trading stopped", pnl=self.portfolio.total_pnl())
                continue

            history_frame = pd.DataFrame(self.history[candle.symbol])
            for strategy in self.strategies:
                signal = strategy.generate_signal(candle.symbol, history_frame, candle.timestamp)
                if not signal:
                    continue
                self.logger.log_signal(signal)
                execution, rejection_reason = self.execution.try_enter(signal)
                if execution:
                    self.logger.log_execution(execution)
                    break
                self.logger.log_rejection(signal, rejection_reason or "Rejected by risk manager")

            self.logger.log_portfolio_snapshot(
                candle.timestamp,
                self.portfolio,
                self.risk_manager.trades_taken,
                self.risk_manager.trading_stopped_reason or "ACTIVE",
            )

        if self.portfolio.positions:
            last_timestamp = max(price_rows[-1]["timestamp"] for price_rows in self.history.values() if price_rows)
            for trade in self.execution.square_off_all(last_timestamp):
                self.logger.log_closed_trade(trade)

        summary = {
            "starting_capital": self.config.fake_capital,
            "ending_equity": round(self.portfolio.equity(), 2),
            "realized_pnl": round(self.portfolio.realized_pnl(), 2),
            "unrealized_pnl": round(self.portfolio.unrealized_pnl(), 2),
            "total_pnl": round(self.portfolio.total_pnl(), 2),
            "trades_taken": self.risk_manager.trades_taken,
            "closed_trades": len(self.portfolio.closed_trades),
        }
        self.logger.log_event(
            timestamp=pd.Timestamp.now().to_pydatetime(),
            event_type="END_OF_DAY_PNL",
            message=f"End-of-day P&L Rs. {summary['total_pnl']:.2f}",
            pnl=summary["total_pnl"],
        )
        self.logger.log_portfolio_snapshot(
            pd.Timestamp.now().to_pydatetime(),
            self.portfolio,
            self.risk_manager.trades_taken,
            self.risk_manager.trading_stopped_reason or "CLOSED",
        )
        return summary

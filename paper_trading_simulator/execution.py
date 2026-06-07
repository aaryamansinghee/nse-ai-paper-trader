from datetime import datetime

from .models import Execution, ExitReason, Position, Signal, SignalSide
from .portfolio import PortfolioTracker
from .risk import RiskManager


class PaperExecutionEngine:
    """Paper-only execution. This class has no broker API or real-order code."""

    def __init__(self, portfolio: PortfolioTracker, risk_manager: RiskManager):
        self.portfolio = portfolio
        self.risk_manager = risk_manager

    def try_enter(self, signal: Signal):
        decision = self.risk_manager.evaluate_entry(signal, self.portfolio)
        if not decision.approved:
            return None, decision.reason
        position = Position(
            symbol=signal.symbol,
            quantity=decision.quantity,
            entry_price=signal.price,
            stop_loss_price=decision.stop_loss_price,
            target_price=decision.target_price,
            entry_time=signal.timestamp,
            strategy=signal.strategy,
        )
        self.portfolio.open_position(position)
        self.risk_manager.record_trade_taken()
        execution = Execution(signal.timestamp, signal.symbol, SignalSide.BUY, decision.quantity, signal.price, signal.strategy, "Paper buy executed")
        return execution, None

    def check_exits(self, symbol: str, low: float, high: float, close: float, timestamp: datetime):
        if not self.portfolio.has_position(symbol):
            return None
        position = self.portfolio.positions[symbol]
        if low <= position.stop_loss_price:
            return self.portfolio.close_position(symbol, position.stop_loss_price, timestamp, ExitReason.STOP_LOSS)
        if high >= position.target_price:
            return self.portfolio.close_position(symbol, position.target_price, timestamp, ExitReason.TARGET_HIT)
        return None

    def square_off_all(self, timestamp: datetime):
        trades = []
        for symbol in list(self.portfolio.positions):
            exit_price = self.portfolio.latest_prices.get(symbol, self.portfolio.positions[symbol].entry_price)
            trades.append(self.portfolio.close_position(symbol, exit_price, timestamp, ExitReason.SQUARE_OFF))
        return trades


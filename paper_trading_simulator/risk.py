from .config import TradingConfig
from .models import RiskDecision, Signal, SignalSide
from .portfolio import PortfolioTracker


class RiskManager:
    def __init__(self, config: TradingConfig):
        self.config = config
        self.trades_taken = 0
        self.trading_stopped_reason: str | None = None

    def should_stop_trading(self, portfolio: PortfolioTracker) -> bool:
        pnl = portfolio.total_pnl()
        if pnl >= self.config.daily_profit_target:
            self.trading_stopped_reason = f"Daily profit target reached: Rs. {pnl:.2f}"
            return True
        if pnl <= -self.config.max_daily_loss:
            self.trading_stopped_reason = f"Max daily loss reached: Rs. {pnl:.2f}"
            return True
        if self.trades_taken >= self.config.max_trades_per_day:
            self.trading_stopped_reason = "Max trades per day reached"
            return True
        return False

    def evaluate_entry(self, signal: Signal, portfolio: PortfolioTracker) -> RiskDecision:
        if not self.config.paper_trading_only:
            return RiskDecision(False, reason="Configuration must remain paper trading only")
        if signal.side != SignalSide.BUY:
            return RiskDecision(False, reason="NSE cash-equity simulator is long-only; short entries are rejected")
        if self.should_stop_trading(portfolio):
            return RiskDecision(False, reason=self.trading_stopped_reason or "Trading stopped")
        if portfolio.has_position(signal.symbol):
            return RiskDecision(False, reason="Position already open in this symbol")
        if any(trade.symbol == signal.symbol for trade in portfolio.closed_trades):
            return RiskDecision(False, reason="Symbol already traded today; avoiding revenge re-entry")
        if len(portfolio.positions) >= self.config.max_open_positions:
            return RiskDecision(False, reason="Max open positions reached")

        stop_pct = min(max(signal.stop_loss_pct, self.config.min_stop_loss_pct), self.config.max_stop_loss_pct)
        risk_per_share = signal.price * stop_pct
        if risk_per_share <= 0:
            return RiskDecision(False, reason="Invalid risk per share")

        risk_quantity = int(self.config.max_loss_per_trade // risk_per_share)
        position_capital = self.config.fake_capital * self.config.max_position_capital_fraction
        affordable_quantity = int(min(position_capital, portfolio.cash) // signal.price)
        quantity = max(0, min(risk_quantity, affordable_quantity))
        if quantity < 1:
            return RiskDecision(False, reason="Not enough paper cash for risk-controlled quantity")

        stop_loss_price = round(signal.price * (1 - stop_pct), 2)
        target_price = round(signal.price + (signal.price - stop_loss_price) * self.config.target_reward_multiple, 2)
        return RiskDecision(True, quantity, stop_loss_price, target_price, "Approved")

    def record_trade_taken(self) -> None:
        self.trades_taken += 1

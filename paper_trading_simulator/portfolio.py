from datetime import datetime

from .models import ClosedTrade, ExitReason, Position


class PortfolioTracker:
    def __init__(self, starting_capital: float):
        self.starting_capital = starting_capital
        self.cash = starting_capital
        self.positions: dict[str, Position] = {}
        self.closed_trades: list[ClosedTrade] = []
        self.latest_prices: dict[str, float] = {}

    def mark_price(self, symbol: str, price: float) -> None:
        self.latest_prices[symbol] = price

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def open_position(self, position: Position) -> None:
        self.positions[position.symbol] = position
        self.cash -= position.entry_price * position.quantity

    def close_position(self, symbol: str, exit_price: float, exit_time: datetime, reason: ExitReason) -> ClosedTrade:
        position = self.positions.pop(symbol)
        proceeds = exit_price * position.quantity
        self.cash += proceeds
        pnl = (exit_price - position.entry_price) * position.quantity
        trade = ClosedTrade(
            symbol=symbol,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=exit_time,
            strategy=position.strategy,
            exit_reason=reason,
            pnl=pnl,
        )
        self.closed_trades.append(trade)
        return trade

    def realized_pnl(self) -> float:
        return sum(trade.pnl for trade in self.closed_trades)

    def unrealized_pnl(self) -> float:
        total = 0.0
        for symbol, position in self.positions.items():
            total += position.unrealized_pnl(self.latest_prices.get(symbol, position.entry_price))
        return total

    def total_pnl(self) -> float:
        return self.realized_pnl() + self.unrealized_pnl()

    def equity(self) -> float:
        return self.cash + sum(
            position.quantity * self.latest_prices.get(symbol, position.entry_price)
            for symbol, position in self.positions.items()
        )


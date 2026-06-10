from dataclasses import dataclass, field
from datetime import datetime, time

from .config import TradingConfig


@dataclass
class LivePaperPosition:
    symbol: str
    quantity: int
    entry_price: float
    latest_price: float
    stop_loss: float
    target: float
    entry_time: datetime
    reason: str
    confidence_score: int
    highest_price: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        return round((self.latest_price - self.entry_price) * self.quantity, 2)


@dataclass
class LivePaperTrade:
    symbol: str
    quantity: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    exit_reason: str
    pnl: float
    reason: str


@dataclass
class LivePaperState:
    cash: float
    positions: dict[str, LivePaperPosition] = field(default_factory=dict)
    closed_trades: list[LivePaperTrade] = field(default_factory=list)
    event_log: list[dict] = field(default_factory=list)
    trades_taken: int = 0
    stopped_reason: str | None = None

    def realized_pnl(self) -> float:
        return round(sum(trade.pnl for trade in self.closed_trades), 2)

    def unrealized_pnl(self) -> float:
        return round(sum(position.unrealized_pnl for position in self.positions.values()), 2)

    def total_pnl(self) -> float:
        return round(self.realized_pnl() + self.unrealized_pnl(), 2)

    def equity(self) -> float:
        invested = sum(position.latest_price * position.quantity for position in self.positions.values())
        return round(self.cash + invested, 2)


class LivePaperTrader:
    def __init__(self, config: TradingConfig):
        self.config = config

    def create_state(self) -> LivePaperState:
        return LivePaperState(cash=self.config.fake_capital)

    def process_setups(self, state: LivePaperState, setup_rows: list[dict], now: datetime) -> LivePaperState:
        prices = {row["stock"]: float(row["LTP"]) for row in setup_rows if row.get("LTP")}
        self._mark_positions(state, prices)
        self._check_exits(state, prices, now)

        if now.time() >= self.config.force_square_off_time:
            self._square_off_all(state, prices, now, "FORCE_SQUARE_OFF_3_20_PM")
            state.stopped_reason = "Force square-off completed at 3:20 PM IST"
            return state

        if now.time() >= self.config.opening_window_square_off_time:
            self._square_off_all(state, prices, now, "OPENING_WINDOW_EXIT_9_45_AM")
            self._log_once(state, "OPENING_WINDOW_CLOSED", "Opening-volume paper trading window closed at 9:45 AM IST")
            return state

        if not self._inside_market_hours(now.time()):
            self._log_once(state, "SYSTEM", "Waiting for NSE cash market hours: 9:15 AM to 3:30 PM IST")
            return state

        stop_reason = self._risk_stop_reason(state)
        if stop_reason:
            state.stopped_reason = stop_reason
            self._square_off_all(state, prices, now, "RISK_STOP_SQUARE_OFF")
            self._log_once(state, "RISK_STOP", stop_reason)
            return state

        for row in sorted(setup_rows, key=lambda item: item.get("confidence score", 0), reverse=True):
            self._try_enter(state, row, now)
        return state

    def _try_enter(self, state: LivePaperState, row: dict, now: datetime) -> None:
        symbol = row["stock"]
        signal = row.get("signal")
        confidence = int(row.get("confidence score") or 0)
        ltp = float(row.get("LTP") or 0)
        trigger = float(row.get("trigger price") or 0)
        stop_loss = float(row.get("stop loss") or 0)
        target = float(row.get("target") or 0)
        quote_status = row.get("quote status", "")
        sentiment = row.get("sentiment", "")
        announcement_eligible = row.get("announcement eligible") == "YES"
        ai_decision = row.get("AI decision", "")
        scanner_lane = row.get("scanner lane", "")

        protection_reason = self._capital_protection_entry_stop(state)
        if protection_reason:
            self._log_rejection(state, symbol, protection_reason, now)
            return
        if not announcement_eligible:
            return
        if scanner_lane != "EXPLOSIVE":
            self._log_rejection(state, symbol, "Rejected: fake trading is restricted to Explosive Movers only", now)
            return
        if sentiment != "positive":
            return
        if ai_decision != "TRADE_READY":
            return
        if signal != "BUY WATCH" or confidence < 75:
            return
        if quote_status != "Updating":
            self._log_rejection(state, symbol, f"Rejected: quote status is not live/updating ({quote_status})", now)
            return
        if now.time() < self.config.first_entry_time:
            self._log_rejection(state, symbol, "Rejected: no fake entries before 9:16 AM IST", now)
            return
        if now.time() > self.config.last_entry_time:
            self._log_rejection(state, symbol, "Rejected: fresh opening-window entries allowed only from 9:16 AM to 9:40 AM IST", now)
            return
        if ltp <= 0 or trigger <= 0 or stop_loss <= 0 or target <= 0:
            self._log_rejection(state, symbol, "Rejected: invalid price, trigger, stop loss, or target", now)
            return
        if symbol in state.positions:
            return
        if any(trade.symbol == symbol for trade in state.closed_trades):
            self._log_rejection(state, symbol, "Rejected: symbol already traded today", now)
            return
        if len(state.positions) >= self.config.max_open_positions:
            self._log_rejection(state, symbol, "Rejected: max 2 open paper positions reached", now)
            return
        if state.trades_taken >= self.config.max_trades_per_day:
            self._log_rejection(state, symbol, "Rejected: max 3 paper trades reached", now)
            return
        if ltp < trigger:
            return
        if stop_loss >= ltp:
            self._log_rejection(state, symbol, "Rejected: stop loss must be below fake entry price", now)
            return
        if target <= ltp:
            self._log_rejection(state, symbol, "Rejected: target must be above fake entry price", now)
            return
        risk_per_share = max(ltp - stop_loss, ltp * self.config.min_stop_loss_pct)
        quantity_by_risk = int(self.config.max_loss_per_trade // risk_per_share)
        quantity_by_cash = int(state.cash // ltp)
        capital_cap = self._capital_cap_for_trade(row, ltp)
        quantity_by_cap = int(capital_cap // ltp)
        quantity = max(0, min(quantity_by_risk, quantity_by_cash, quantity_by_cap))
        if quantity < 1:
            self._log_rejection(state, symbol, "Rejected: not enough fake cash for risk-controlled quantity", now)
            return

        state.cash = round(state.cash - quantity * ltp, 2)
        state.positions[symbol] = LivePaperPosition(
            symbol=symbol,
            quantity=quantity,
            entry_price=ltp,
            latest_price=ltp,
            stop_loss=stop_loss,
            target=target,
            entry_time=now,
            reason=row.get("reason for trade", ""),
            confidence_score=confidence,
            highest_price=ltp,
        )
        state.trades_taken += 1
        self._log_event(
            state,
            now,
            "FAKE_BUY",
            symbol,
            f"Fake buy executed at Rs. {ltp:.2f}. Deployed about Rs. {quantity * ltp:,.2f} "
            f"against capital cap Rs. {capital_cap:,.2f}. AI waited for trigger Rs. {trigger:.2f}. "
            f"Reason: {row.get('reason for trade', '')}",
            ltp,
            quantity,
            None,
        )

    @staticmethod
    def _capital_cap_for_trade(row: dict, entry_price: float) -> float:
        target = float(row.get("target") or 0)
        confidence = int(row.get("confidence score") or 0)
        if entry_price <= 0 or target <= entry_price:
            return 20000.0
        target_pct = (target - entry_price) / entry_price
        if target_pct >= 0.15:
            return 40000.0 if confidence >= 88 else 35000.0
        if target_pct >= 0.10:
            return 35000.0
        if target_pct >= 0.05:
            return 25000.0
        return 20000.0

    def _mark_positions(self, state: LivePaperState, prices: dict[str, float]) -> None:
        for symbol, position in state.positions.items():
            if symbol in prices:
                position.latest_price = prices[symbol]
                previous_high = getattr(position, "highest_price", 0.0) or position.entry_price
                position.highest_price = max(previous_high, position.latest_price)

    def _check_exits(self, state: LivePaperState, prices: dict[str, float], now: datetime) -> None:
        for symbol, position in list(state.positions.items()):
            price = prices.get(symbol, position.latest_price)
            active_stop, stop_reason = self._active_stop(position)
            if price <= active_stop:
                position.stop_loss = active_stop
                self._close_position(state, symbol, price, now, stop_reason)
            elif price <= position.stop_loss:
                self._close_position(state, symbol, price, now, "STOP_LOSS")
            elif price >= position.target:
                self._close_position(state, symbol, price, now, "TARGET_HIT")

    @staticmethod
    def _active_stop(position: LivePaperPosition) -> tuple[float, str]:
        highest = max(getattr(position, "highest_price", 0.0) or position.entry_price, position.latest_price)
        gain_pct = (highest - position.entry_price) / position.entry_price if position.entry_price else 0
        active_stop = position.stop_loss
        reason = "STOP_LOSS"
        if gain_pct >= 0.03:
            active_stop = max(active_stop, highest * 0.985, position.entry_price * 1.006)
            reason = "TRAILING_PROFIT_STOP"
        elif gain_pct >= 0.015:
            active_stop = max(active_stop, position.entry_price * 1.001)
            reason = "BREAKEVEN_PROTECTION_STOP"
        return round(active_stop, 2), reason

    def _square_off_all(self, state: LivePaperState, prices: dict[str, float], now: datetime, reason: str) -> None:
        for symbol in list(state.positions):
            position = state.positions[symbol]
            self._close_position(state, symbol, prices.get(symbol, position.latest_price), now, reason)

    def _close_position(self, state: LivePaperState, symbol: str, exit_price: float, now: datetime, reason: str) -> None:
        position = state.positions.pop(symbol)
        state.cash = round(state.cash + position.quantity * exit_price, 2)
        pnl = round((exit_price - position.entry_price) * position.quantity, 2)
        trade = LivePaperTrade(
            symbol=symbol,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=now,
            exit_reason=reason,
            pnl=pnl,
            reason=position.reason,
        )
        state.closed_trades.append(trade)
        self._log_event(state, now, reason, symbol, f"Paper position closed. P&L Rs. {pnl:.2f}", exit_price, position.quantity, pnl)

    def _risk_stop_reason(self, state: LivePaperState) -> str | None:
        pnl = state.total_pnl()
        if pnl >= self.config.daily_profit_target:
            return f"Daily fake profit target reached: Rs. {pnl:.2f}"
        if pnl <= -self.config.max_daily_loss:
            return f"Max daily fake loss reached: Rs. {pnl:.2f}"
        return None

    def _capital_protection_entry_stop(self, state: LivePaperState) -> str | None:
        realized = state.realized_pnl()
        if self.config.lock_after_first_profitable_trade and any(trade.pnl > 0 for trade in state.closed_trades):
            return "Rejected: profitable trade already booked; locking the green paper day"
        if realized <= -self.config.morning_capital_protection_loss:
            return f"Rejected: morning protection active after Rs. {realized:.2f} realized P&L"
        recent_losses = 0
        for trade in reversed(state.closed_trades):
            if trade.pnl < 0:
                recent_losses += 1
            else:
                break
        if recent_losses >= self.config.stop_after_consecutive_losses:
            return f"Rejected: {recent_losses} consecutive losing paper trades; stopping fresh entries"
        return None

    def _inside_market_hours(self, current_time: time) -> bool:
        return self.config.market_open_time <= current_time <= self.config.market_close_time

    def _log_rejection(self, state: LivePaperState, symbol: str, message: str, now: datetime) -> None:
        self._log_event(state, now, "REJECTED_FAKE_TRADE", symbol, message, None, None, None)

    def _log_once(self, state: LivePaperState, event_type: str, message: str) -> None:
        if state.event_log and state.event_log[0]["event_type"] == event_type and state.event_log[0]["message"] == message:
            return
        self._log_event(state, datetime.now(), event_type, None, message, None, None, None)

    def _log_event(
        self,
        state: LivePaperState,
        timestamp: datetime,
        event_type: str,
        symbol: str | None,
        message: str,
        price: float | None,
        quantity: int | None,
        pnl: float | None,
    ) -> None:
        state.event_log.insert(
            0,
            {
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "event_type": event_type,
                "stock": symbol or "",
                "message": message,
                "price": price,
                "quantity": quantity,
                "pnl": pnl,
            },
        )
        state.event_log = state.event_log[:200]

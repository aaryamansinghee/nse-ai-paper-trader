from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class SignalSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TARGET_HIT = "TARGET_HIT"
    SQUARE_OFF = "SQUARE_OFF"
    STRATEGY_EXIT = "STRATEGY_EXIT"


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class Signal:
    timestamp: datetime
    symbol: str
    side: SignalSide
    strategy: str
    price: float
    stop_loss_pct: float
    reason: str


@dataclass
class Position:
    symbol: str
    quantity: int
    entry_price: float
    stop_loss_price: float
    target_price: float
    entry_time: datetime
    strategy: str

    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.quantity


@dataclass(frozen=True)
class Execution:
    timestamp: datetime
    symbol: str
    side: SignalSide
    quantity: int
    price: float
    strategy: str
    reason: str


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str
    quantity: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    strategy: str
    exit_reason: ExitReason
    pnl: float


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    quantity: int = 0
    stop_loss_price: Optional[float] = None
    target_price: Optional[float] = None
    reason: str = ""


from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class TradingConfig:
    fake_capital: float = 100000.0
    daily_profit_target: float = 2500.0
    max_daily_loss: float = 1000.0
    min_stop_loss_pct: float = 0.005
    max_stop_loss_pct: float = 0.005
    max_loss_per_trade: float = 400.0
    max_trades_per_day: int = 3
    max_open_positions: int = 2
    force_square_off_time: time = time(15, 20)
    market_open_time: time = time(9, 15)
    first_entry_time: time = time(9, 20)
    last_entry_time: time = time(9, 40)
    opening_window_square_off_time: time = time(9, 45)
    market_close_time: time = time(15, 30)
    opening_range_minutes: int = 15
    target_reward_multiple: float = 2.55
    max_position_capital_fraction: float = 1.00
    database_path: str = "data/paper_trading.db"
    paper_trading_only: bool = True


DEFAULT_SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

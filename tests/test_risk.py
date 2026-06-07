from datetime import datetime
import unittest

from paper_trading_simulator.config import TradingConfig
from paper_trading_simulator.models import Signal, SignalSide
from paper_trading_simulator.portfolio import PortfolioTracker
from paper_trading_simulator.risk import RiskManager


class RiskManagerTests(unittest.TestCase):
    def test_short_entries_are_rejected(self) -> None:
        config = TradingConfig()
        portfolio = PortfolioTracker(config.fake_capital)
        risk = RiskManager(config)
        signal = Signal(datetime.now(), "RELIANCE", SignalSide.SELL, "test", 1000.0, 0.003, "short test")
        decision = risk.evaluate_entry(signal, portfolio)
        self.assertFalse(decision.approved)
        self.assertIn("long-only", decision.reason)

    def test_position_size_respects_max_trade_loss(self) -> None:
        config = TradingConfig()
        portfolio = PortfolioTracker(config.fake_capital)
        risk = RiskManager(config)
        signal = Signal(datetime.now(), "RELIANCE", SignalSide.BUY, "test", 1000.0, 0.005, "buy test")
        decision = risk.evaluate_entry(signal, portfolio)
        self.assertTrue(decision.approved)
        per_share_loss = signal.price - decision.stop_loss_price
        self.assertLessEqual(decision.quantity * per_share_loss, config.max_loss_per_trade + 1)


if __name__ == "__main__":
    unittest.main()

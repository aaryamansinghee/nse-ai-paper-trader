from datetime import datetime, time
import unittest

from paper_trading_simulator.config import TradingConfig
from paper_trading_simulator.live_paper import LivePaperTrader


class LivePaperTraderTests(unittest.TestCase):
    def setUp(self):
        self.trader = LivePaperTrader(TradingConfig())
        self.now = datetime.combine(datetime.today(), time(9, 30))
        self.row = {
            "stock": "ABC",
            "LTP": 252.0,
            "trigger price": 252.0,
            "stop loss": 250.99,
            "target": 270.0,
            "signal": "BUY WATCH",
            "confidence score": 82,
            "reason for trade": "Positive NSE announcement; trigger reached",
            "quote status": "Updating",
            "sentiment": "positive",
            "AI decision": "TRADE_READY",
            "announcement eligible": "YES",
        }

    def test_rejects_ineligible_announcement_row(self):
        state = self.trader.create_state()
        row = dict(self.row, **{"announcement eligible": "NO"})
        self.trader.process_setups(state, [row], self.now)
        self.assertEqual(len(state.positions), 0)

    def test_rejects_stale_quote(self):
        state = self.trader.create_state()
        row = dict(self.row, **{"quote status": "Market closed / last session"})
        self.trader.process_setups(state, [row], self.now)
        self.assertEqual(len(state.positions), 0)

    def test_rejects_invalid_stop_and_target(self):
        state = self.trader.create_state()
        bad_stop = dict(self.row, **{"stop loss": 253.0})
        bad_target = dict(self.row, **{"target": 251.0})
        self.trader.process_setups(state, [bad_stop, bad_target], self.now)
        self.assertEqual(len(state.positions), 0)

    def test_accepts_valid_trade_ready_row(self):
        state = self.trader.create_state()
        self.trader.process_setups(state, [self.row], self.now)
        self.assertEqual(len(state.positions), 1)
        self.assertEqual(state.trades_taken, 1)


if __name__ == "__main__":
    unittest.main()

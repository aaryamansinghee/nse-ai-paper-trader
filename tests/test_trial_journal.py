from datetime import datetime
import sqlite3
import tempfile
import unittest

from paper_trading_simulator.config import TradingConfig
from paper_trading_simulator.live_paper import LivePaperTrader
from paper_trading_simulator.logger import SQLiteTradeLogger


class TrialJournalTests(unittest.TestCase):
    def test_live_paper_journal_ignores_refresh_duplicates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = f"{temp_dir}/paper.db"
            logger = SQLiteTradeLogger(db_path)
            trader = LivePaperTrader(TradingConfig())
            state = trader.create_state()
            now = datetime(2026, 6, 8, 9, 30)
            row = {
                "stock": "ABC",
                "LTP": 252.0,
                "trigger price": 252.0,
                "stop loss": 250.99,
                "target": 253.0,
                "signal": "BUY WATCH",
                "confidence score": 82,
                "reason for trade": "Positive NSE announcement; trigger reached",
                "quote status": "Updating",
                "sentiment": "positive",
                "AI decision": "TRADE_READY",
                "announcement eligible": "YES",
            }

            trader.process_setups(state, [row], now)
            trader.process_setups(state, [dict(row, **{"LTP": 253.0})], datetime(2026, 6, 8, 9, 40))
            logger.log_live_paper_state("2026-06-08", state)
            logger.log_live_paper_state("2026-06-08", state)

            with sqlite3.connect(db_path) as connection:
                trade_count = connection.execute("SELECT COUNT(*) FROM live_paper_trades").fetchone()[0]
                event_count = connection.execute("SELECT COUNT(*) FROM live_paper_events").fetchone()[0]

            self.assertEqual(trade_count, 1)
            self.assertGreaterEqual(event_count, 2)


if __name__ == "__main__":
    unittest.main()

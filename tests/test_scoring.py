from datetime import datetime
import unittest

from paper_trading_simulator.announcements import CorporateAnnouncement
from paper_trading_simulator.models import Candle
from paper_trading_simulator.scoring import score_trade_setup
from paper_trading_simulator.sentiment import SentimentResult


class StrategyScoringTests(unittest.TestCase):
    def test_actionable_announcement_gets_weighted_breakdown(self):
        announcement = CorporateAnnouncement(
            symbol="ABC",
            company="ABC Limited",
            headline="Company wins large order contract",
            details="Large order win from a reputed customer",
            published_at=datetime(2026, 6, 8, 9, 20),
            source="NSE Corporate Announcements",
        )
        candle = Candle(
            timestamp=datetime(2026, 6, 8, 9, 35),
            symbol="ABC",
            open=248.0,
            high=252.0,
            low=247.5,
            close=251.5,
            volume=650000,
            previous_close=246.0,
        )
        sentiment = SentimentResult("positive", 35, "Positive catalyst words")

        score = score_trade_setup(announcement, sentiment, candle)

        self.assertEqual(score.signal, "BUY WATCH")
        self.assertGreaterEqual(score.confidence_score, 75)
        self.assertGreater(score.catalyst_points, 0)
        self.assertGreater(score.liquidity_points, 0)
        self.assertGreater(score.market_structure_points, 0)
        self.assertGreater(score.risk_reward_points, 0)
        self.assertIn("risk/reward score", score.reason_for_trade)

    def test_routine_announcement_is_not_tradeable(self):
        announcement = CorporateAnnouncement(
            symbol="XYZ",
            company="XYZ Limited",
            headline="Shareholding Pattern for the quarter",
            details="Routine disclosure",
            published_at=datetime(2026, 6, 8, 9, 20),
            source="NSE Corporate Announcements",
        )
        candle = Candle(
            timestamp=datetime(2026, 6, 8, 9, 35),
            symbol="XYZ",
            open=310.0,
            high=315.0,
            low=309.0,
            close=314.0,
            volume=800000,
            previous_close=308.0,
        )
        sentiment = SentimentResult("ignore", 0, "Routine filing")

        score = score_trade_setup(announcement, sentiment, candle)

        self.assertEqual(score.signal, "IGNORE")
        self.assertLess(score.confidence_score, 75)
        self.assertEqual(score.catalyst_points, 0)


if __name__ == "__main__":
    unittest.main()

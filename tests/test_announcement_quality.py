import unittest

from paper_trading_simulator.announcement_quality import classify_announcement_quality


class AnnouncementQualityTests(unittest.TestCase):
    def test_order_win_is_actionable(self):
        result = classify_announcement_quality("Company wins large order contract", "")
        self.assertEqual(result.action, "CONSIDER")
        self.assertEqual(result.category, "order/deal win")
        self.assertGreaterEqual(result.quality_score, 20)

    def test_routine_filing_is_ignored(self):
        result = classify_announcement_quality("Shareholding Pattern for the quarter", "")
        self.assertEqual(result.action, "IGNORE")
        self.assertLess(result.quality_score, 0)

    def test_governance_risk_is_rejected(self):
        result = classify_announcement_quality("Company receives penalty and show cause notice", "")
        self.assertEqual(result.action, "REJECT")
        self.assertLess(result.quality_score, 0)


if __name__ == "__main__":
    unittest.main()

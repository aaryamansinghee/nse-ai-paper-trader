from datetime import datetime
import unittest

from paper_trading_simulator.market_data import KiteQuoteSnapshotProvider


class KiteSnapshotTests(unittest.TestCase):
    def test_quote_payload_converts_to_candle(self):
        quote = {
            "last_price": 252.5,
            "volume": 1200000,
            "timestamp": datetime(2026, 6, 8, 9, 25, 18),
            "ohlc": {
                "open": 248.0,
                "high": 253.0,
                "low": 247.0,
                "close": 246.0,
            },
        }

        candle = KiteQuoteSnapshotProvider._quote_to_candle("ABC", quote)

        self.assertEqual(candle.symbol, "ABC")
        self.assertEqual(candle.close, 252.5)
        self.assertEqual(candle.volume, 1200000)
        self.assertEqual(candle.previous_close, 246.0)
        self.assertEqual(candle.timestamp.second, 0)

    def test_empty_last_price_is_skipped(self):
        candle = KiteQuoteSnapshotProvider._quote_to_candle("ABC", {"last_price": 0})

        self.assertIsNone(candle)


if __name__ == "__main__":
    unittest.main()

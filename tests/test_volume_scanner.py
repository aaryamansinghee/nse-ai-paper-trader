from datetime import datetime
import unittest

from paper_trading_simulator.models import Candle
from paper_trading_simulator.volume_scanner import scan_explosive_movers, scan_volume_setups, sector_leaders_from_quotes


class VolumeScannerTests(unittest.TestCase):
    def test_opening_momentum_ranks_and_scores_positive_volume_pressure(self):
        quotes = {
            "ABC": {
                "candle": Candle(
                    timestamp=datetime(2026, 6, 8, 9, 45),
                    symbol="ABC",
                    open=248.0,
                    high=253.0,
                    low=247.0,
                    close=252.5,
                    volume=1200000,
                    previous_close=247.0,
                ),
                "source": "Yahoo Finance NSE (.NS)",
                "status": "Updating",
            },
            "XYZ": {
                "candle": Candle(
                    timestamp=datetime(2026, 6, 8, 9, 45),
                    symbol="XYZ",
                    open=410.0,
                    high=412.0,
                    low=405.0,
                    close=408.0,
                    volume=200000,
                    previous_close=409.0,
                ),
                "source": "Yahoo Finance NSE (.NS)",
                "status": "Updating",
            },
        }

        setups = scan_volume_setups(quotes, min_ltp=200, max_ltp=1000, top_n=5)

        self.assertEqual(setups[0].symbol, "ABC")
        self.assertGreaterEqual(setups[0].confidence_score, 70)
        self.assertLessEqual(setups[0].trigger_price, round(setups[0].ltp * 1.004, 2))
        self.assertEqual(setups[0].stop_loss, round(setups[0].trigger_price * 0.995, 2))
        self.assertIn(setups[0].signal, {"BUY WATCH", "WAIT"})
        self.assertIn("RVOL", setups[0].reason)

    def test_opening_momentum_filters_outside_price_range_and_stale_quotes(self):
        quotes = {
            "HIGH": {
                "candle": Candle(datetime(2026, 6, 8, 9, 45), "HIGH", 1200, 1210, 1190, 1205, 900000, 1190),
                "source": "Yahoo Finance NSE (.NS)",
                "status": "Updating",
            },
            "STALE": {
                "candle": Candle(datetime(2026, 6, 8, 9, 45), "STALE", 250, 255, 248, 254, 900000, 249),
                "source": "Yahoo Finance NSE (.NS)",
                "status": "Market closed / last session",
            },
        }

        setups = scan_volume_setups(quotes, min_ltp=200, max_ltp=1000, top_n=5)

        self.assertEqual(setups, [])

    def test_sector_leaders_are_reported(self):
        quotes = {
            "SBIN": {
                "candle": Candle(datetime(2026, 6, 8, 9, 45), "SBIN", 610, 630, 608, 628, 2500000, 600),
                "source": "Yahoo Finance NSE (.NS)",
                "status": "Updating",
            },
            "ICICIBANK": {
                "candle": Candle(datetime(2026, 6, 8, 9, 45), "ICICIBANK", 940, 955, 938, 952, 1800000, 930),
                "source": "Yahoo Finance NSE (.NS)",
                "status": "Updating",
            },
        }

        leaders = sector_leaders_from_quotes(quotes, min_ltp=100, max_ltp=1000)

        self.assertEqual(leaders[0]["sector"], "Banking")
        self.assertGreater(leaders[0]["sector score"], 0)

    def test_explosive_mover_lane_captures_occlltd_style_smallcap(self):
        quotes = {
            "OCCLLTD": {
                "candle": Candle(
                    timestamp=datetime(2026, 6, 8, 9, 35),
                    symbol="OCCLLTD",
                    open=115.5,
                    high=135.0,
                    low=115.5,
                    close=133.59,
                    volume=192942,
                    previous_close=115.67,
                ),
                "source": "Kite",
                "status": "Updating",
            },
            "LARGECAP": {
                "candle": Candle(
                    timestamp=datetime(2026, 6, 8, 9, 35),
                    symbol="LARGECAP",
                    open=500,
                    high=506,
                    low=498,
                    close=504,
                    volume=900000,
                    previous_close=500,
                ),
                "source": "Kite",
                "status": "Updating",
            },
        }

        setups = scan_explosive_movers(quotes, min_ltp=100, max_ltp=1000, top_n=5, min_change_pct=2)

        self.assertEqual(setups[0].symbol, "OCCLLTD")
        self.assertGreaterEqual(setups[0].confidence_score, 70)
        self.assertIn("Explosive Mover", setups[0].strategy)
        self.assertGreaterEqual(setups[0].relative_volume, 1.2)
        self.assertGreaterEqual(setups[0].target, round(setups[0].trigger_price * 1.10, 2))
        self.assertEqual(setups[0].stop_loss, round(setups[0].trigger_price * 0.9975, 2))

    def test_explosive_mover_lane_captures_early_two_percent_move(self):
        quotes = {
            "EARLYRUN": {
                "candle": Candle(
                    timestamp=datetime(2026, 6, 8, 9, 22),
                    symbol="EARLYRUN",
                    open=205.0,
                    high=211.0,
                    low=204.5,
                    close=210.2,
                    volume=180000,
                    previous_close=205.4,
                ),
                "source": "Kite",
                "status": "Updating",
            },
        }

        setups = scan_explosive_movers(quotes, min_ltp=100, max_ltp=1000, top_n=5, min_change_pct=2)

        self.assertEqual(setups[0].symbol, "EARLYRUN")
        self.assertGreaterEqual(setups[0].change_pct, 2)
        self.assertGreaterEqual(setups[0].confidence_score, 58)
        self.assertGreaterEqual(setups[0].target, round(setups[0].trigger_price * 1.05, 2))
        self.assertEqual(setups[0].stop_loss, round(setups[0].trigger_price * 0.995, 2))
        self.assertIn(setups[0].ai_decision, {"WAIT", "WAIT_FOR_TRIGGER", "TRADE_READY"})

    def test_explosive_mover_default_filters_out_small_two_percent_moves(self):
        quotes = {
            "EARLYRUN": {
                "candle": Candle(
                    timestamp=datetime(2026, 6, 8, 9, 22),
                    symbol="EARLYRUN",
                    open=205.0,
                    high=211.0,
                    low=204.5,
                    close=210.2,
                    volume=180000,
                    previous_close=205.4,
                ),
                "source": "Kite",
                "status": "Updating",
            },
        }

        setups = scan_explosive_movers(quotes, min_ltp=100, max_ltp=1000, top_n=5)

        self.assertEqual(setups, [])

    def test_near_day_high_early_setup_can_be_trade_ready(self):
        quotes = {
            "JAYBARMARU": {
                "candle": Candle(
                    timestamp=datetime(2026, 6, 9, 9, 28),
                    symbol="JAYBARMARU",
                    open=136.0,
                    high=140.76,
                    low=135.5,
                    close=140.76,
                    volume=3887000,
                    previous_close=128.0,
                ),
                "source": "Kite",
                "status": "Updating",
            },
        }

        setups = scan_explosive_movers(quotes, min_ltp=100, max_ltp=1000, top_n=5)

        self.assertEqual(setups[0].trigger_price, setups[0].ltp)
        self.assertEqual(setups[0].signal, "BUY WATCH")
        self.assertEqual(setups[0].ai_decision, "TRADE_READY")

    def test_stretched_from_open_setup_is_not_chased(self):
        quotes = {
            "THOMASCOOK": {
                "candle": Candle(
                    timestamp=datetime(2026, 6, 9, 9, 35),
                    symbol="THOMASCOOK",
                    open=105.48,
                    high=112.24,
                    low=105.48,
                    close=112.24,
                    volume=2600000,
                    previous_close=104.82,
                ),
                "source": "Kite",
                "status": "Updating",
            },
        }

        setups = scan_explosive_movers(quotes, min_ltp=100, max_ltp=1000, top_n=5)

        self.assertEqual(setups[0].signal, "BUY WATCH")
        self.assertEqual(setups[0].ai_decision, "WAIT_CHASE_TOO_LATE")


if __name__ == "__main__":
    unittest.main()

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
            "scanner lane": "EXPLOSIVE",
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

    def test_rejects_non_explosive_rows(self):
        state = self.trader.create_state()
        row = dict(self.row, **{"scanner lane": "OPENING_MOMENTUM"})
        self.trader.process_setups(state, [row], self.now)
        self.assertEqual(len(state.positions), 0)

    def test_position_size_uses_target_based_cap(self):
        state = self.trader.create_state()
        five_percent_row = dict(self.row, **{"LTP": 100.0, "trigger price": 100.0, "stop loss": 99.5, "target": 105.0})
        self.trader.process_setups(state, [five_percent_row], self.now)

        position = state.positions["ABC"]

        self.assertEqual(position.quantity, 250)
        self.assertEqual(round(position.quantity * position.entry_price, 2), 25000.0)

    def test_position_size_uses_larger_cap_for_ten_percent_target(self):
        state = self.trader.create_state()
        ten_percent_row = dict(self.row, **{"LTP": 100.0, "trigger price": 100.0, "stop loss": 99.75, "target": 110.0})
        self.trader.process_setups(state, [ten_percent_row], self.now)

        position = state.positions["ABC"]

        self.assertEqual(position.quantity, 350)
        self.assertEqual(round(position.quantity * position.entry_price, 2), 35000.0)

    def test_rejects_entry_before_916(self):
        state = self.trader.create_state()
        early = datetime.combine(datetime.today(), time(9, 15))
        self.trader.process_setups(state, [self.row], early)
        self.assertEqual(len(state.positions), 0)

    def test_rejects_late_fresh_entry(self):
        state = self.trader.create_state()
        late = datetime.combine(datetime.today(), time(9, 41))
        self.trader.process_setups(state, [self.row], late)
        self.assertEqual(len(state.positions), 0)

    def test_exits_open_position_at_945_opening_window_close(self):
        state = self.trader.create_state()
        self.trader.process_setups(state, [self.row], self.now)
        later = datetime.combine(datetime.today(), time(9, 45))
        exit_row = dict(self.row, **{"LTP": 253.0})

        self.trader.process_setups(state, [exit_row], later)

        self.assertEqual(len(state.positions), 0)
        self.assertEqual(len(state.closed_trades), 1)
        self.assertEqual(state.closed_trades[0].exit_reason, "OPENING_WINDOW_EXIT_9_45_AM")

    def test_max_trades_reached_does_not_square_off_open_position(self):
        state = self.trader.create_state()
        state.trades_taken = self.trader.config.max_trades_per_day
        state.positions["ABC"] = self.trader.process_setups(self.trader.create_state(), [self.row], self.now).positions["ABC"]
        later_row = dict(self.row, **{"LTP": 253.0})

        self.trader.process_setups(state, [later_row], self.now)

        self.assertEqual(len(state.positions), 1)
        self.assertEqual(len(state.closed_trades), 0)

    def test_profitable_trade_locks_new_entries(self):
        state = self.trader.create_state()
        self.trader.process_setups(state, [self.row], self.now)
        self.trader.process_setups(state, [dict(self.row, **{"LTP": 270.0})], self.now)
        next_row = dict(self.row, **{"stock": "XYZ"})

        self.trader.process_setups(state, [next_row], self.now)

        self.assertEqual(len(state.closed_trades), 1)
        self.assertEqual(len(state.positions), 0)

    def test_two_consecutive_losses_stop_new_entries(self):
        state = self.trader.create_state()
        first_loss = dict(self.row, **{"stock": "AAA"})
        second_loss = dict(self.row, **{"stock": "BBB"})
        third_trade = dict(self.row, **{"stock": "CCC"})

        self.trader.process_setups(state, [first_loss], self.now)
        self.trader.process_setups(state, [dict(first_loss, **{"LTP": 250.0})], self.now)
        self.trader.process_setups(state, [second_loss], self.now)
        self.trader.process_setups(state, [dict(second_loss, **{"LTP": 250.0})], self.now)
        self.trader.process_setups(state, [third_trade], self.now)

        self.assertEqual(len(state.closed_trades), 2)
        self.assertEqual(len(state.positions), 0)

    def test_profit_move_activates_breakeven_protection(self):
        state = self.trader.create_state()
        self.trader.process_setups(state, [self.row], self.now)
        self.trader.process_setups(state, [dict(self.row, **{"LTP": 256.0})], self.now)
        self.trader.process_setups(state, [dict(self.row, **{"LTP": 252.1})], self.now)

        self.assertEqual(len(state.positions), 0)
        self.assertEqual(state.closed_trades[0].exit_reason, "BREAKEVEN_PROTECTION_STOP")


if __name__ == "__main__":
    unittest.main()

from datetime import datetime, time
from typing import Optional

import pandas as pd

from ..indicators import add_vwap, rolling_average_volume
from ..models import Signal, SignalSide
from .base import Strategy


def _body_strength(row: pd.Series) -> float:
    candle_range = max(float(row["high"] - row["low"]), 0.01)
    body = float(row["close"] - row["open"])
    return body / candle_range


def _recent_trend_is_positive(history: pd.DataFrame, lookback: int = 20) -> bool:
    if len(history) < lookback:
        return False
    recent = history.tail(lookback)
    return float(recent["close"].iloc[-1]) > float(recent["close"].iloc[0])


class VWAPBreakoutStrategy(Strategy):
    name = "VWAP breakout"

    def generate_signal(self, symbol: str, history: pd.DataFrame, now: datetime) -> Optional[Signal]:
        if len(history) < 30 or now.time() > time(14, 45):
            return None
        data = add_vwap(history)
        last = data.iloc[-1]
        previous = data.iloc[-2]
        avg_volume = data["volume"].tail(20).mean()
        first_open = float(history.iloc[0]["open"])
        price_is_strong = last["close"] > first_open and last["close"] > last["vwap"] and last["close"] > history["high"].tail(10).iloc[:-1].max()
        volume_is_strong = last["volume"] > avg_volume * 1.25
        trend_is_strong = _recent_trend_is_positive(history, 20) and _body_strength(last) > 0.45
        if previous["close"] <= previous["vwap"] and price_is_strong and volume_is_strong and trend_is_strong:
            return Signal(now, symbol, SignalSide.BUY, self.name, float(last["close"]), 0.0035, "VWAP reclaim with trend, range breakout, and volume confirmation")
        return None


class OpeningRangeBreakoutStrategy(Strategy):
    name = "Opening range breakout"

    def generate_signal(self, symbol: str, history: pd.DataFrame, now: datetime) -> Optional[Signal]:
        if len(history) < 20 or now.time() < time(9, 30) or now.time() > time(13, 30):
            return None
        opening = history.iloc[:15]
        last = history.iloc[-1]
        previous = history.iloc[-2]
        opening_high = float(opening["high"].max())
        opening_low = float(opening["low"].min())
        opening_range_pct = (opening_high - opening_low) / float(opening.iloc[0]["open"])
        valid_opening_range = 0.007 <= opening_range_pct <= 0.018
        close_location = (last["high"] - last["close"]) / max(float(last["high"] - last["low"]), 0.01)
        strong_close = _body_strength(last) > 0.25 and close_location <= 0.55
        if previous["close"] <= opening_high and last["close"] > opening_high and valid_opening_range and strong_close:
            return Signal(now, symbol, SignalSide.BUY, self.name, float(last["close"]), 0.004, "Clean opening range breakout from a meaningful opening range")
        return None


class VolumeBreakoutStrategy(Strategy):
    name = "Volume breakout"

    def generate_signal(self, symbol: str, history: pd.DataFrame, now: datetime) -> Optional[Signal]:
        if len(history) < 35 or now.time() > time(14, 30):
            return None
        avg_volume = rolling_average_volume(history, 20).iloc[-1]
        last = history.iloc[-1]
        recent_high = history["high"].tail(30).iloc[:-1].max()
        day_vwap = add_vwap(history).iloc[-1]["vwap"]
        if last["volume"] >= avg_volume * 2.0 and last["close"] > recent_high and last["close"] > day_vwap and _body_strength(last) > 0.50:
            return Signal(now, symbol, SignalSide.BUY, self.name, float(last["close"]), 0.0035, "High-volume breakout above recent high and VWAP")
        return None


class PreviousDayHighLowBreakoutStrategy(Strategy):
    name = "Previous day high/low breakout"

    def generate_signal(self, symbol: str, history: pd.DataFrame, now: datetime) -> Optional[Signal]:
        if len(history) < 30 or now.time() > time(14, 30):
            return None
        first_price = float(history.iloc[0]["open"])
        synthetic_previous_high = first_price * 1.006
        synthetic_previous_low = first_price * 0.994
        opening_high = float(history.iloc[:15]["high"].max())
        last = history.iloc[-1]
        previous = history.iloc[-2]
        avg_volume = history["volume"].tail(20).mean()
        breakout_level = max(synthetic_previous_high, opening_high * 1.006)
        if previous["close"] <= breakout_level and last["close"] > breakout_level and last["volume"] > avg_volume * 1.4 and _body_strength(last) > 0.45:
            return Signal(now, symbol, SignalSide.BUY, self.name, float(last["close"]), 0.004, "Previous high breakout with volume and strong close")
        if previous["close"] >= synthetic_previous_low and last["close"] < synthetic_previous_low:
            return Signal(now, symbol, SignalSide.SELL, self.name, float(last["close"]), 0.0045, "Price broke synthetic previous day low; shorts are rejected in cash mode")
        return None

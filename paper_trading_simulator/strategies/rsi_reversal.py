from datetime import datetime, time
from typing import Optional

import pandas as pd

from ..indicators import add_rsi
from ..indicators import add_vwap
from ..models import Signal, SignalSide
from .base import Strategy


class RSIReversalStrategy(Strategy):
    name = "RSI reversal"

    def generate_signal(self, symbol: str, history: pd.DataFrame, now: datetime) -> Optional[Signal]:
        if len(history) < 130 or now.time() < time(11, 25) or now.time() > time(13, 30):
            return None
        data = add_vwap(add_rsi(history))
        last = data.iloc[-1]
        previous = data.iloc[-2]
        recent = data.tail(20)
        if pd.isna(last["rsi"]):
            return None
        vwap_discount = float(last["close"] / last["vwap"])
        rsi_recovering = recent["rsi"].min() < 32 and 20 <= last["rsi"] <= 45 and last["rsi"] > previous["rsi"]
        price_turning = last["close"] > previous["close"] and last["low"] > recent["low"].min()
        near_vwap_discount = 0.986 <= vwap_discount <= 0.994
        if rsi_recovering and price_turning and near_vwap_discount:
            return Signal(now, symbol, SignalSide.BUY, self.name, float(last["close"]), 0.004, "Oversold RSI bounce from a VWAP discount")
        return None

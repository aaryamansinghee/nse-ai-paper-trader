from .base import Strategy
from .breakouts import (
    OpeningRangeBreakoutStrategy,
    PreviousDayHighLowBreakoutStrategy,
    VolumeBreakoutStrategy,
    VWAPBreakoutStrategy,
)
from .rsi_reversal import RSIReversalStrategy


def build_default_strategies() -> list[Strategy]:
    return [
        VWAPBreakoutStrategy(),
        OpeningRangeBreakoutStrategy(),
        VolumeBreakoutStrategy(),
        RSIReversalStrategy(),
        PreviousDayHighLowBreakoutStrategy(),
    ]


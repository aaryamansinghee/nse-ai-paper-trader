from dataclasses import dataclass
from datetime import datetime, time

from .announcements import CorporateAnnouncement
from .models import Candle
from .sentiment import SentimentResult


@dataclass(frozen=True)
class StrategyScore:
    symbol: str
    latest_news: str
    sentiment: str
    ltp: float
    trigger_price: float
    stop_loss: float
    target: float
    signal: str
    confidence_score: int
    reason_for_trade: str
    source: str


def score_trade_setup(
    announcement: CorporateAnnouncement,
    sentiment: SentimentResult,
    candle: Candle | None,
    reward_multiple: float = 2.55,
) -> StrategyScore:
    ltp = candle.close if candle else 0.0
    if ltp <= 0:
        return StrategyScore(
            announcement.symbol,
            announcement.headline,
            sentiment.label,
            0.0,
            0.0,
            0.0,
            0.0,
            "WAIT",
            0,
            "No live or fallback quote available yet",
            announcement.source,
        )

    price_range = max((candle.high - candle.low) if candle else 0.0, ltp * 0.002)
    vwap_proxy = ((candle.high + candle.low + candle.close) / 3) if candle else ltp
    previous_day_high_proxy = candle.high if candle else ltp
    opening_range_high_proxy = max(candle.open, candle.high) if candle else ltp

    score = 0
    reasons: list[str] = []

    if sentiment.label == "positive":
        score += 25 + sentiment.score
        reasons.append("news catalyst breakout")
    elif sentiment.label == "negative":
        score -= 25
        reasons.append("negative news risk")
    elif sentiment.label == "ignore":
        score -= 40
        reasons.append("ignored routine filing")
    else:
        score += 5
        reasons.append("neutral news")

    if candle and candle.volume >= 100000:
        score += 15
        reasons.append("volume spike")
    elif candle and candle.volume > 0:
        score += 5
        reasons.append("volume available")

    if ltp >= vwap_proxy:
        score += 15
        reasons.append("VWAP trend")

    if ltp >= previous_day_high_proxy * 0.998:
        score += 12
        reasons.append("previous day high breakout zone")

    if _market_open_window(datetime.now().time()) and ltp >= opening_range_high_proxy * 0.998:
        score += 10
        reasons.append("opening range breakout zone")

    confidence = max(0, min(100, score))
    trigger = round(max(ltp + price_range * 0.10, ltp * 1.001), 2)
    stop_loss = round(trigger * 0.996, 2)
    risk = trigger - stop_loss
    target = round(trigger + risk * reward_multiple, 2)

    if sentiment.label in {"negative", "ignore"}:
        signal = "IGNORE"
    elif confidence >= 70:
        signal = "BUY WATCH"
    elif confidence >= 45:
        signal = "WAIT"
    else:
        signal = "NO TRADE"

    return StrategyScore(
        announcement.symbol,
        announcement.headline,
        sentiment.label,
        round(ltp, 2),
        trigger,
        stop_loss,
        target,
        signal,
        confidence,
        "; ".join(reasons),
        announcement.source,
    )


def _market_open_window(now: time) -> bool:
    return time(9, 15) <= now <= time(10, 15)


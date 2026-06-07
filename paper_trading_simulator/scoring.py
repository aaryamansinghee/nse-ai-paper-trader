from dataclasses import dataclass
from datetime import datetime, time

from .announcement_quality import AnnouncementQuality, classify_announcement_quality
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
    announcement_category: str
    announcement_quality_score: int
    preferred_strategy: str
    reason_for_trade: str
    source: str


def score_trade_setup(
    announcement: CorporateAnnouncement,
    sentiment: SentimentResult,
    candle: Candle | None,
    reward_multiple: float = 2.55,
) -> StrategyScore:
    quality = classify_announcement_quality(announcement.headline, announcement.details)
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
            quality.category,
            quality.quality_score,
            quality.preferred_strategy,
            "No live or fallback quote available yet",
            announcement.source,
        )

    price_range = max((candle.high - candle.low) if candle else 0.0, ltp * 0.002)
    vwap_proxy = ((candle.high + candle.low + candle.close) / 3) if candle else ltp
    previous_day_high_proxy = candle.high if candle else ltp
    opening_range_high_proxy = max(candle.open, candle.high) if candle else ltp

    score = 0
    reasons: list[str] = []
    score += quality.quality_score
    reasons.append(f"{quality.category}: {quality.reason}")

    if quality.action in {"REJECT", "IGNORE"}:
        score -= 30
        reasons.append(f"announcement action: {quality.action.lower()}")

    if sentiment.label == "positive" and quality.action == "CONSIDER":
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

    if candle and candle.volume >= 300000:
        score += 22
        reasons.append("strong volume spike")
    elif candle and candle.volume >= 100000:
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
    entry_buffer_pct = _entry_buffer_pct(confidence, sentiment.label)
    trigger = round(max(ltp + price_range * 0.18, ltp * (1 + entry_buffer_pct)), 2)
    stop_loss = round(trigger * 0.996, 2)
    risk = trigger - stop_loss
    full_target = trigger + risk * reward_multiple
    early_breakout_target = _early_exit_target(trigger, full_target, candle.high if candle else trigger)
    target = round(early_breakout_target, 2)

    if sentiment.label in {"negative", "ignore"} or quality.action in {"REJECT", "IGNORE"}:
        signal = "IGNORE"
    elif confidence >= 75 and quality.action == "CONSIDER":
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
        quality.category,
        quality.quality_score,
        quality.preferred_strategy,
        "; ".join(reasons),
        announcement.source,
    )


def _entry_buffer_pct(confidence: int, sentiment_label: str) -> float:
    if sentiment_label != "positive":
        return 0.006
    if confidence >= 85:
        return 0.008
    if confidence >= 75:
        return 0.006
    return 0.004


def _early_exit_target(trigger: float, full_target: float, day_high: float) -> float:
    if day_high > trigger * 1.02:
        return trigger + (day_high - trigger) * 0.85
    return trigger + (full_target - trigger) * 0.82


def _market_open_window(now: time) -> bool:
    return time(9, 15) <= now <= time(10, 15)

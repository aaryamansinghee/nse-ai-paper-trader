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
    catalyst_points: int
    sentiment_points: int
    liquidity_points: int
    market_structure_points: int
    risk_reward_points: int
    reason_for_trade: str
    source: str


WEIGHTS = {
    "catalyst": 35,
    "sentiment": 15,
    "liquidity": 15,
    "market_structure": 20,
    "risk_reward": 15,
}


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
            0,
            0,
            0,
            0,
            0,
            "No live or fallback quote available yet",
            announcement.source,
        )

    price_range = max((candle.high - candle.low) if candle else 0.0, ltp * 0.002)
    vwap_proxy = ((candle.high + candle.low + candle.close) / 3) if candle else ltp
    previous_day_high_proxy = max(candle.previous_close or 0, candle.high) if candle else ltp
    opening_range_high_proxy = max(candle.open, candle.high) if candle else ltp

    reasons: list[str] = []
    catalyst_points = _catalyst_points(quality, reasons)
    sentiment_points = _sentiment_points(sentiment, quality, reasons)
    liquidity_points = _liquidity_points(candle, ltp, reasons)
    market_structure_points = _market_structure_points(
        candle,
        ltp,
        vwap_proxy,
        previous_day_high_proxy,
        opening_range_high_proxy,
        reasons,
    )

    entry_buffer_pct = _entry_buffer_pct(catalyst_points + sentiment_points, sentiment.label)
    trigger = round(max(ltp + price_range * 0.18, ltp * (1 + entry_buffer_pct)), 2)
    stop_loss_pct = _stop_loss_pct(catalyst_points + market_structure_points)
    stop_loss = round(trigger * (1 - stop_loss_pct), 2)
    risk = max(trigger - stop_loss, trigger * 0.002)
    full_target = trigger + risk * reward_multiple
    early_breakout_target = _early_exit_target(trigger, full_target, candle.high if candle else trigger)
    target = round(early_breakout_target, 2)
    risk_reward_points = _risk_reward_points(trigger, stop_loss, target, ltp, reasons)

    confidence = max(
        0,
        min(
            100,
            catalyst_points
            + sentiment_points
            + liquidity_points
            + market_structure_points
            + risk_reward_points,
        ),
    )

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
            catalyst_points,
            sentiment_points,
            liquidity_points,
            market_structure_points,
            risk_reward_points,
            "; ".join(reasons),
            announcement.source,
        )


def _catalyst_points(quality: AnnouncementQuality, reasons: list[str]) -> int:
    if quality.action == "REJECT":
        reasons.append(f"catalyst rejected: {quality.reason}")
        return 0
    if quality.action == "IGNORE":
        reasons.append(f"catalyst ignored: {quality.reason}")
        return 0
    points = max(0, min(WEIGHTS["catalyst"], quality.quality_score))
    reasons.append(f"catalyst {points}/{WEIGHTS['catalyst']}: {quality.category} - {quality.reason}")
    return points


def _sentiment_points(sentiment: SentimentResult, quality: AnnouncementQuality, reasons: list[str]) -> int:
    if sentiment.label == "positive" and quality.action == "CONSIDER":
        points = min(WEIGHTS["sentiment"], 8 + max(0, sentiment.score // 4))
        reasons.append(f"sentiment {points}/{WEIGHTS['sentiment']}: {sentiment.reason}")
        return points
    if sentiment.label == "negative":
        reasons.append(f"sentiment 0/{WEIGHTS['sentiment']}: negative risk")
        return 0
    reasons.append(f"sentiment 0/{WEIGHTS['sentiment']}: {sentiment.label}")
    return 0


def _liquidity_points(candle: Candle, ltp: float, reasons: list[str]) -> int:
    points = 0
    if candle.volume >= 500000:
        points += 10
        reasons.append("liquidity: strong volume")
    elif candle.volume >= 150000:
        points += 7
        reasons.append("liquidity: acceptable volume")
    elif candle.volume >= 50000:
        points += 3
        reasons.append("liquidity: thin volume")
    else:
        reasons.append("liquidity: weak volume")

    day_range_pct = ((candle.high - candle.low) / ltp) * 100 if ltp else 0
    if 0.25 <= day_range_pct <= 4.0:
        points += 5
        reasons.append("liquidity: tradable intraday range")
    elif day_range_pct > 4.0:
        points += 1
        reasons.append("liquidity: extended range, reduced score")
    points = min(WEIGHTS["liquidity"], points)
    reasons.append(f"liquidity score {points}/{WEIGHTS['liquidity']}")
    return points


def _market_structure_points(
    candle: Candle,
    ltp: float,
    vwap_proxy: float,
    previous_day_high_proxy: float,
    opening_range_high_proxy: float,
    reasons: list[str],
) -> int:
    points = 0
    if ltp >= vwap_proxy:
        points += 8
        reasons.append("market: price above VWAP proxy")
    if candle.previous_close and ltp >= candle.previous_close * 1.001:
        points += 4
        reasons.append("market: green versus previous close")
    if ltp >= previous_day_high_proxy * 0.998:
        points += 4
        reasons.append("market: near previous-day high breakout")
    if _market_open_window(datetime.now().time()) and ltp >= opening_range_high_proxy * 0.998:
        points += 4
        reasons.append("market: opening range breakout zone")
    points = min(WEIGHTS["market_structure"], points)
    reasons.append(f"market structure score {points}/{WEIGHTS['market_structure']}")
    return points


def _risk_reward_points(trigger: float, stop_loss: float, target: float, ltp: float, reasons: list[str]) -> int:
    risk = trigger - stop_loss
    reward = target - trigger
    risk_pct = risk / trigger if trigger else 0
    reward_multiple = reward / risk if risk else 0
    points = 0
    if 0.002 <= risk_pct <= 0.005:
        points += 6
        reasons.append("risk: stop loss within 0.2%-0.5%")
    else:
        reasons.append("risk: stop loss outside ideal range")
    if reward_multiple >= 1.5:
        points += 6
        reasons.append(f"risk: reward/risk {reward_multiple:.2f}x")
    if trigger <= ltp * 1.012:
        points += 3
        reasons.append("risk: trigger not too far from LTP")
    points = min(WEIGHTS["risk_reward"], points)
    reasons.append(f"risk/reward score {points}/{WEIGHTS['risk_reward']}")
    return points


def _entry_buffer_pct(score: int, sentiment_label: str) -> float:
    if sentiment_label != "positive":
        return 0.006
    if score >= 45:
        return 0.008
    if score >= 35:
        return 0.006
    return 0.004


def _stop_loss_pct(score: int) -> float:
    if score >= 50:
        return 0.0035
    if score >= 40:
        return 0.004
    return 0.005


def _early_exit_target(trigger: float, full_target: float, day_high: float) -> float:
    if day_high > trigger * 1.02:
        return trigger + (day_high - trigger) * 0.85
    return trigger + (full_target - trigger) * 0.82


def _market_open_window(now: time) -> bool:
    return time(9, 15) <= now <= time(10, 15)

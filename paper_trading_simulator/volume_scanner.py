from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import Candle


OPENING_MOMENTUM_UNIVERSE = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "AXISBANK",
    "KOTAKBANK",
    "ITC",
    "LT",
    "BHARTIARTL",
    "TATAMOTORS",
    "MARUTI",
    "M&M",
    "BAJFINANCE",
    "HINDUNILVR",
    "HCLTECH",
    "WIPRO",
    "TECHM",
    "SUNPHARMA",
    "CIPLA",
    "DRREDDY",
    "ONGC",
    "NTPC",
    "POWERGRID",
    "COALINDIA",
    "BPCL",
    "UPL",
    "ADANIENT",
    "ADANIPORTS",
    "JIOFIN",
    "IRFC",
    "BEL",
    "HAL",
    "VEDL",
    "TATASTEEL",
    "JSWSTEEL",
    "DLF",
    "INDIGO",
    "ZOMATO",
]

VOLUME_SCANNER_UNIVERSE = OPENING_MOMENTUM_UNIVERSE

SECTOR_BY_SYMBOL = {
    "RELIANCE": "Energy",
    "ONGC": "Energy",
    "BPCL": "Energy",
    "TCS": "IT",
    "INFY": "IT",
    "HCLTECH": "IT",
    "WIPRO": "IT",
    "TECHM": "IT",
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "SBIN": "Banking",
    "AXISBANK": "Banking",
    "KOTAKBANK": "Banking",
    "BAJFINANCE": "Financials",
    "JIOFIN": "Financials",
    "IRFC": "Financials",
    "TATAMOTORS": "Auto",
    "MARUTI": "Auto",
    "M&M": "Auto",
    "BHARTIARTL": "Telecom",
    "ITC": "FMCG",
    "HINDUNILVR": "FMCG",
    "SUNPHARMA": "Pharma",
    "CIPLA": "Pharma",
    "DRREDDY": "Pharma",
    "NTPC": "Power",
    "POWERGRID": "Power",
    "COALINDIA": "Commodities",
    "UPL": "Chemicals",
    "ADANIENT": "Infrastructure",
    "ADANIPORTS": "Infrastructure",
    "LT": "Infrastructure",
    "BEL": "Defence",
    "HAL": "Defence",
    "VEDL": "Metals",
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
    "DLF": "Real Estate",
    "INDIGO": "Travel",
    "ZOMATO": "Consumer Tech",
}

EXPECTED_OPENING_VOLUME = {
    "RELIANCE": 600000,
    "TCS": 180000,
    "INFY": 450000,
    "HDFCBANK": 800000,
    "ICICIBANK": 900000,
    "SBIN": 1600000,
    "AXISBANK": 650000,
    "KOTAKBANK": 250000,
    "ITC": 850000,
    "LT": 250000,
    "BHARTIARTL": 700000,
    "TATAMOTORS": 1800000,
    "MARUTI": 90000,
    "M&M": 220000,
    "BAJFINANCE": 130000,
    "HINDUNILVR": 120000,
    "HCLTECH": 240000,
    "WIPRO": 450000,
    "TECHM": 220000,
    "SUNPHARMA": 180000,
    "CIPLA": 140000,
    "DRREDDY": 65000,
    "ONGC": 1200000,
    "NTPC": 1600000,
    "POWERGRID": 900000,
    "COALINDIA": 650000,
    "BPCL": 380000,
    "UPL": 300000,
    "ADANIENT": 350000,
    "ADANIPORTS": 350000,
    "JIOFIN": 2000000,
    "IRFC": 3500000,
    "BEL": 1800000,
    "HAL": 250000,
    "VEDL": 800000,
    "TATASTEEL": 1600000,
    "JSWSTEEL": 350000,
    "DLF": 700000,
    "INDIGO": 100000,
    "ZOMATO": 3500000,
}


@dataclass(frozen=True)
class OpeningMomentumSetup:
    symbol: str
    sector: str
    ltp: float
    day_open: float
    previous_close: float | None
    change: float | None
    change_pct: float | None
    move_from_open_pct: float
    day_high: float
    day_low: float
    volume: int
    expected_volume: int
    relative_volume: float
    traded_value_lakh: float
    volume_rank: int
    price_rank: int
    sector_rank: int
    strategy: str
    relative_volume_score: int
    price_momentum_score: int
    opening_breakout_score: int
    sector_score: int
    vwap_score: int
    day_high_distance_score: int
    liquidity_score: int
    confidence_score: int
    trigger_price: float
    stop_loss: float
    target: float
    signal: str
    ai_decision: str
    reason: str
    timestamp: datetime
    quote_source: str
    quote_status: str


VolumeSetup = OpeningMomentumSetup


def scan_volume_setups(
    quotes: dict[str, dict],
    min_ltp: float = 100,
    max_ltp: float = 1000,
    top_n: int = 12,
) -> list[OpeningMomentumSetup]:
    candidates = _candidate_rows(quotes, min_ltp, max_ltp)
    sector_scores = _sector_strength(candidates)
    candidates.sort(key=lambda item: (item["volume"], item["change_pct"] or -999), reverse=True)

    setups: list[OpeningMomentumSetup] = []
    for rank, row in enumerate(candidates[:top_n], start=1):
        row["volume_rank"] = rank
        row["sector_rank"] = sector_scores.get(row["sector"], {}).get("rank", 99)
        setups.append(_score_candidate(row, len(candidates), sector_scores))
    return sorted(setups, key=lambda item: item.confidence_score, reverse=True)


def scan_explosive_movers(
    quotes: dict[str, dict],
    min_ltp: float = 100,
    max_ltp: float = 1000,
    top_n: int = 12,
    min_change_pct: float = 5.0,
) -> list[OpeningMomentumSetup]:
    """Find OCCLLTD-style opening movers that absolute-volume ranking can miss."""
    candidates = _candidate_rows(quotes, min_ltp, max_ltp)
    explosive_rows = []
    for row in candidates:
        candle: Candle = row["candle"]
        change_pct = row["change_pct"] or 0
        traded_value_lakh = (candle.close * candle.volume) / 100000
        day_high_distance_pct = ((candle.high - candle.close) / candle.close) * 100 if candle.close else 100
        if change_pct < min_change_pct:
            continue
        if row["relative_volume"] < 0.7:
            continue
        if traded_value_lakh < _minimum_explosive_traded_value(candle.close):
            continue
        if day_high_distance_pct > 1.5:
            continue
        row["explosive_rank_score"] = _explosive_rank_score(row)
        row["explosive_boost"] = _explosive_confidence_boost(row)
        explosive_rows.append(row)

    explosive_rows.sort(key=lambda item: item["explosive_rank_score"], reverse=True)
    sector_scores = _sector_strength(candidates)
    setups: list[OpeningMomentumSetup] = []
    for rank, row in enumerate(explosive_rows[:top_n], start=1):
        row["volume_rank"] = rank
        row["sector_rank"] = sector_scores.get(row["sector"], {}).get("rank", 99)
        setups.append(_score_candidate(row, len(candidates), sector_scores))
    return sorted(setups, key=lambda item: item.confidence_score, reverse=True)


def sector_leaders_from_quotes(quotes: dict[str, dict], min_ltp: float = 100, max_ltp: float = 1000) -> list[dict]:
    rows = _candidate_rows(quotes, min_ltp, max_ltp)
    leaders = _sector_strength(rows)
    output = []
    for sector, data in sorted(leaders.items(), key=lambda item: item[1]["score"], reverse=True):
        output.append(
            {
                "sector": sector,
                "sector score": data["score"],
                "positive stocks": data["positive_count"],
                "average change %": round(data["average_change_pct"], 2),
                "average relative volume": round(data["average_relative_volume"], 2),
                "sector rank": data["rank"],
            }
        )
    return output


def _candidate_rows(quotes: dict[str, dict], min_ltp: float, max_ltp: float) -> list[dict]:
    rows: list[dict] = []
    for symbol, quote in quotes.items():
        candle = quote.get("candle")
        source = quote.get("source", "")
        status = quote.get("status", "")
        symbol = symbol.upper()
        if not candle or candle.close <= 0:
            continue
        if status != "Updating":
            continue
        if not (min_ltp <= candle.close <= max_ltp):
            continue
        if candle.volume < _minimum_liquidity(symbol, candle.close):
            continue
        previous_close = candle.previous_close
        change = round(candle.close - previous_close, 2) if previous_close else None
        change_pct = round((change / previous_close) * 100, 2) if previous_close and change is not None else None
        move_from_open_pct = round(((candle.close - candle.open) / candle.open) * 100, 2) if candle.open else 0
        expected_volume = _expected_opening_volume(symbol, candle.close)
        relative_volume = round(candle.volume / max(expected_volume, 1), 2)
        rows.append(
            {
                "symbol": symbol,
                "sector": SECTOR_BY_SYMBOL.get(symbol, "Other"),
                "candle": candle,
                "source": source,
                "status": status,
                "previous_close": previous_close,
                "change": change,
                "change_pct": change_pct,
                "move_from_open_pct": move_from_open_pct,
                "volume": int(candle.volume),
                "expected_volume": expected_volume,
                "relative_volume": relative_volume,
            }
        )
    rows.sort(key=lambda item: item["change_pct"] if item["change_pct"] is not None else -999, reverse=True)
    for index, row in enumerate(rows, start=1):
        row["price_rank"] = index
    return rows


def _score_candidate(row: dict, total_candidates: int, sector_scores: dict[str, dict]) -> OpeningMomentumSetup:
    candle: Candle = row["candle"]
    symbol = row["symbol"]
    sector = row["sector"]
    vwap_proxy = (candle.open + candle.high + candle.low + candle.close) / 4
    day_high_distance_pct = ((candle.high - candle.close) / candle.close) * 100 if candle.close else 100

    relative_volume_score = _relative_volume_score(row["relative_volume"])
    price_momentum_score = _price_momentum_score(row["change_pct"], candle)
    opening_breakout_score = _opening_breakout_score(candle)
    sector_score = _sector_score(sector_scores.get(sector, {}))
    vwap_score = _vwap_score(candle.close, vwap_proxy)
    day_high_distance_score = _day_high_distance_score(day_high_distance_pct)
    liquidity_score = _liquidity_quality_score(candle, row["volume_rank"], total_candidates)
    explosive_boost = row.get("explosive_boost", 0)
    confidence = min(
        100,
        relative_volume_score
        + price_momentum_score
        + opening_breakout_score
        + sector_score
        + vwap_score
        + day_high_distance_score
        + liquidity_score
        + explosive_boost,
    )

    strategy = _preferred_strategy(relative_volume_score, opening_breakout_score, vwap_score, explosive_boost)
    trigger = _entry_trigger(candle, confidence, row)
    stop_loss = round(trigger * (1 - _stop_loss_pct(row, confidence)), 2)
    target = _target_price(trigger, row, confidence)
    signal, ai_decision = _signal(confidence, candle.close, trigger, row)

    reason = (
        f"{strategy}; RVOL {row['relative_volume']:.2f}x; "
        f"relative volume {relative_volume_score}/22, price momentum {price_momentum_score}/18, "
        f"opening breakout {opening_breakout_score}/16, sector {sector_score}/12, "
        f"VWAP strength {vwap_score}/12, day-high distance {day_high_distance_score}/10, "
        f"liquidity {liquidity_score}/10, explosive-mover boost {explosive_boost}. "
        f"move from open {row['move_from_open_pct']:.2f}%; "
        f"Stop is {round((_stop_loss_pct(row, confidence) * 100), 2)}%; "
        f"momentum target is {round((_target_pct(row, confidence) * 100), 1)}%. "
        "Enter only after trigger confirmation."
    )
    return OpeningMomentumSetup(
        symbol=symbol,
        sector=sector,
        ltp=round(candle.close, 2),
        day_open=round(candle.open, 2),
        previous_close=row["previous_close"],
        change=row["change"],
        change_pct=row["change_pct"],
        move_from_open_pct=row["move_from_open_pct"],
        day_high=round(candle.high, 2),
        day_low=round(candle.low, 2),
        volume=int(candle.volume),
        expected_volume=row["expected_volume"],
        relative_volume=row["relative_volume"],
        traded_value_lakh=round((candle.close * candle.volume) / 100000, 2),
        volume_rank=row["volume_rank"],
        price_rank=row["price_rank"],
        sector_rank=row["sector_rank"],
        strategy=strategy,
        relative_volume_score=relative_volume_score,
        price_momentum_score=price_momentum_score,
        opening_breakout_score=opening_breakout_score,
        sector_score=sector_score,
        vwap_score=vwap_score,
        day_high_distance_score=day_high_distance_score,
        liquidity_score=liquidity_score,
        confidence_score=confidence,
        trigger_price=trigger,
        stop_loss=stop_loss,
        target=target,
        signal=signal,
        ai_decision=ai_decision,
        reason=reason,
        timestamp=candle.timestamp,
        quote_source=row["source"],
        quote_status=row["status"],
    )


def _sector_strength(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["sector"], []).append(row)
    scores: dict[str, dict] = {}
    for sector, sector_rows in grouped.items():
        changes = [row["change_pct"] or 0 for row in sector_rows]
        rvols = [row["relative_volume"] for row in sector_rows]
        positive_count = sum(1 for value in changes if value > 0)
        average_change_pct = sum(changes) / len(changes)
        average_relative_volume = sum(rvols) / len(rvols)
        score = round(positive_count * 8 + max(0, average_change_pct) * 5 + min(average_relative_volume, 4) * 6, 2)
        scores[sector] = {
            "score": score,
            "positive_count": positive_count,
            "average_change_pct": average_change_pct,
            "average_relative_volume": average_relative_volume,
        }
    for rank, sector in enumerate(sorted(scores, key=lambda item: scores[item]["score"], reverse=True), start=1):
        scores[sector]["rank"] = rank
    return scores


def _minimum_liquidity(symbol: str, ltp: float) -> int:
    if ltp < 150:
        return 50000
    if ltp < 500:
        return 75000
    return 50000


def _minimum_explosive_traded_value(ltp: float) -> float:
    if ltp < 150:
        return 60
    if ltp < 500:
        return 80
    return 100


def _expected_opening_volume(symbol: str, ltp: float) -> int:
    if symbol in EXPECTED_OPENING_VOLUME:
        return EXPECTED_OPENING_VOLUME[symbol]
    if ltp < 150:
        return 100000
    if ltp < 500:
        return 125000
    return 175000


def _explosive_rank_score(row: dict) -> float:
    candle: Candle = row["candle"]
    change_pct = row["change_pct"] or 0
    traded_value_lakh = (candle.close * candle.volume) / 100000
    day_high_distance_pct = ((candle.high - candle.close) / candle.close) * 100 if candle.close else 100
    return (
        min(change_pct, 20) * 4
        + min(row["relative_volume"], 5) * 12
        + min(traded_value_lakh / 50, 20)
        + max(0, 20 - day_high_distance_pct * 5)
    )


def _explosive_confidence_boost(row: dict) -> int:
    change_pct = row["change_pct"] or 0
    if change_pct >= 10 and row["relative_volume"] >= 1.2:
        return 18
    if change_pct >= 5:
        return 12
    if change_pct >= 3:
        return 8
    if change_pct >= 2:
        return 6
    return 0


def _relative_volume_score(relative_volume: float) -> int:
    if relative_volume >= 3:
        return 22
    if relative_volume >= 2:
        return 18
    if relative_volume >= 1.5:
        return 13
    if relative_volume >= 1:
        return 8
    return 0


def _price_momentum_score(change_pct: float | None, candle: Candle) -> int:
    points = 0
    if change_pct is not None:
        if 2 <= change_pct <= 12:
            points += 12
        elif 1 <= change_pct < 2:
            points += 10
        elif 0.35 <= change_pct < 1:
            points += 8
        elif change_pct > 12:
            points += 5
    if candle.close >= candle.open:
        points += 6
    return min(18, points)


def _opening_breakout_score(candle: Candle) -> int:
    if candle.close <= 0:
        return 0
    range_pct = ((candle.high - candle.low) / candle.close) * 100
    if candle.close >= candle.high * 0.998 and 0.3 <= range_pct <= 8:
        return 16
    if candle.close >= candle.high * 0.992:
        return 10
    return 0


def _sector_score(sector_data: dict) -> int:
    rank = sector_data.get("rank", 99)
    if rank == 1:
        return 12
    if rank == 2:
        return 9
    if rank == 3:
        return 6
    return 2


def _vwap_score(ltp: float, vwap_proxy: float) -> int:
    if ltp >= vwap_proxy * 1.004:
        return 12
    if ltp >= vwap_proxy:
        return 8
    return 0


def _day_high_distance_score(distance_pct: float) -> int:
    if distance_pct <= 0.15:
        return 10
    if distance_pct <= 0.4:
        return 7
    if distance_pct <= 0.8:
        return 3
    return 0


def _liquidity_quality_score(candle: Candle, volume_rank: int, total_candidates: int) -> int:
    points = 0
    traded_value_lakh = (candle.close * candle.volume) / 100000
    if traded_value_lakh >= 1000:
        points += 5
    elif traded_value_lakh >= 300:
        points += 3
    if volume_rank <= max(3, total_candidates * 0.2):
        points += 5
    elif volume_rank <= max(6, total_candidates * 0.4):
        points += 3
    return min(10, points)


def _preferred_strategy(relative_volume_score: int, opening_breakout_score: int, vwap_score: int, explosive_boost: int = 0) -> str:
    if explosive_boost >= 12:
        return "Strategy C: Relative Volume Momentum (Explosive Mover)"
    if opening_breakout_score >= 16:
        return "Strategy A: Opening Range Breakout"
    if vwap_score >= 12:
        return "Strategy B: VWAP Reclaim"
    if relative_volume_score >= 18:
        return "Strategy C: Relative Volume Momentum"
    return "WAIT: Needs stronger opening confirmation"


def _entry_trigger(candle: Candle, confidence: int, row: dict) -> float:
    day_high_distance_pct = ((candle.high - candle.close) / candle.close) * 100 if candle.close else 100
    if confidence >= 75 and day_high_distance_pct <= 0.15 and row["move_from_open_pct"] <= 4:
        return round(candle.close, 2)
    buffer_pct = 0.001 if confidence >= 82 else 0.002
    breakout_level = max(candle.high * 1.0005, candle.close * (1 + buffer_pct))
    return round(min(breakout_level, candle.close * 1.004), 2)


def _target_price(trigger: float, row: dict, confidence: int) -> float:
    return round(trigger * (1 + _target_pct(row, confidence)), 2)


def _stop_loss_pct(row: dict, confidence: int) -> float:
    explosive_boost = row.get("explosive_boost", 0)
    if explosive_boost >= 18:
        return 0.0025
    if explosive_boost >= 12 and confidence >= 75:
        return 0.0025
    return 0.005


def _target_pct(row: dict, confidence: int) -> float:
    explosive_boost = row.get("explosive_boost", 0)
    change_pct = row["change_pct"] or 0
    relative_volume = row["relative_volume"]
    if explosive_boost >= 18:
        return 0.10
    if explosive_boost >= 12 or (change_pct >= 5 and relative_volume >= 1.5):
        return 0.08
    if explosive_boost >= 6 or (change_pct >= 2 and relative_volume >= 1.2):
        return 0.05
    if confidence >= 78:
        return 0.035
    return 0.025


def _signal(confidence: int, ltp: float, trigger: float, row: dict) -> tuple[str, str]:
    if row["move_from_open_pct"] > 4:
        return "BUY WATCH", "WAIT_CHASE_TOO_LATE"
    if confidence >= 75 and ltp >= trigger:
        return "BUY WATCH", "TRADE_READY"
    if confidence >= 72:
        return "BUY WATCH", "WAIT_FOR_TRIGGER"
    if confidence >= 58:
        return "WAIT", "WAIT"
    return "NO TRADE", "REJECT"

from dataclasses import dataclass


@dataclass(frozen=True)
class SentimentResult:
    label: str
    score: int
    reason: str


POSITIVE_KEYWORDS = {
    "order": 12,
    "deal": 18,
    "contract": 18,
    "agreement": 14,
    "partnership": 12,
    "approval": 12,
    "acquisition": 10,
    "expansion": 12,
    "commissioning": 12,
    "launch": 10,
    "buyback": 15,
    "bonus": 12,
    "dividend": 8,
    "growth": 10,
    "wins": 18,
    "won": 18,
}

NEGATIVE_KEYWORDS = {
    "resignation": -14,
    "default": -25,
    "fraud": -30,
    "penalty": -18,
    "fine": -15,
    "raid": -25,
    "downgrade": -18,
    "loss": -10,
    "shutdown": -18,
    "delay": -10,
    "litigation": -14,
}

IGNORE_KEYWORDS = {
    "certificate",
    "shareholding pattern",
    "investor grievance",
    "newspaper publication",
    "compliance certificate",
    "trading window",
    "secretarial compliance",
    "regulation 74",
}


def classify_sentiment(text: str) -> SentimentResult:
    lowered = text.lower()
    for keyword in IGNORE_KEYWORDS:
        if keyword in lowered:
            return SentimentResult("ignore", 0, f"Routine filing: {keyword}")

    score = 0
    hits: list[str] = []
    for keyword, value in POSITIVE_KEYWORDS.items():
        if keyword in lowered:
            score += value
            hits.append(keyword)
    for keyword, value in NEGATIVE_KEYWORDS.items():
        if keyword in lowered:
            score += value
            hits.append(keyword)

    if score >= 12:
        return SentimentResult("positive", min(score, 40), "Positive catalyst words: " + ", ".join(hits[:4]))
    if score <= -10:
        return SentimentResult("negative", max(score, -40), "Negative risk words: " + ", ".join(hits[:4]))
    return SentimentResult("neutral", 0, "No strong catalyst words found")


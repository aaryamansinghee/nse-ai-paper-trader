from dataclasses import dataclass


@dataclass(frozen=True)
class AnnouncementQuality:
    category: str
    quality_score: int
    action: str
    preferred_strategy: str
    reason: str


HIGH_QUALITY_CATEGORIES = [
    (
        "order/deal win",
        ["order win", "wins order", "bagged", "contract", "deal", "agreement", "letter of award", "loa"],
        34,
        "news catalyst breakout",
    ),
    (
        "regulatory approval",
        ["approval", "approved", "license", "clearance", "authorisation", "authorization"],
        28,
        "VWAP reclaim",
    ),
    (
        "business expansion",
        ["commissioning", "capacity expansion", "expansion", "commercial production", "launch"],
        24,
        "volume spike continuation",
    ),
    (
        "fund raise/buyback/bonus",
        ["buyback", "bonus", "fund raising", "preferential issue", "qip", "rights issue"],
        20,
        "opening range breakout",
    ),
    (
        "strong financial update",
        ["results", "profit", "revenue", "ebitda", "margin", "sales growth", "turnover"],
        18,
        "previous day high breakout",
    ),
]

LOW_QUALITY_CATEGORIES = [
    (
        "routine compliance",
        [
            "certificate",
            "shareholding pattern",
            "investor grievance",
            "newspaper publication",
            "compliance certificate",
            "trading window",
            "secretarial compliance",
            "regulation 74",
            "regulation 30",
            "annual report",
            "scrutinizer",
            "voting results",
        ],
        -35,
    ),
    (
        "investor meet/transcript",
        ["investor meet", "analyst", "conference call", "transcript", "presentation"],
        -12,
    ),
    (
        "clarification/no catalyst",
        ["clarification", "intimation", "updates", "disclosure"],
        -8,
    ),
]

RISK_CATEGORIES = [
    (
        "governance/legal risk",
        ["resignation", "default", "fraud", "penalty", "fine", "raid", "litigation", "insolvency", "show cause"],
        -45,
    )
]


def classify_announcement_quality(headline: str, details: str = "") -> AnnouncementQuality:
    text = f"{headline} {details}".lower()

    for category, keywords, score in RISK_CATEGORIES:
        hit = _first_hit(text, keywords)
        if hit:
            return AnnouncementQuality(category, score, "REJECT", "no trade", f"Risk keyword found: {hit}")

    for category, keywords, score in LOW_QUALITY_CATEGORIES:
        hit = _first_hit(text, keywords)
        if hit:
            return AnnouncementQuality(category, score, "IGNORE", "no trade", f"Low-quality announcement: {hit}")

    for category, keywords, score, strategy in HIGH_QUALITY_CATEGORIES:
        hit = _first_hit(text, keywords)
        if hit:
            return AnnouncementQuality(category, score, "CONSIDER", strategy, f"Actionable catalyst: {hit}")

    return AnnouncementQuality("unclear catalyst", 0, "WAIT", "VWAP confirmation", "No strong actionable announcement pattern found")


def _first_hit(text: str, keywords: list[str]) -> str | None:
    for keyword in keywords:
        if keyword in text:
            return keyword
    return None

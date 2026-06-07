from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Sequence

import requests


@dataclass(frozen=True)
class CorporateAnnouncement:
    symbol: str
    company: str
    headline: str
    details: str
    published_at: datetime
    source: str
    link: str = ""


class NSECorporateAnnouncementsScanner:
    """Fetches recent NSE corporate announcements with a mock fallback for demos."""

    base_url = "https://www.nseindia.com"
    announcements_url = "https://www.nseindia.com/api/corporate-announcements"

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-IN,en;q=0.9",
                "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            }
        )

    def fetch_recent(self, days: int = 3, limit: int = 25) -> list[CorporateAnnouncement]:
        today = date.today()
        from_day = today - timedelta(days=days)
        try:
            self._warm_session()
            response = self.session.get(
                self.announcements_url,
                params={
                    "index": "equities",
                    "from_date": from_day.strftime("%d-%m-%Y"),
                    "to_date": today.strftime("%d-%m-%Y"),
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            rows = response.json()
            if isinstance(rows, dict):
                rows = rows.get("data", [])
            announcements = [self._parse_row(row) for row in rows[:limit]]
            return [item for item in announcements if item is not None]
        except Exception:
            return mock_announcements(limit=limit)

    def _warm_session(self) -> None:
        if self.session.cookies:
            return
        response = self.session.get(self.base_url, timeout=self.timeout_seconds)
        response.raise_for_status()

    @staticmethod
    def _parse_row(row: dict) -> CorporateAnnouncement | None:
        symbol = str(row.get("symbol") or row.get("symb") or "").strip().upper()
        if not symbol:
            return None
        company = str(row.get("sm_name") or row.get("companyName") or symbol).strip()
        headline = str(row.get("desc") or row.get("subject") or row.get("headline") or "Corporate announcement").strip()
        details = str(row.get("details") or row.get("attchmntText") or headline).strip()
        raw_date = str(row.get("an_dt") or row.get("dt") or row.get("sort_date") or "").strip()
        published_at = _parse_datetime(raw_date)
        link = str(row.get("attchmntFile") or row.get("link") or "").strip()
        return CorporateAnnouncement(symbol, company, headline, details, published_at, "NSE Corporate Announcements", link)


def _parse_datetime(raw: str) -> datetime:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return datetime.now()


def mock_announcements(limit: int = 25) -> list[CorporateAnnouncement]:
    now = datetime.now().replace(second=0, microsecond=0)
    items = [
        CorporateAnnouncement(
            "INFY",
            "Infosys Limited",
            "Large digital transformation deal win announced",
            "Company announced a strategic multi-year technology transformation agreement.",
            now,
            "Mock NSE announcement fallback",
        ),
        CorporateAnnouncement(
            "RELIANCE",
            "Reliance Industries Limited",
            "Update on commissioning and business expansion",
            "Company shared a business update related to expansion and operational progress.",
            now - timedelta(minutes=20),
            "Mock NSE announcement fallback",
        ),
        CorporateAnnouncement(
            "TCS",
            "Tata Consultancy Services Limited",
            "Press release on new partnership",
            "Company announced a new partnership and service expansion.",
            now - timedelta(minutes=35),
            "Mock NSE announcement fallback",
        ),
        CorporateAnnouncement(
            "HDFCBANK",
            "HDFC Bank Limited",
            "Routine disclosure under SEBI listing regulations",
            "Routine compliance filing with no direct trading catalyst.",
            now - timedelta(minutes=50),
            "Mock NSE announcement fallback",
        ),
        CorporateAnnouncement(
            "ICICIBANK",
            "ICICI Bank Limited",
            "Clarification to exchange",
            "Company issued a neutral clarification to the exchange.",
            now - timedelta(minutes=65),
            "Mock NSE announcement fallback",
        ),
    ]
    return items[:limit]


def symbols_from_announcements(announcements: Sequence[CorporateAnnouncement], max_symbols: int = 12) -> list[str]:
    symbols: list[str] = []
    for item in announcements:
        if item.symbol and item.symbol not in symbols:
            symbols.append(item.symbol)
    return symbols[:max_symbols]


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


@dataclass(frozen=True)
class AnnouncementFetchResult:
    announcements: list[CorporateAnnouncement]
    ok: bool
    message: str
    fetched_at: datetime
    source_url: str


class NSECorporateAnnouncementsScanner:
    """Fetches recent NSE corporate announcements from NSE."""

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
        return self.fetch_recent_with_status(days, limit).announcements

    def fetch_recent_with_status(self, days: int = 3, limit: int = 25) -> AnnouncementFetchResult:
        today = date.today()
        from_day = today - timedelta(days=days)
        fetched_at = datetime.now().replace(microsecond=0)
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
            announcements = [self._parse_row(row) for row in rows]
            clean_announcements = [item for item in announcements if item is not None]
            clean_announcements.sort(key=lambda item: item.published_at, reverse=True)
            shown_announcements = clean_announcements[:limit]
            if shown_announcements:
                message = f"Connected to NSE. Fetched {len(shown_announcements)} announcement rows."
            else:
                message = "Connected to NSE, but no announcement rows were returned for the selected window."
            return AnnouncementFetchResult(shown_announcements, True, message, fetched_at, self.announcements_url)
        except Exception as exc:
            return AnnouncementFetchResult(
                [],
                False,
                f"NSE announcement fetch failed: {type(exc).__name__}: {exc}",
                fetched_at,
                self.announcements_url,
            )

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

def symbols_from_announcements(announcements: Sequence[CorporateAnnouncement], max_symbols: int = 12) -> list[str]:
    symbols: list[str] = []
    for item in announcements:
        if item.symbol and item.symbol not in symbols:
            symbols.append(item.symbol)
    return symbols[:max_symbols]

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import csv
import io
import os
import re
from typing import Protocol, Sequence
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

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
class ProviderStatus:
    provider: str
    ok: bool
    message: str
    fetched_at: datetime
    rows: int = 0
    source_url: str = ""


@dataclass(frozen=True)
class AnnouncementFetchResult:
    announcements: list[CorporateAnnouncement]
    ok: bool
    message: str
    fetched_at: datetime
    source_url: str
    source_used: str
    last_successful_fetch: datetime | None = None
    provider_statuses: list[ProviderStatus] = field(default_factory=list)


class AnnouncementProvider(Protocol):
    name: str

    def fetch(self, days: int = 3, limit: int = 25) -> AnnouncementFetchResult:
        ...


class NSEAnnouncementProvider:
    name = "NSE Provider"
    base_url = "https://www.nseindia.com"
    announcements_url = "https://www.nseindia.com/api/corporate-announcements"

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-IN,en;q=0.9",
                "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            }
        )

    def fetch(self, days: int = 3, limit: int = 25) -> AnnouncementFetchResult:
        today = date.today()
        from_day = today - timedelta(days=days)
        fetched_at = _now()
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
            announcements = [_parse_nse_row(row) for row in rows]
            clean = _clean_and_limit(announcements, limit)
            return _result(self.name, clean, True, f"NSE fetched {len(clean)} announcement rows.", fetched_at, self.announcements_url)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "HTTP"
            message = f"NSE provider failed with HTTP {status_code}. Automatic fallback will be used."
            return _result(self.name, [], False, message, fetched_at, self.announcements_url)
        except Exception as exc:
            message = f"NSE provider failed: {type(exc).__name__}: {exc}. Automatic fallback will be used."
            return _result(self.name, [], False, message, fetched_at, self.announcements_url)

    def _warm_session(self) -> None:
        if self.session.cookies:
            return
        response = self.session.get(self.base_url, timeout=self.timeout_seconds)
        response.raise_for_status()


class BrokerAnnouncementProvider:
    name = "Broker Provider"

    def __init__(self, csv_path_env: str = "BROKER_ANNOUNCEMENTS_CSV"):
        self.csv_path_env = csv_path_env

    def fetch(self, days: int = 3, limit: int = 25) -> AnnouncementFetchResult:
        fetched_at = _now()
        path = os.environ.get(self.csv_path_env, "").strip()
        if not path:
            return _result(self.name, [], False, "Broker provider not configured.", fetched_at, self.csv_path_env)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                announcements = parse_announcement_csv(handle.read(), source=self.name)
            clean = _clean_and_limit(_within_days(announcements, days), limit)
            return _result(self.name, clean, bool(clean), f"Broker provider loaded {len(clean)} rows.", fetched_at, path)
        except Exception as exc:
            return _result(self.name, [], False, f"Broker provider failed: {type(exc).__name__}: {exc}", fetched_at, path)


class ManualUploadAnnouncementProvider:
    name = "Manual Upload Provider"

    def __init__(self, csv_text: object | None):
        self.csv_texts = _normalize_csv_inputs(csv_text)

    def fetch(self, days: int = 3, limit: int = 25) -> AnnouncementFetchResult:
        fetched_at = _now()
        try:
            if not any(text.strip() for text in self.csv_texts):
                return _result(self.name, [], False, "No manual announcement CSV uploaded.", fetched_at, "manual upload")
            announcements: list[CorporateAnnouncement] = []
            for csv_text in self.csv_texts:
                announcements.extend(parse_announcement_csv(csv_text, source=self.name))
            clean = _clean_and_limit(_dedupe_announcements(_within_days(announcements, days)), limit)
            return _result(
                self.name,
                clean,
                bool(clean),
                f"Manual upload loaded {len(clean)} rows from {len(self.csv_texts)} CSV file(s).",
                fetched_at,
                "manual upload",
            )
        except Exception as exc:
            return _result(self.name, [], False, f"Manual upload failed: {type(exc).__name__}: {exc}", fetched_at, "manual upload")


class RSSNewsAnnouncementProvider:
    name = "RSS/News Provider"

    def __init__(self, urls: Sequence[str] | None = None, timeout_seconds: float = 10.0):
        self.urls = [url.strip() for url in (urls or []) if url.strip()]
        self.timeout_seconds = timeout_seconds

    def fetch(self, days: int = 3, limit: int = 25) -> AnnouncementFetchResult:
        fetched_at = _now()
        if not self.urls:
            return _result(self.name, [], False, "No RSS/news URLs configured.", fetched_at, "")
        announcements: list[CorporateAnnouncement] = []
        errors: list[str] = []
        for url in self.urls:
            try:
                response = requests.get(url, timeout=self.timeout_seconds, headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
                announcements.extend(_parse_rss(response.text, url))
            except Exception as exc:
                errors.append(f"{_domain(url)}: {type(exc).__name__}")
        clean = _clean_and_limit(_within_days(announcements, days), limit)
        if clean:
            return _result(self.name, clean, True, f"RSS/news provider loaded {len(clean)} rows.", fetched_at, ", ".join(self.urls))
        message = "RSS/news provider returned no usable symbol-linked announcements."
        if errors:
            message += " Errors: " + "; ".join(errors[:3])
        return _result(self.name, [], False, message, fetched_at, ", ".join(self.urls))


class MockAnnouncementProvider:
    name = "Mock Announcement Provider"

    def fetch(self, days: int = 3, limit: int = 25) -> AnnouncementFetchResult:
        fetched_at = _now()
        announcements = [
            CorporateAnnouncement("ABC", "ABC Limited", "ABC wins large order contract", "Large order win from a reputed customer", fetched_at, self.name),
            CorporateAnnouncement("XYZ", "XYZ Limited", "XYZ receives regulatory approval", "Approval for commercial launch received", fetched_at, self.name),
            CorporateAnnouncement("PQR", "PQR Limited", "PQR shareholding pattern for the quarter", "Routine compliance disclosure", fetched_at, self.name),
        ]
        clean = announcements[:limit]
        return _result(self.name, clean, True, f"Mock mode loaded {len(clean)} test announcements.", fetched_at, "mock")


class FallbackAnnouncementProvider:
    name = "Auto Fallback Provider"

    def __init__(self, providers: Sequence[AnnouncementProvider]):
        self.providers = list(providers)

    def fetch(self, days: int = 3, limit: int = 25) -> AnnouncementFetchResult:
        statuses: list[ProviderStatus] = []
        failures: list[str] = []
        fetched_at = _now()
        for provider in self.providers:
            result = provider.fetch(days=days, limit=limit)
            statuses.extend(result.provider_statuses or [_status_from_result(result)])
            if result.ok and result.announcements:
                return AnnouncementFetchResult(
                    result.announcements,
                    True,
                    f"Source used: {result.source_used}. " + result.message,
                    fetched_at,
                    result.source_url,
                    result.source_used,
                    result.last_successful_fetch or result.fetched_at,
                    statuses,
                )
            failures.append(f"{result.source_used}: {result.message}")
        return AnnouncementFetchResult(
            [],
            False,
            "All announcement providers failed or returned no rows. " + " | ".join(failures[:4]),
            fetched_at,
            "",
            "None",
            None,
            statuses,
        )


class NSECorporateAnnouncementsScanner:
    """Compatibility wrapper around the new provider architecture."""

    def __init__(self, timeout_seconds: float = 10.0, provider: AnnouncementProvider | None = None):
        self.provider = provider or NSEAnnouncementProvider(timeout_seconds=timeout_seconds)

    def fetch_recent(self, days: int = 3, limit: int = 25) -> list[CorporateAnnouncement]:
        return self.fetch_recent_with_status(days, limit).announcements

    def fetch_recent_with_status(self, days: int = 3, limit: int = 25) -> AnnouncementFetchResult:
        return self.provider.fetch(days=days, limit=limit)


def build_announcement_provider(
    mode: str = "auto",
    manual_csv_text: str | Sequence[str] | None = None,
    rss_urls: Sequence[str] | None = None,
    enable_mock: bool = False,
) -> AnnouncementProvider:
    mode = mode.lower().strip()
    if enable_mock or mode == "mock":
        return MockAnnouncementProvider()
    if mode == "nse":
        return NSEAnnouncementProvider()
    if mode == "broker":
        return BrokerAnnouncementProvider()
    if mode == "manual":
        return ManualUploadAnnouncementProvider(manual_csv_text)
    if mode == "rss":
        return RSSNewsAnnouncementProvider(rss_urls)
    providers: list[AnnouncementProvider] = [NSEAnnouncementProvider()]
    if manual_csv_text:
        providers.append(ManualUploadAnnouncementProvider(manual_csv_text))
    providers.append(BrokerAnnouncementProvider())
    if rss_urls:
        providers.append(RSSNewsAnnouncementProvider(rss_urls))
    return FallbackAnnouncementProvider(providers)


def parse_announcement_csv(csv_text: str, source: str = "Manual Upload Provider") -> list[CorporateAnnouncement]:
    csv_text = _to_text(csv_text)
    reader = csv.DictReader(io.StringIO(csv_text))
    announcements: list[CorporateAnnouncement] = []
    for row in reader:
        normalized = {str(key).strip().lower(): value for key, value in row.items() if key is not None}
        symbol = _first_value(normalized, "symbol", "symb", "stock", "ticker", "security")
        company = _first_value(normalized, "company", "company name", "company_name", "sm_name", "name") or symbol
        headline = _first_value(normalized, "headline", "subject", "desc", "announcement", "title", "details")
        details = _first_value(normalized, "details", "attchmnttext", "description", "summary") or headline
        published_raw = _first_value(normalized, "published_at", "time", "date", "broadcast date/time", "broadcast_datetime", "an_dt", "dt")
        link = _first_value(normalized, "link", "url", "attachment", "attchmntfile")
        if not symbol or not headline:
            continue
        announcements.append(
            CorporateAnnouncement(
                symbol=symbol.strip().upper(),
                company=(company or symbol).strip(),
                headline=headline.strip(),
                details=(details or headline).strip(),
                published_at=_parse_datetime(published_raw or ""),
                source=source,
                link=(link or "").strip(),
            )
        )
    return announcements


def symbols_from_announcements(announcements: Sequence[CorporateAnnouncement], max_symbols: int = 12) -> list[str]:
    symbols: list[str] = []
    for item in announcements:
        if item.symbol and item.symbol not in symbols:
            symbols.append(item.symbol)
    return symbols[:max_symbols]


def _normalize_csv_inputs(csv_input: object | None) -> tuple[str, ...]:
    if csv_input is None:
        return ()
    if isinstance(csv_input, (str, bytes, bytearray)):
        return (_to_text(csv_input),)
    if hasattr(csv_input, "getvalue"):
        return (_to_text(csv_input),)
    try:
        return tuple(_to_text(item) for item in csv_input if _to_text(item).strip())
    except TypeError:
        return (_to_text(csv_input),)


def _to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8-sig", errors="ignore")
    if isinstance(value, bytearray):
        return bytes(value).decode("utf-8-sig", errors="ignore")
    if hasattr(value, "getvalue"):
        return _to_text(value.getvalue())
    return str(value)


def _result(
    provider: str,
    announcements: list[CorporateAnnouncement],
    ok: bool,
    message: str,
    fetched_at: datetime,
    source_url: str,
) -> AnnouncementFetchResult:
    status = ProviderStatus(provider, ok, message, fetched_at, len(announcements), source_url)
    return AnnouncementFetchResult(
        announcements,
        ok,
        message,
        fetched_at,
        source_url,
        provider,
        fetched_at if ok else None,
        [status],
    )


def _status_from_result(result: AnnouncementFetchResult) -> ProviderStatus:
    return ProviderStatus(result.source_used, result.ok, result.message, result.fetched_at, len(result.announcements), result.source_url)


def _parse_nse_row(row: dict) -> CorporateAnnouncement | None:
    symbol = str(row.get("symbol") or row.get("symb") or "").strip().upper()
    if not symbol:
        return None
    company = str(row.get("sm_name") or row.get("companyName") or symbol).strip()
    headline = str(row.get("desc") or row.get("subject") or row.get("headline") or "Corporate announcement").strip()
    details = str(row.get("details") or row.get("attchmntText") or headline).strip()
    raw_date = str(row.get("an_dt") or row.get("dt") or row.get("sort_date") or "").strip()
    link = str(row.get("attchmntFile") or row.get("link") or "").strip()
    return CorporateAnnouncement(symbol, company, headline, details, _parse_datetime(raw_date), "NSE Provider", link)


def _parse_rss(xml_text: str, url: str) -> list[CorporateAnnouncement]:
    root = ET.fromstring(xml_text)
    items = root.findall(".//item")
    announcements: list[CorporateAnnouncement] = []
    for item in items:
        title = _xml_text(item, "title")
        description = _xml_text(item, "description")
        link = _xml_text(item, "link")
        published = _xml_text(item, "pubDate")
        symbol = _extract_symbol(f"{title} {description}")
        if not symbol:
            continue
        announcements.append(
            CorporateAnnouncement(symbol, symbol, title or "News update", description or title, _parse_datetime(published), f"RSS/News Provider - {_domain(url)}", link)
        )
    return announcements


def _xml_text(item, tag: str) -> str:
    child = item.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def _extract_symbol(text: str) -> str:
    text = text or ""
    for pattern in (r"\bNSE[:\-\s]+([A-Z]{2,12})\b", r"\(([A-Z]{2,12})\)", r"\b([A-Z]{2,12})\b"):
        for match in re.finditer(pattern, text):
            symbol = match.group(1)
            if symbol not in {"NSE", "BSE", "INDIA", "LIMITED", "LTD", "THE", "AND", "FOR"}:
                return symbol
    return ""


def _clean_and_limit(announcements: Sequence[CorporateAnnouncement | None], limit: int) -> list[CorporateAnnouncement]:
    clean = [item for item in announcements if item is not None and item.symbol]
    clean.sort(key=lambda item: item.published_at, reverse=True)
    return clean[:limit]


def _dedupe_announcements(announcements: Sequence[CorporateAnnouncement]) -> list[CorporateAnnouncement]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[CorporateAnnouncement] = []
    for item in announcements:
        key = (item.symbol, item.headline.lower().strip(), item.published_at.strftime("%Y-%m-%d %H:%M:%S"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _within_days(announcements: Sequence[CorporateAnnouncement], days: int) -> list[CorporateAnnouncement]:
    cutoff = datetime.now() - timedelta(days=days)
    return [item for item in announcements if item.published_at >= cutoff]


def _first_value(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value:
            return str(value)
    return ""


def _parse_datetime(raw: str) -> datetime:
    raw = (raw or "").strip()
    for fmt in (
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
    ):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.replace(tzinfo=None)
        except ValueError:
            continue
    return _now()


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _domain(url: str) -> str:
    return urlparse(url).netloc or url

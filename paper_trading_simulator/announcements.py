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


DEFAULT_RSS_URLS = (
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.business-standard.com/rss/markets-106.rss",
    "https://news.google.com/rss/search?q=India%20NSE%20listed%20company%20stock%20announcement&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=NSE%20stock%20order%20contract%20acquisition%20approval&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=site%3Amoneycontrol.com%20NSE%20stock%20order%20contract%20acquisition%20approval&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=site%3Aeconomictimes.indiatimes.com%20NSE%20stock%20order%20contract%20acquisition%20approval&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=site%3Abusiness-standard.com%20India%20stock%20order%20contract%20acquisition%20approval&hl=en-IN&gl=IN&ceid=IN:en",
)

COMMON_COMPANY_SYMBOLS = {
    "reliance industries": "RELIANCE",
    "tata motors": "TATAMOTORS",
    "tata steel": "TATASTEEL",
    "tcs": "TCS",
    "infosys": "INFY",
    "hdfc bank": "HDFCBANK",
    "icici bank": "ICICIBANK",
    "axis bank": "AXISBANK",
    "state bank of india": "SBIN",
    "sbi": "SBIN",
    "larsen": "LT",
    "bharti airtel": "BHARTIARTL",
    "itc": "ITC",
    "mahindra": "M&M",
    "maruti": "MARUTI",
    "bajaj finance": "BAJFINANCE",
    "adani enterprises": "ADANIENT",
    "adani ports": "ADANIPORTS",
    "hindustan unilever": "HINDUNILVR",
    "hcl tech": "HCLTECH",
    "hcl technologies": "HCLTECH",
    "hul": "HINDUNILVR",
    "hdfc": "HDFCBANK",
    "tata motors pv": "TATAMOTORS",
    "bharat petroleum": "BPCL",
    "bpcl": "BPCL",
    "upl": "UPL",
    "sun pharma": "SUNPHARMA",
    "cipla": "CIPLA",
    "dr reddy": "DRREDDY",
    "wipro": "WIPRO",
    "tech mahindra": "TECHM",
    "coal india": "COALINDIA",
    "ongc": "ONGC",
    "ntpc": "NTPC",
    "power grid": "POWERGRID",
}


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
            deduped = _dedupe_announcements(announcements)
            within_window = _within_days(deduped, days)
            clean = _clean_and_limit(within_window, limit)
            if deduped and not clean:
                oldest = min(item.published_at for item in deduped).strftime("%Y-%m-%d")
                newest = max(item.published_at for item in deduped).strftime("%Y-%m-%d")
                return _result(
                    self.name,
                    [],
                    False,
                    f"Manual upload parsed {len(deduped)} rows, but none are inside the {days}-day lookback window. File dates: {oldest} to {newest}. Increase lookback days.",
                    fetched_at,
                    "manual upload",
                )
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
        selected_urls = urls or DEFAULT_RSS_URLS
        self.urls = [url.strip() for url in selected_urls if url.strip()]
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
        clean = _clean_and_limit(_dedupe_announcements(_within_days(announcements, days)), limit)
        if clean:
            message = (
                f"RSS/news provider loaded {len(clean)} rows from {len(self.urls)} feed(s). "
                "This is a latest-news snapshot; the count changes only when source feeds publish new items."
            )
            return _result(self.name, clean, True, message, fetched_at, ", ".join(self.urls))
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
    providers.append(RSSNewsAnnouncementProvider(rss_urls or DEFAULT_RSS_URLS))
    return FallbackAnnouncementProvider(providers)


def parse_announcement_csv(csv_text: str, source: str = "Manual Upload Provider") -> list[CorporateAnnouncement]:
    csv_text = _to_text(csv_text)
    csv_text = _trim_to_csv_header(csv_text)
    delimiter = _detect_delimiter(csv_text)
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
    announcements: list[CorporateAnnouncement] = []
    for row in reader:
        normalized = {str(key).strip().lower(): value for key, value in row.items() if key is not None}
        symbol = _first_value(normalized, "symbol", "symb", "stock", "ticker", "security")
        company = _first_value(normalized, "company", "company name", "company_name", "sm_name", "name") or symbol
        headline = _first_value(
            normalized,
            "headline",
            "subject",
            "event/subject",
            "event subject",
            "event",
            "desc",
            "announcement",
            "title",
            "details",
        )
        details = _first_value(
            normalized,
            "details",
            "attchmnttext",
            "description",
            "summary",
            "type of submission",
        ) or headline
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
    if announcements:
        return announcements
    positional = _parse_positional_announcement_csv(csv_text, source, delimiter)
    if positional:
        return positional
    return _parse_loose_nse_lines(csv_text, source)


def _parse_positional_announcement_csv(csv_text: str, source: str, delimiter: str) -> list[CorporateAnnouncement]:
    rows = list(csv.reader(io.StringIO(csv_text), delimiter=delimiter))
    if not rows:
        return []
    header = [cell.strip().lower() for cell in rows[0]]
    symbol_index = _header_index(header, "symbol", "symb", "stock")
    company_index = _header_index(header, "company name", "company", "name")
    headline_index = _header_index(header, "subject", "event/subject", "event subject", "event", "details")
    details_index = _header_index(header, "details", "type of submission", "description")
    date_index = _header_index(header, "broadcast date/time", "date", "time", "receipt", "dissemination")
    if symbol_index is None:
        return []
    announcements: list[CorporateAnnouncement] = []
    for row in rows[1:]:
        if len(row) <= symbol_index:
            continue
        symbol = row[symbol_index].strip().upper()
        if not symbol or symbol == "SYMBOL":
            continue
        company = _cell(row, company_index) or symbol
        headline = _cell(row, headline_index) or _cell(row, details_index)
        details = _cell(row, details_index) or headline
        if not headline:
            continue
        announcements.append(
            CorporateAnnouncement(
                symbol=symbol,
                company=company,
                headline=headline,
                details=details,
                published_at=_parse_datetime(_cell(row, date_index)),
                source=source,
            )
        )
    return announcements


def _parse_loose_nse_lines(csv_text: str, source: str) -> list[CorporateAnnouncement]:
    text = _strip_html(csv_text)
    announcements: list[CorporateAnnouncement] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "SYMBOL" in line.upper():
            continue
        cells = _split_loose_line(line)
        if len(cells) < 3:
            continue
        symbol = cells[0].strip().upper()
        if not re.fullmatch(r"[A-Z0-9&.-]{2,20}", symbol):
            continue
        company = cells[1].strip() if len(cells) > 1 else symbol
        headline = cells[2].strip() if len(cells) > 2 else ""
        details = cells[3].strip() if len(cells) > 3 else headline
        published_raw = _first_date_like(cells)
        if not headline:
            continue
        announcements.append(
            CorporateAnnouncement(
                symbol=symbol,
                company=company or symbol,
                headline=headline,
                details=details or headline,
                published_at=_parse_datetime(published_raw),
                source=source,
            )
        )
    return announcements


def _strip_html(text: str) -> str:
    text = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", ",", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def _split_loose_line(line: str) -> list[str]:
    if "," in line:
        try:
            return next(csv.reader([line]))
        except csv.Error:
            return [part.strip() for part in line.split(",")]
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    if "|" in line:
        return [part.strip() for part in line.split("|")]
    return [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]


def _first_date_like(cells: Sequence[str]) -> str:
    for cell in cells:
        if re.search(r"\d{1,2}[-/][A-Za-z0-9]{2,}[-/]\d{4}", cell) or re.search(r"\d{4}-\d{2}-\d{2}", cell):
            return cell.strip()
    return ""


def _header_index(header: Sequence[str], *names: str) -> int | None:
    for name in names:
        lowered = name.lower()
        for index, cell in enumerate(header):
            if cell == lowered:
                return index
    for name in names:
        lowered = name.lower()
        for index, cell in enumerate(header):
            if lowered in cell:
                return index
    return None


def _cell(row: Sequence[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _trim_to_csv_header(csv_text: str) -> str:
    lines = [line for line in csv_text.splitlines() if line.strip()]
    if not lines:
        return ""
    for index, line in enumerate(lines):
        lowered = line.lower()
        if "symbol" in lowered and ("company" in lowered or "subject" in lowered or "details" in lowered):
            return "\n".join(lines[index:])
    return "\n".join(lines)


def _detect_delimiter(csv_text: str) -> str:
    sample = "\n".join(csv_text.splitlines()[:5])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
    except csv.Error:
        header = csv_text.splitlines()[0] if csv_text.splitlines() else ""
        counts = {delimiter: header.count(delimiter) for delimiter in [",", "\t", ";", "|"]}
        return max(counts, key=counts.get) if any(counts.values()) else ","


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
    lowered = text.lower()
    for company_name, symbol in COMMON_COMPANY_SYMBOLS.items():
        if company_name in lowered:
            return symbol
    blocked_tokens = {
        "NSE",
        "BSE",
        "INDIA",
        "LIMITED",
        "LTD",
        "THE",
        "AND",
        "FOR",
        "SEBI",
        "IPO",
        "LIVE",
        "UPDATE",
        "UPDATES",
        "SHARE",
        "PRICE",
        "STOCK",
        "MARKET",
        "CLOSE",
        "CLOSING",
        "TECH",
        "VIEW",
        "BULLS",
        "RSI",
        "PV",
        "SC",
    }
    for pattern in (r"\bNSE[:\-\s]+([A-Z]{2,12})\b", r"\(([A-Z]{2,12})\)", r"\b([A-Z]{2,12})\b"):
        for match in re.finditer(pattern, text):
            symbol = match.group(1)
            if symbol not in blocked_tokens:
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
    cutoff_day = (datetime.now() - timedelta(days=max(days, 0) + 1)).date()
    return [item for item in announcements if item.published_at.date() >= cutoff_day]


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

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from queue import Empty, Queue
import time as clock
from typing import Callable, Iterable, Iterator, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from .config import DEFAULT_SYMBOLS, TradingConfig
from .models import Candle


class LiveMarketDataProvider(ABC):
    """Interface for live-like market data. Implementations must yield candles only."""

    @abstractmethod
    def stream(self, symbols: Sequence[str], trading_day: date) -> Iterator[Candle]:
        raise NotImplementedError


class SimulatedNSEMarketDataProvider(LiveMarketDataProvider):
    """Deterministic NSE-like minute candle stream for paper trading and testing."""

    def __init__(self, config: TradingConfig, seed: int = 7):
        self.config = config
        self.seed = seed
        self.start_prices = {
            "RELIANCE": 2860.0,
            "TCS": 3920.0,
            "INFY": 1480.0,
            "HDFCBANK": 1640.0,
            "ICICIBANK": 1110.0,
        }

    def stream(self, symbols: Sequence[str], trading_day: date) -> Iterator[Candle]:
        frames = [self._generate_symbol_day(symbol, trading_day) for symbol in symbols]
        all_candles = pd.concat(frames).sort_values(["timestamp", "symbol"])
        for row in all_candles.itertuples(index=False):
            yield Candle(
                timestamp=row.timestamp.to_pydatetime(),
                symbol=row.symbol,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=int(row.volume),
                previous_close=None,
            )

    def _generate_symbol_day(self, symbol: str, trading_day: date) -> pd.DataFrame:
        symbol_seed = self.seed + sum(ord(ch) for ch in symbol)
        rng = np.random.default_rng(symbol_seed)
        start = datetime.combine(trading_day, self.config.market_open_time)
        end = datetime.combine(trading_day, self.config.market_close_time)
        timestamps = pd.date_range(start=start, end=end, freq="1min")
        base_price = self.start_prices.get(symbol, 1000.0)
        drift = rng.normal(0.00003, 0.00002)
        noise = rng.normal(drift, 0.0012, len(timestamps))
        close = base_price * np.cumprod(1 + noise)
        open_ = np.r_[base_price, close[:-1]]
        high = np.maximum(open_, close) * (1 + rng.uniform(0.0001, 0.0014, len(timestamps)))
        low = np.minimum(open_, close) * (1 - rng.uniform(0.0001, 0.0014, len(timestamps)))
        base_volume = rng.integers(12000, 45000, len(timestamps))
        opening_boost = np.linspace(2.0, 1.0, len(timestamps))
        volume = (base_volume * opening_boost).astype(int)
        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "symbol": symbol,
                "open": open_.round(2),
                "high": high.round(2),
                "low": low.round(2),
                "close": close.round(2),
                "volume": volume,
            }
        )


class CSVMarketDataProvider(LiveMarketDataProvider):
    """Reads minute candles from CSV files with timestamp,symbol,open,high,low,close,volume."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)

    def stream(self, symbols: Sequence[str], trading_day: date) -> Iterator[Candle]:
        data = pd.read_csv(self.csv_path, parse_dates=["timestamp"])
        data = data[data["symbol"].isin(symbols)].copy()
        data = data[data["timestamp"].dt.date == trading_day]
        data = data.sort_values(["timestamp", "symbol"])
        for row in data.itertuples(index=False):
            yield Candle(
                timestamp=row.timestamp.to_pydatetime(),
                symbol=row.symbol,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=int(row.volume),
                previous_close=None,
            )


class RealtimeReplayMarketDataProvider(LiveMarketDataProvider):
    """Replays any provider one market minute at a time for live dashboard demos."""

    def __init__(self, provider: LiveMarketDataProvider, seconds_per_market_minute: float = 60.0):
        self.provider = provider
        self.seconds_per_market_minute = seconds_per_market_minute

    def stream(self, symbols: Sequence[str], trading_day: date) -> Iterator[Candle]:
        previous_timestamp = None
        for candle in self.provider.stream(symbols, trading_day):
            if previous_timestamp is not None and candle.timestamp != previous_timestamp:
                clock.sleep(self.seconds_per_market_minute)
            previous_timestamp = candle.timestamp
            yield candle


class StreamingCSVMarketDataProvider(LiveMarketDataProvider):
    """Polls a growing CSV file and yields new 1-minute candles as they arrive."""

    def __init__(self, csv_path: str | Path, poll_seconds: float = 2.0):
        self.csv_path = Path(csv_path)
        self.poll_seconds = poll_seconds

    def stream(self, symbols: Sequence[str], trading_day: date) -> Iterator[Candle]:
        seen: set[tuple[str, datetime]] = set()
        end_time = datetime.combine(trading_day, time(15, 21))
        while datetime.now() <= end_time:
            if not self.csv_path.exists():
                clock.sleep(self.poll_seconds)
                continue
            data = pd.read_csv(self.csv_path, parse_dates=["timestamp"])
            if data.empty:
                clock.sleep(self.poll_seconds)
                continue
            data = data[data["symbol"].isin(symbols)].copy()
            data = data[data["timestamp"].dt.date == trading_day]
            data = data.sort_values(["timestamp", "symbol"])
            for row in data.itertuples(index=False):
                timestamp = row.timestamp.to_pydatetime()
                key = (row.symbol, timestamp)
                if key in seen:
                    continue
                seen.add(key)
                yield Candle(
                    timestamp=timestamp,
                    symbol=row.symbol,
                    open=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    volume=int(row.volume),
                    previous_close=None,
                )
            clock.sleep(self.poll_seconds)


class NSELiveQuoteMarketDataProvider(LiveMarketDataProvider):
    """Polls NSE equity quotes and builds paper-trading minute candles from LTP changes."""

    base_url = "https://www.nseindia.com"
    quote_url = "https://www.nseindia.com/api/quote-equity"

    def __init__(self, poll_seconds: float = 60.0, timeout_seconds: float = 10.0):
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-IN,en;q=0.9",
                "Referer": "https://www.nseindia.com/get-quotes/equity",
            }
        )
        self._previous_price: dict[str, float] = {}
        self._previous_volume: dict[str, int] = {}

    def stream(self, symbols: Sequence[str], trading_day: date) -> Iterator[Candle]:
        market_close = datetime.combine(trading_day, time(15, 21))
        while datetime.now() <= market_close:
            for symbol in symbols:
                try:
                    yield self._fetch_candle(symbol.upper())
                except Exception as exc:
                    print(f"NSE quote fetch failed for {symbol}: {exc}")
            clock.sleep(self.poll_seconds)

    def _fetch_candle(self, symbol: str) -> Candle:
        self._warm_session()
        response = self.session.get(
            self.quote_url,
            params={"symbol": symbol, "section": "trade_info"},
            timeout=self.timeout_seconds,
        )
        if response.status_code in {401, 403}:
            self._warm_session(force=True)
            response = self.session.get(
                self.quote_url,
                params={"symbol": symbol, "section": "trade_info"},
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
        price_info = payload.get("priceInfo", {})
        security_info = payload.get("securityInfo", {})
        metadata = payload.get("metadata", {})

        last_price = float(price_info["lastPrice"])
        previous_price = self._previous_price.get(symbol, last_price)
        cumulative_volume = int(
            payload.get("marketDeptOrderBook", {}).get("tradeInfo", {}).get("totalTradedVolume")
            or metadata.get("totalTradedVolume")
            or self._previous_volume.get(symbol, 0)
        )
        previous_volume = self._previous_volume.get(symbol, cumulative_volume)
        minute_volume = max(cumulative_volume - previous_volume, 0)
        if minute_volume == 0:
            minute_volume = previous_volume if previous_volume > 0 else 1

        self._previous_price[symbol] = last_price
        self._previous_volume[symbol] = cumulative_volume
        timestamp = datetime.now().replace(second=0, microsecond=0)
        return Candle(
            timestamp=timestamp,
            symbol=symbol,
            open=round(previous_price, 2),
            high=round(max(previous_price, last_price), 2),
            low=round(min(previous_price, last_price), 2),
            close=round(last_price, 2),
            volume=minute_volume,
            previous_close=None,
        )

    def _warm_session(self, force: bool = False) -> None:
        if force:
            self.session.cookies.clear()
        if self.session.cookies:
            return
        response = self.session.get(self.base_url, timeout=self.timeout_seconds)
        response.raise_for_status()


class YahooNSELiveQuoteMarketDataProvider(LiveMarketDataProvider):
    """Fetches NSE-listed equity 1-minute candles from Yahoo Finance symbols like INFY.NS."""

    chart_url = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS"

    def __init__(self, poll_seconds: float = 60.0, timeout_seconds: float = 10.0):
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self._seen: set[tuple[str, datetime]] = set()

    def stream(self, symbols: Sequence[str], trading_day: date) -> Iterator[Candle]:
        market_close = datetime.combine(trading_day, time(15, 21))
        while datetime.now() <= market_close:
            for symbol in symbols:
                try:
                    for candle in self._fetch_new_candles(symbol.upper(), trading_day):
                        yield candle
                except Exception as exc:
                    print(f"Yahoo NSE quote fetch failed for {symbol}: {exc}")
            clock.sleep(self.poll_seconds)

    def _fetch_new_candles(self, symbol: str, trading_day: date) -> list[Candle]:
        response = self.session.get(
            self.chart_url.format(symbol=symbol),
            params={"interval": "1m", "range": "1d"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("chart", {}).get("result") or []
        if not result:
            return []
        data = result[0]
        timestamps = data.get("timestamp") or []
        quote = (data.get("indicators", {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
        candles: list[Candle] = []
        for index, raw_timestamp in enumerate(timestamps):
            timestamp = datetime.fromtimestamp(raw_timestamp, ZoneInfo("Asia/Kolkata")).replace(second=0, microsecond=0, tzinfo=None)
            if timestamp.date() != trading_day:
                continue
            key = (symbol, timestamp)
            if key in self._seen:
                continue
            values = [opens[index], highs[index], lows[index], closes[index]]
            if any(value is None for value in values):
                continue
            self._seen.add(key)
            candles.append(
                Candle(
                    timestamp=timestamp,
                    symbol=symbol,
                    open=round(float(opens[index]), 2),
                    high=round(float(highs[index]), 2),
                    low=round(float(lows[index]), 2),
                    close=round(float(closes[index]), 2),
                    volume=int(volumes[index] or 0),
                )
            )
        return candles

    def fetch_latest_candle(self, symbol: str) -> Candle | None:
        response = self.session.get(
            self.chart_url.format(symbol=symbol.upper()),
            params={"interval": "1m", "range": "1d"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("chart", {}).get("result") or []
        if not result:
            return None
        data = result[0]
        meta = data.get("meta", {})
        timestamps = data.get("timestamp") or []
        quote = (data.get("indicators", {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        regular_price = meta.get("regularMarketPrice")
        regular_time = meta.get("regularMarketTime")
        day_high = meta.get("regularMarketDayHigh")
        day_low = meta.get("regularMarketDayLow")
        day_volume = meta.get("regularMarketVolume")
        previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        if regular_price is not None and regular_time is not None:
            timestamp = datetime.fromtimestamp(regular_time, ZoneInfo("Asia/Kolkata")).replace(second=0, microsecond=0, tzinfo=None)
            latest_open = None
            for index, value in enumerate(opens):
                if value is not None:
                    latest_open = value
                    break
            return Candle(
                timestamp=timestamp,
                symbol=symbol.upper(),
                open=round(float(latest_open or regular_price), 2),
                high=round(float(day_high or regular_price), 2),
                low=round(float(day_low or regular_price), 2),
                close=round(float(regular_price), 2),
                volume=int(day_volume or 0),
                previous_close=round(float(previous_close), 2) if previous_close is not None else None,
            )

        for index in range(len(timestamps) - 1, -1, -1):
            values = [opens[index], highs[index], lows[index], closes[index]]
            if any(value is None for value in values):
                continue
            timestamp = datetime.fromtimestamp(timestamps[index], ZoneInfo("Asia/Kolkata")).replace(second=0, microsecond=0, tzinfo=None)
            return Candle(
                timestamp=timestamp,
                symbol=symbol.upper(),
                open=round(float(opens[index]), 2),
                high=round(float(highs[index]), 2),
                low=round(float(lows[index]), 2),
                close=round(float(closes[index]), 2),
                volume=int(volumes[index] or 0),
                previous_close=None,
            )
        return None


class KiteLiveMarketDataProvider(LiveMarketDataProvider):
    """Streams live Kite ticks and converts them into 1-minute candles for paper trading."""

    source_name = "Kite Connect WebSocket"

    def __init__(
        self,
        api_key: str,
        access_token: str,
        symbol_token_map: dict[str, int] | None = None,
        tick_callback: Callable[[datetime, str, float, int | None, str], None] | None = None,
        idle_timeout_seconds: float = 90.0,
    ):
        self.api_key = api_key
        self.access_token = access_token
        self.symbol_token_map = {key.upper(): int(value) for key, value in (symbol_token_map or {}).items()}
        self.tick_callback = tick_callback
        self.idle_timeout_seconds = idle_timeout_seconds
        self._queue: Queue[Candle] = Queue()
        self._current_candles: dict[str, dict] = {}
        self._previous_volume: dict[str, int] = defaultdict(int)
        self._token_symbol: dict[int, str] = {}
        self._last_tick_at = datetime.now()
        self._closed = False

    def stream(self, symbols: Sequence[str], trading_day: date) -> Iterator[Candle]:
        clean_symbols = [symbol.upper() for symbol in symbols]
        self._resolve_missing_tokens(clean_symbols)
        self._token_symbol = {token: symbol for symbol, token in self.symbol_token_map.items() if symbol in clean_symbols}
        if not self._token_symbol:
            raise ValueError("No Kite instrument tokens found. Provide symbols or KITE_SYMBOL_TOKENS.")

        kws = self._build_ticker()
        instrument_tokens = list(self._token_symbol.keys())

        def on_ticks(_ws, ticks):
            self._last_tick_at = datetime.now()
            for tick in ticks:
                self._handle_tick(tick)

        def on_connect(ws, _response):
            ws.subscribe(instrument_tokens)
            ws.set_mode(ws.MODE_QUOTE, instrument_tokens)

        def on_close(_ws, code, reason):
            self._closed = True
            print(f"Kite WebSocket closed: {code} {reason}")

        def on_error(_ws, code, reason):
            print(f"Kite WebSocket error: {code} {reason}")

        kws.on_ticks = on_ticks
        kws.on_connect = on_connect
        kws.on_close = on_close
        kws.on_error = on_error
        kws.connect(threaded=True)

        market_close = datetime.combine(trading_day, time(15, 21))
        while datetime.now() <= market_close and not self._closed:
            try:
                yield self._queue.get(timeout=1)
            except Empty:
                if (datetime.now() - self._last_tick_at).total_seconds() > self.idle_timeout_seconds:
                    print("No Kite ticks received recently; waiting for market data...")
                    self._last_tick_at = datetime.now()

        for candle in self._flush_open_candles():
            yield candle
        kws.close()

    def _build_ticker(self):
        try:
            from kiteconnect import KiteTicker
        except ImportError as exc:
            raise RuntimeError("Install Kite support with `pip install -r requirements-kite.txt`.") from exc
        return KiteTicker(self.api_key, self.access_token)

    def _resolve_missing_tokens(self, symbols: Sequence[str]) -> None:
        missing = [symbol for symbol in symbols if symbol not in self.symbol_token_map]
        if not missing:
            return
        try:
            from kiteconnect import KiteConnect
        except ImportError as exc:
            raise RuntimeError("Install Kite support with `pip install -r requirements-kite.txt`.") from exc
        kite = KiteConnect(api_key=self.api_key)
        kite.set_access_token(self.access_token)
        instruments = kite.instruments("NSE")
        for instrument in instruments:
            symbol = instrument.get("tradingsymbol", "").upper()
            if symbol in missing and instrument.get("instrument_type") == "EQ":
                self.symbol_token_map[symbol] = int(instrument["instrument_token"])
        still_missing = [symbol for symbol in missing if symbol not in self.symbol_token_map]
        if still_missing:
            raise ValueError(f"Could not resolve Kite instrument tokens for: {', '.join(still_missing)}")

    def _handle_tick(self, tick: dict) -> None:
        token = int(tick["instrument_token"])
        symbol = self._token_symbol.get(token)
        if not symbol:
            return
        last_price = float(tick["last_price"])
        timestamp = tick.get("exchange_timestamp") or tick.get("timestamp") or datetime.now()
        timestamp = timestamp.replace(second=0, microsecond=0)
        volume = tick.get("volume_traded")
        if self.tick_callback:
            self.tick_callback(timestamp, symbol, last_price, volume, self.source_name)

        current = self._current_candles.get(symbol)
        if current and current["timestamp"] != timestamp:
            self._queue.put(self._to_candle(symbol, current))
            current = None
        if current is None:
            self._current_candles[symbol] = {
                "timestamp": timestamp,
                "open": last_price,
                "high": last_price,
                "low": last_price,
                "close": last_price,
                "volume": 0,
            }
        else:
            current["high"] = max(current["high"], last_price)
            current["low"] = min(current["low"], last_price)
            current["close"] = last_price

        if volume is not None:
            previous = self._previous_volume[symbol]
            self._current_candles[symbol]["volume"] += max(int(volume) - previous, 0)
            self._previous_volume[symbol] = int(volume)

    def _flush_open_candles(self) -> list[Candle]:
        candles = [self._to_candle(symbol, data) for symbol, data in self._current_candles.items()]
        self._current_candles.clear()
        return candles

    @staticmethod
    def _to_candle(symbol: str, data: dict) -> Candle:
        return Candle(
            timestamp=data["timestamp"],
            symbol=symbol,
            open=round(float(data["open"]), 2),
            high=round(float(data["high"]), 2),
            low=round(float(data["low"]), 2),
            close=round(float(data["close"]), 2),
            volume=max(int(data["volume"]), 1),
        )


def default_symbols() -> list[str]:
    return list(DEFAULT_SYMBOLS)


def mock_latest_candle(symbol: str) -> Candle:
    prices = {
        "RELIANCE": 1291.0,
        "TCS": 2198.9,
        "INFY": 1197.5,
        "HDFCBANK": 1992.4,
        "ICICIBANK": 1442.2,
        "SBIN": 807.5,
        "AXISBANK": 1185.0,
        "LT": 3630.0,
        "WIPRO": 260.0,
        "HCLTECH": 1450.0,
    }
    clean_symbol = symbol.upper()
    price = prices.get(clean_symbol, 1000.0)
    return Candle(
        timestamp=datetime.now().replace(second=0, microsecond=0),
        symbol=clean_symbol,
        open=round(price * 0.998, 2),
        high=round(price * 1.004, 2),
        low=round(price * 0.996, 2),
        close=round(price, 2),
        volume=125000,
        previous_close=round(price * 0.992, 2),
    )

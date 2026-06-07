from argparse import ArgumentParser
from datetime import date
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from paper_trading_simulator.config import TradingConfig
from paper_trading_simulator.engine import IntradaySimulator
from paper_trading_simulator.logger import SQLiteTradeLogger
from paper_trading_simulator.market_data import (
    KiteLiveMarketDataProvider,
    NSELiveQuoteMarketDataProvider,
    RealtimeReplayMarketDataProvider,
    SimulatedNSEMarketDataProvider,
    StreamingCSVMarketDataProvider,
    YahooNSELiveQuoteMarketDataProvider,
    default_symbols,
)


def parse_symbols(raw: str) -> list[str]:
    return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]


def parse_symbol_tokens(raw: str) -> dict[str, int]:
    tokens: dict[str, int] = {}
    for item in raw.split(","):
        if not item.strip():
            continue
        symbol, token = item.split(":", maxsplit=1)
        tokens[symbol.strip().upper()] = int(token.strip())
    return tokens


def main() -> None:
    parser = ArgumentParser(description="Run the paper-only intraday session in monitor mode.")
    parser.add_argument("--mode", choices=["demo", "csv", "nse", "yahoo", "kite"], default="demo")
    parser.add_argument("--csv", default="data/live_candles.csv")
    parser.add_argument("--symbols", default=",".join(default_symbols()))
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--seconds-per-minute", type=float, default=60.0)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()

    config = TradingConfig()
    logger = SQLiteTradeLogger(config.database_path)
    if args.reset:
        logger.reset()

    trading_day = date.fromisoformat(args.day)
    symbols = parse_symbols(args.symbols)
    if args.mode == "csv":
        provider = StreamingCSVMarketDataProvider(args.csv, poll_seconds=args.poll_seconds)
    elif args.mode == "nse":
        provider = NSELiveQuoteMarketDataProvider(poll_seconds=args.poll_seconds)
    elif args.mode == "yahoo":
        provider = YahooNSELiveQuoteMarketDataProvider(poll_seconds=args.poll_seconds)
    elif args.mode == "kite":
        api_key = os.environ.get("KITE_API_KEY")
        access_token = os.environ.get("KITE_ACCESS_TOKEN")
        if not api_key or not access_token:
            raise SystemExit("Set KITE_API_KEY and KITE_ACCESS_TOKEN before running --mode kite.")
        symbol_token_map = parse_symbol_tokens(os.environ.get("KITE_SYMBOL_TOKENS", ""))
        provider = KiteLiveMarketDataProvider(
            api_key=api_key,
            access_token=access_token,
            symbol_token_map=symbol_token_map,
            tick_callback=logger.log_tick,
        )
    else:
        simulated = SimulatedNSEMarketDataProvider(config)
        provider = RealtimeReplayMarketDataProvider(simulated, seconds_per_market_minute=args.seconds_per_minute)

    simulator = IntradaySimulator(config, provider, logger)
    summary = simulator.run(symbols, trading_day)
    print("Live paper session complete")
    print(f"Total P&L: Rs. {summary['total_pnl']:.2f}")
    print(f"Trades taken: {summary['trades_taken']}")
    print(f"SQLite log: {config.database_path}")


if __name__ == "__main__":
    main()

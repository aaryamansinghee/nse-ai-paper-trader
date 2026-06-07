from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from paper_trading_simulator.config import TradingConfig
from paper_trading_simulator.engine import IntradaySimulator
from paper_trading_simulator.logger import SQLiteTradeLogger
from paper_trading_simulator.market_data import SimulatedNSEMarketDataProvider, default_symbols


def main() -> None:
    config = TradingConfig()
    logger = SQLiteTradeLogger(config.database_path)
    logger.reset()
    provider = SimulatedNSEMarketDataProvider(config)
    simulator = IntradaySimulator(config, provider, logger)
    summary = simulator.run(default_symbols(), date.today())
    print("Paper session complete")
    print(f"Total P&L: Rs. {summary['total_pnl']:.2f}")
    print(f"Trades taken: {summary['trades_taken']}")
    print(f"Closed trades: {summary['closed_trades']}")
    print(f"SQLite log: {config.database_path}")


if __name__ == "__main__":
    main()

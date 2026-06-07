import pandas as pd


def add_vwap(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    typical_price = (data["high"] + data["low"] + data["close"]) / 3
    traded_value = typical_price * data["volume"]
    data["vwap"] = traded_value.cumsum() / data["volume"].cumsum().replace(0, pd.NA)
    return data


def add_rsi(frame: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    data = frame.copy()
    change = data["close"].diff()
    gain = change.clip(lower=0)
    loss = -change.clip(upper=0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    data["rsi"] = 100 - (100 / (1 + rs))
    return data


def rolling_average_volume(frame: pd.DataFrame, window: int = 20) -> pd.Series:
    return frame["volume"].rolling(window, min_periods=1).mean()


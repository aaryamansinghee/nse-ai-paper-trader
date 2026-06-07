from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd

from ..models import Signal


class Strategy(ABC):
    name: str

    @abstractmethod
    def generate_signal(self, symbol: str, history: pd.DataFrame, now: datetime) -> Optional[Signal]:
        raise NotImplementedError


from abc import ABC, abstractmethod
from typing import Generator, List
from src.core.types import MarketState

class DataProvider(ABC):

    @abstractmethod
    def fetch_historical_data(
        self, symbol: str, interval: str = "1day", days: int = 30
        ) -> list[MarketState]:
        '''
        Batch mode: Fetches historical data.
        '''
        pass

    @abstractmethod
    def stream_market_data(
        self, symbol: str, interval: str = "1day"
        ) -> Generator[MarketState, None, None]:
        '''
        Streaming mode: Yield market data continuously.
        '''
        pass
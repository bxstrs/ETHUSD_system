"""MT5 Market data fetching - handles real-time price and historical data retrieval."""
import MetaTrader5 as mt5
from typing import Dict, Optional

from src.core.types import TickData
from src.core.exceptions import RateFetchError, TickFetchError
from src.infrastructure.logger.logger import log


class MarketDataFetcher:
    """Fetches market data: ticks, rates, spreads."""

    def __init__(self, connection_manager):
        """
        Args:
            connection_manager: ConnectionManager instance for connection checks
        """
        self.connection_manager = connection_manager

    def get_rates(self, symbol: str, timeframe, n: int = 180) -> Optional[Dict]:
        """Fetch historical rates (bars/candles)."""
        if not self.connection_manager.ensure_connected():
            raise ConnectionError("Not connected to MT5")

        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)

        if rates is None:
            raise RateFetchError(f"Failed to fetch rates for {symbol} on timeframe {timeframe}")

        return {
            "open": [r["open"] for r in rates],
            "high": [r["high"] for r in rates],
            "low": [r["low"] for r in rates],
            "close": [r["close"] for r in rates],
            "timestamp": [r["time"] for r in rates],
        }

    def get_tick(self, symbol: str):

        """Fetch current tick (bid/ask)."""
        if not self.connection_manager.ensure_connected():
            raise ConnectionError("Not connected to MT5")
        
        raw_tick = mt5.symbol_info_tick(symbol)
        
        if raw_tick is None:
            raise TickFetchError(f"Failed to fetch tick for {symbol}")
        
        return TickData(
            symbol=symbol,
            bid=raw_tick.bid,
            ask=raw_tick.ask,
            last=raw_tick.last,
            volume=raw_tick.volume,
            time=raw_tick.time
        )

    def get_spread(self, symbol: str) -> float:
        """Calculate spread in points."""
        tick = self.get_tick(symbol)
        info = mt5.symbol_info(symbol)

        if info is None or info.point == 0:
            return float("inf")

        return (tick.ask - tick.bid) / info.point

"""MT5 Market data fetching - handles real-time price and historical data retrieval."""
import MetaTrader5 as mt5
from typing import Dict, Optional

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
            log(f"Cannot fetch rates: not connected", level="ERROR")
            return None

        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
        if rates is None:
            log(f"Failed to fetch rates for {symbol}", level="WARNING")
            return None

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
            log(f"Cannot fetch tick: not connected", level="ERROR")
            return None

        return mt5.symbol_info_tick(symbol)

    def get_spread(self, symbol: str) -> float:
        """Calculate spread in points."""
        tick = self.get_tick(symbol)
        info = mt5.symbol_info(symbol)

        if not tick or not info or not tick.ask or not tick.bid or info.point == 0:
            return float("inf")

        return (tick.ask - tick.bid) / info.point

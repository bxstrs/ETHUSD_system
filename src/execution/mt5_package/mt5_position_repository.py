"""MT5 Position queries - handles position and deal lookups."""
import MetaTrader5 as mt5

from src.utils.logger import log


class PositionRepository:
    """Queries and retrieves position/deal information."""

    def __init__(self, connection_manager):
        """
        Args:
            connection_manager: ConnectionManager instance
        """
        self.connection_manager = connection_manager

    def get_positions(self, symbol: str):
        """Fetch all open positions for a symbol."""
        if not self.connection_manager.ensure_connected():
            log(f"Cannot fetch positions: not connected", level="ERROR")
            return None

        return mt5.positions_get(symbol=symbol)

    def history_deals_get(self, ticket):
        """Fetch deal history for a position ticket."""
        if not self.connection_manager.ensure_connected():
            log(f"Cannot fetch deals: not connected", level="ERROR")
            return None

        return mt5.history_deals_get(ticket=ticket)

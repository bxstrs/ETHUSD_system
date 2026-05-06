"""MT5Bridge - Facade for MT5 API interactions with separated concerns."""
from src.execution.mt5_package.mt5_connection import ConnectionManager
from src.execution.mt5_package.mt5_market_data import MarketDataFetcher
from src.execution.mt5_package.mt5_order_executor import OrderExecutor
from src.execution.mt5_package.mt5_position_repository import PositionRepository


class MT5Bridge:
    """
    Facade for MT5 API interactions.
    
    Separates concerns into:
    - ConnectionManager: Connection lifecycle
    - MarketDataFetcher: Price data retrieval
    - OrderExecutor: Order execution with retry logic
    - PositionRepository: Position/deal queries
    """

    def __init__(self, login=None, password=None, server=None):
        """Initialize MT5 Bridge with all components."""
        self.connection = ConnectionManager(login, password, server)
        self.market_data = MarketDataFetcher(self.connection)
        self.executor = OrderExecutor(self.connection, self.market_data)
        self.positions = PositionRepository(self.connection)

        # Expose commonly used connection methods
        self.connected = self.connection.connected

    def connect(self) -> bool:
        """Proxy to ConnectionManager.connect()"""
        return self.connection.connect()

    def shutdown(self):
        """Proxy to ConnectionManager.shutdown()"""
        return self.connection.shutdown()

    def ensure_connected(self) -> bool:
        """Proxy to ConnectionManager.ensure_connected()"""
        return self.connection.ensure_connected()

    # Market Data Methods
    def get_rates(self, symbol: str, timeframe, n: int = 180):
        """Proxy to MarketDataFetcher.get_rates()"""
        return self.market_data.get_rates(symbol, timeframe, n)

    def get_tick(self, symbol: str):
        """Proxy to MarketDataFetcher.get_tick()"""
        return self.market_data.get_tick(symbol)

    def get_spread(self, symbol: str) -> float:
        """Proxy to MarketDataFetcher.get_spread()"""
        return self.market_data.get_spread(symbol)

    # Order Execution Methods
    def send_order(self, symbol: str, direction: str, volume: float,
                   magic: int, comment: str = "forward_test", max_retries: int = 3):
        """Proxy to OrderExecutor.send_order()"""
        return self.executor.send_order(symbol, direction, volume, magic, comment, max_retries)

    def close_position(self, position):
        """Proxy to OrderExecutor.close_position()"""
        return self.executor.close_position(position)

    # Position Queries
    def get_positions(self, symbol: str):
        """Proxy to PositionRepository.get_positions()"""
        return self.positions.get_positions(symbol)

    def history_deals_get(self, ticket):
        """Proxy to PositionRepository.history_deals_get()"""
        return self.positions.history_deals_get(ticket)
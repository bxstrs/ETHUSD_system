"""MT5 Connection management - handles initialization, reconnection, and lifecycle."""
import os
import time
import MetaTrader5 as mt5
from dotenv import load_dotenv

from src.utils.logger import log

load_dotenv()


class ConnectionManager:
    """Manages MT5 terminal connection with automatic reconnection logic."""

    def __init__(self, login=None, password=None, server=None):
        self.connected = False
        self.reconnection_attempts = 0
        self.max_reconnection_attempts = 5

        self.login = login or int(os.getenv("MT5_LOGIN", 0))
        self.password = password or os.getenv("MT5_PASSWORD")
        self.server = server or os.getenv("MT5_SERVER")

    def connect(self) -> bool:
        """Initial MT5 connection with exponential backoff."""
        MAX_ATTEMPTS = 5
        BACKOFF_SECONDS = [1, 2, 5, 10, 30]

        for attempt in range(MAX_ATTEMPTS):
            try:
                if self.login:
                    self.connected = mt5.initialize(
                        login=self.login,
                        password=self.password,
                        server=self.server
                    )
                else:
                    self.connected = mt5.initialize()

                if self.connected:
                    log(f"MT5 connected successfully on attempt {attempt + 1}", level="INFO")
                    return True
            except Exception as e:
                pass

            if attempt < MAX_ATTEMPTS - 1:
                wait_time = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                log(f"Connection attempt {attempt + 1} failed. Retrying in {wait_time}s...", level="WARNING")
                time.sleep(wait_time)

        error = mt5.last_error()
        log(f"MT5 connection failed after {MAX_ATTEMPTS} attempts: {error}", level="ERROR")
        raise RuntimeError(f"MT5 init failed after {MAX_ATTEMPTS} attempts: {error}")

    def shutdown(self):
        """Gracefully shutdown MT5 connection."""
        mt5.shutdown()
        self.connected = False

    def ensure_connected(self) -> bool:
        """Check connection, reconnect with backoff if needed."""
        try:
            info = mt5.terminal_info()

            # If terminal_info fails or returns None → connection broken
            if info is None:
                raise RuntimeError("Terminal not available")
            if mt5.account_info() is None:
                raise RuntimeError("Account info unavailable")

            # Connection restored, reset counter
            self.reconnection_attempts = 0
            return True

        except Exception as e:
            self.reconnection_attempts += 1

            if self.reconnection_attempts > self.max_reconnection_attempts:
                log(
                    f"Connection lost ({e}), max reconnection attempts ({self.max_reconnection_attempts}) exceeded",
                    level="ERROR"
                )
                raise RuntimeError(f"Cannot reconnect after {self.max_reconnection_attempts} attempts: {e}")

            # Exponential backoff: [1, 2, 4, 8, 16] seconds
            backoff = min(2 ** (self.reconnection_attempts - 1), 30)
            log(
                f"Connection lost ({e}), attempting reconnect (attempt {self.reconnection_attempts}/"
                f"{self.max_reconnection_attempts}), waiting {backoff}s...",
                level="WARNING"
            )

            time.sleep(backoff)
            self.shutdown()

            try:
                return self.connect()
            except Exception as reconnect_error:
                log(f"Reconnection failed: {reconnect_error}", level="ERROR")
                return False

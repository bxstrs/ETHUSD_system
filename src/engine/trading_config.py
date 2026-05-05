from dataclasses import dataclass
import MetaTrader5 as mt5 
from src.config.loader import load_yaml
 
 
@dataclass(frozen=True)
class TradingConfig:
    """Immutable snapshot of configs/trading.yaml."""
    symbol: str
    timeframe: str
    timeframe_value: int
    deviation: int
    base_volume: float
    tick_sleep: float           # seconds (converted from tick_sleep_ms)
    rate_fetch_interval: int    # seconds between full history refreshes
    checkpoint_interval: int    # ticks between checkpoint saves
    restart_delay: int          # seconds between crash restarts
    max_restart_attempts: int   # -1 = unlimited
 
 
def load_trading_config() -> TradingConfig:
    """Load and return an immutable TradingConfig from trading.yaml."""
    raw = load_yaml("trading.yaml")
 
    return TradingConfig(
        symbol=raw.get("symbol", "ETHUSD#"),
        timeframe=raw.get("timeframe", "H4"),
        timeframe_value=raw.get("timeframe_value", mt5.TIMEFRAME_H4),
        deviation=raw.get("deviation", 3),
        base_volume=raw.get("base_volume", 0.1),
        tick_sleep=raw.get("tick_sleep_ms", 100) / 1000.0,
        rate_fetch_interval=raw.get("rate_fetch_interval_s", 1),
        checkpoint_interval=raw.get("checkpoint_interval_ticks", 100),
        restart_delay=raw.get("restart_delay_seconds", 10),
        max_restart_attempts=raw.get("max_restart_attempts", -1),
    )
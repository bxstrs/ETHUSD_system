"""src/engine/marketstate_builder.py

Handles all market data retrieval and construction of MarketState objects.
Isolated here so the main loop stays free of data-plumbing details,
and so these functions can be tested independently.
"""
from typing import Optional, Tuple

from src.core.types import MarketState
from src.engine.components.trading_config import TradingConfig
from src.utils.logger import log


def fetch_data(
    bridge,
    config: TradingConfig,
    n_bars: int = 220,
) -> Tuple[Optional[dict], Optional[object]]:

    try:
        bridge.ensure_connected()
    except Exception as exc:
        log(f"Connection error: {exc}", level="ERROR")
        return None, None

    history = bridge.get_rates(config.symbol, config.timeframe_value, n_bars)
    tick = bridge.get_tick(config.symbol)

    if history is None or tick is None:
        log("Market data fetch returned invalid response", level="WARNING")
        return None, None

    return history, tick


def build_market_state(
    history: dict,
    tick,
    config: TradingConfig,
    use_previous: bool = False,
) -> MarketState:

    idx = -2 if use_previous else -1

    if not history or not history.get("timestamp") or len(history["timestamp"]) < abs(idx):
        raise ValueError(
            f"Insufficient history: got {len(history.get('timestamp', []))} bars, "
            f"need at least {abs(idx)}"
        )

    if tick is None or tick.bid is None or tick.ask is None:
        raise ValueError(
            f"Invalid tick data: bid={getattr(tick, 'bid', None)}, "
            f"ask={getattr(tick, 'ask', None)}"
        )

    return MarketState(
        symbol=config.symbol,
        interval=config.timeframe,
        timestamp=history["timestamp"][idx],
        open=history["open"][idx],
        high=history["high"][idx],
        low=history["low"][idx],
        close=history["close"][idx],
        bid=tick.bid,
        ask=tick.ask,
    )
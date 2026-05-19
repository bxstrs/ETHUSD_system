"""src/engine/marketstate_builder.py"""
import time
from datetime import datetime, timezone

from typing import Tuple
from domain.market_data import TickData, History, MarketSnapshot
from src.domain.exceptions import MarketDataUnavailable, TickFetchError
from src.engine.components.trading_config import TradingConfig
from src.infrastructure.logger.logger import log


def fetch_full_market_data(
    bridge,
    config: TradingConfig,
) -> Tuple[History, TickData]:

    for attempt in range(config.max_fetch_attempts):

        try:
            bridge.ensure_connected()
            history = bridge.get_rates(config.symbol, config.timeframe_value, config.bar_lookback)
            tick = bridge.get_tick(config.symbol)

            return history, tick
        
        except MarketDataUnavailable as exc:
            log(
                f"Market data fetch failed "
                f"({attempt + 1}/{config.max_fetch_attempts}): {exc}",
                level="WARNING",
            )

        time.sleep(config.tick_sleep)

    raise MarketDataUnavailable(
        f"Failed after {config.max_fetch_attempts} attempts"
    )


def get_market_snapshot(
    bridge,
    config,
    force_full: bool = False,
) -> MarketSnapshot:

    if force_full:
        history, tick = fetch_full_market_data(bridge, config)
        return MarketSnapshot(
            tick            = tick,
            history         = history,
            is_full_refresh = True,
        )
    last_error = None

    for attempt in range(1, config.max_fetch_attempts + 1):
        try:
            tick = bridge.get_tick(config.symbol)

            return MarketSnapshot(
                tick            = tick,
                history         = None,
                is_full_refresh = False,
            )
        except TickFetchError as exc:
            last_error = exc
            log(f"Tick fetch failed ({attempt}/{config.max_fetch_attempts}): {exc}",level="WARNING",)

            if attempt < config.max_fetch_attempts:
                time.sleep(0.25)

    raise MarketDataUnavailable (f"Unable to fetch market tick aftern {config.max_fetch_attempts} attempts") from last_error

'''
def build_snapshot(
    history: History,
    tick: TickData,
    config: TradingConfig,
    use_previous: bool = False,
) -> MarketSnapshot:

    idx = -2 if use_previous else -1

    if not history or not history.time_unix or len(history.time_unix) < abs(idx):
        raise ValueError(
            f"Insufficient history: got {len(history.time_unix)} bars, "
            f"need at least {abs(idx)}"
        )

    if tick is None or tick.bid is None or tick.ask is None:
        raise ValueError(
            f"Invalid tick data: bid={getattr(tick, 'bid', None)}, "
            f"ask={getattr(tick, 'ask', None)}"
        )

    return MarketState(
        symbol      = config.symbol,
        interval    = config.timeframe,
        timestamp   = datetime.fromtimestamp(history["timestamp"][idx], tz=timezone.utc),
        open        = history["open"][idx],
        high        = history["high"][idx],
        low         = history["low"][idx],
        close       = history["close"][idx],
        bid         = tick.bid,
        ask         = tick.ask,
        volume      = tick.volume,
    )
'''
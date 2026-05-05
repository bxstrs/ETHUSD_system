"""src/engine/entry_handler.py
 
Handles the full trade entry lifecycle:
  1. Pre-entry guards (risk limits, open position, bar dedup)
  2. Signal generation
  3. TradeSetup logging
  4. Order submission to MT5
  5. TradeExecution logging
  6. Position metadata registration
 
Extracted from forward.py so the logic can be read, tested, and modified
without touching the main loop orchestration.
"""
import uuid
from typing import Optional, Tuple
 
import MetaTrader5 as mt5
 
from src.core.types import Direction, MarketState, TradeExecution, TradeSetup
from src.engine.trading_config import TradingConfig
from src.infrastructure.logger.data_logger import DataLogger
from src.infrastructure.logger.logger import log
 
 
def try_entry(
    bridge,
    position_manager,
    strategy,
    market_state: MarketState,
    history: dict,
    spread: float,
    current_bar_time,
    last_entry_bar_time,
    datalogger: DataLogger,
    config: TradingConfig,
) -> Tuple[bool, object]:

    # ── Pre-entry guards ──────────────────────────────────────────────
    if not position_manager.can_trade():
        return False, last_entry_bar_time
 
    if position_manager.has_open_position(config.symbol, strategy.strategy_id):
        return False, last_entry_bar_time
 
    if last_entry_bar_time == current_bar_time:
        return False, last_entry_bar_time
 
    # ── Signal generation ─────────────────────────────────────────────
    signal = strategy.generate_signal(
        market_state=market_state,
        history=history,
        spread=spread,
    )
 
    if not signal:
        return False, last_entry_bar_time
 
    direction_str = "BUY" if signal.direction.name == "LONG" else "SELL"
    direction_enum = Direction.LONG if signal.direction.name == "LONG" else Direction.SHORT
 
    log(f"[ENTRY] {signal.direction} at expected price: {signal.entry_price}", level="SIGNAL")
 
    # ── Build and log TradeSetup ──────────────────────────────────────
    setup_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())
    indicator_values = _get_indicator_values(strategy)
 
    setup = TradeSetup(
        setup_id=setup_id,
        strategy_id=strategy.strategy_id,
        symbol=config.symbol,
        timestamp=market_state.timestamp,
        direction=direction_enum,
        trigger_price=signal.entry_price,
        bb_upper=indicator_values.get("bb_upper", 0.0),
        bb_lower=indicator_values.get("bb_lower", 0.0),
        bb_middle=indicator_values.get("bb_middle", 0.0),
        bandwidth=indicator_values.get("bandwidth", 0.0),
        bandwidth_ma=indicator_values.get("bandwidth_ma", 0.0),
        atr=indicator_values.get("atr", 0.0),
        spread=spread,
        intended_entry_price=signal.entry_price,
        intended_volume=config.base_volume,
        hour_of_day=market_state.timestamp.hour,
        candle_open=market_state.open,
        candle_high=market_state.high,
        candle_low=market_state.low,
        candle_close=market_state.close,
        prev_trade_pnl=None,
        adaptive_filter_active=False,
    )
    datalogger.log_trade_setup(setup)
 
    # ── Submit order ──────────────────────────────────────────────────
    result = bridge.send_order(
        symbol=config.symbol,
        direction=direction_str,
        volume=config.base_volume,
        magic=strategy.magic_number,
        comment=strategy.strategy_id,
    )
 
    if result is None:
        log("Order failed: no response from MT5", level="ERROR")
        return False, last_entry_bar_time
 
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log(
            f"Order failed: retcode={result.retcode}, "
            f"comment={getattr(result, 'comment', 'N/A')}",
            level="ERROR",
        )
        return False, last_entry_bar_time
 
    # ── Log execution and register position ───────────────────────────
    execution = TradeExecution(
        execution_id=execution_id,
        setup_id=setup_id,
        filled_entry_price=result.price,
        filled_volume=config.base_volume,
        filled_time=market_state.timestamp,
        slippage=abs(result.price - signal.entry_price),
        latency_ms=0,
        status="SUCCESS",
    )
    datalogger.log_trade_execution(execution)
 
    position_manager.track_position_entry(
        position_ticket=result.order,
        setup_id=setup_id,
        execution_id=execution_id,
        entry_slippage=execution.slippage,
        entry_latency_ms=execution.latency_ms,
    )
 
    return True, current_bar_time
 
 
# ── Private helpers ───────────────────────────────────────────────────────────
 
def _get_indicator_values(strategy) -> dict:
    """Safely retrieve indicator snapshot from strategy, return {} on failure."""
    if not hasattr(strategy, "get_indicator_values"):
        return {}
    try:
        return strategy.get_indicator_values() or {}
    except Exception as exc:
        log(f"Failed to fetch strategy indicator values: {exc}", level="WARNING")
        return {}
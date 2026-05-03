'''src/engine/forward.py'''
import time
import uuid
import signal
import traceback
from typing import Optional, Tuple

import MetaTrader5 as mt5

from src.core.types import MarketState, TradeSetup, TradeExecution, Direction
from src.strategies.strategy_loader import load_strategy
from src.execution.mt5_bridge import MT5Bridge
from src.utils.logger import log
from src.utils.line_notifier import LineNotifier
from src.utils.data_logger import DataLogger
from src.execution.position_manager import PositionManager
from src.utils.state_manager import StateManager
from src.config.loader import load_yaml


# ============================================================================
# Configuration (loaded from configs/trading.yaml)
# ============================================================================

trading_config = load_yaml("trading.yaml")

SYMBOL = trading_config.get("symbol", "ETHUSD#")
STR_TIMEFRAME = trading_config.get("timeframe", "H4")
TIMEFRAME = trading_config.get("timeframe_value", mt5.TIMEFRAME_H4)
DEVIATION = trading_config.get("deviation", 3)
BASE_VOLUME = trading_config.get("base_volume", 0.1)

TICK_SLEEP = trading_config.get("tick_sleep_ms", 100) / 1000.0  # Convert ms to seconds
RATE_FETCH_INTERVAL = trading_config.get("rate_fetch_interval_s", 1)
CHECKPOINT_INTERVAL = trading_config.get("checkpoint_interval_ticks", 100)
RESTART_DELAY_SECONDS = trading_config.get("restart_delay_seconds", 10)
MAX_RESTART_ATTEMPTS = trading_config.get("max_restart_attempts", -1)

state_manager = StateManager()
_should_exit = False


def _signal_handler(signum, frame):
    global _should_exit
    _should_exit = True
    log(f"Received shutdown signal ({signum})", level="INFO")


def send_notification(notifier: LineNotifier, message: str) -> None:
    if notifier and notifier.enabled:
        notifier.notify(message)


def fetch_data(bridge) -> Tuple[Optional[dict], Optional[object]]:
    try:
        bridge.ensure_connected()
    except Exception as exc:
        log(f"Connection error: {exc}", level="ERROR")
        return None, None

    history = bridge.get_rates(SYMBOL, TIMEFRAME, 220)
    tick = bridge.get_tick(SYMBOL)

    if history is None or tick is None:
        log("Market data fetch returned invalid response", level="WARNING")
        return None, None

    return history, tick


def build_market_state(history, tick, use_previous=False):
    idx = -2 if use_previous else -1
    
    if not history or not history.get("timestamp") or len(history["timestamp"]) < abs(idx):
        raise ValueError(f"Insufficient history data: got {len(history.get('timestamp', []))} bars, need at least {abs(idx)}")

    return MarketState(
        symbol=SYMBOL,
        interval=STR_TIMEFRAME,
        timestamp=history["timestamp"][idx],
        open=history["open"][idx],
        high=history["high"][idx],
        low=history["low"][idx],
        close=history["close"][idx],
        bid=tick.bid,
        ask=tick.ask,
    )


def warmup_strategy(strategy, history):
    closes = history["close"]
    highs = history["high"]
    lows = history["low"]

    for i in range(1, len(closes)):
        sub_history = {
            "close": closes[: i + 1],
            "high": highs[: i + 1],
            "low": lows[: i + 1],
            "open": history["open"][: i + 1],
            "timestamp": history["timestamp"][: i + 1],
        }
        if hasattr(strategy, "on_new_bar"):
            strategy.on_new_bar(sub_history)
    if len(history["timestamp"]):
        strategy._current_bar_time = history["timestamp"][-1]


def try_entry(
    bridge,
    position_manager,
    strategy,
    market_state,
    history,
    spread,
    current_bar_time,
    _last_entry_bar_time,
    datalogger: DataLogger,
) -> Tuple[bool, Optional[object]]:
    if not position_manager.can_trade():
        return False, _last_entry_bar_time

    if position_manager.has_open_position(SYMBOL, strategy.strategy_id):
        return False, _last_entry_bar_time

    if _last_entry_bar_time == current_bar_time:
        return False, _last_entry_bar_time

    signal = strategy.generate_signal(
        market_state=market_state,
        history=history,
        spread=spread,
    )

    if not signal:
        return False, _last_entry_bar_time

    direction = "BUY" if signal.direction.name == "LONG" else "SELL"
    direction_enum = Direction.LONG if signal.direction.name == "LONG" else Direction.SHORT

    log(f"[ENTRY] {signal.direction} at expected price: {signal.entry_price}", level="SIGNAL")

    setup_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())

    indicator_values = {}
    if hasattr(strategy, "get_indicator_values"):
        try:
            indicator_values = strategy.get_indicator_values() or {}
        except Exception as exc:
            log(f"Failed to fetch strategy indicator values: {exc}", level="WARNING")
            indicator_values = {}

    setup = TradeSetup(
        setup_id=setup_id,
        strategy_id=strategy.strategy_id,
        symbol=SYMBOL,
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
        intended_volume=BASE_VOLUME,
        hour_of_day=market_state.timestamp.hour,
        candle_open=market_state.open,
        candle_high=market_state.high,
        candle_low=market_state.low,
        candle_close=market_state.close,
        prev_trade_pnl=None,
        adaptive_filter_active=False,
    )

    datalogger.log_trade_setup(setup)

    result = bridge.send_order(
        symbol=SYMBOL,
        direction=direction,
        volume=BASE_VOLUME,
        magic=strategy.magic_number,
        comment=strategy.strategy_id,
    )

    if result is None:
        log("Order failed: no response from MT5", level="ERROR")
        return False, _last_entry_bar_time

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log(
            f"Order failed: retcode={result.retcode}, comment={getattr(result, 'comment', 'N/A')}",
            level="ERROR",
        )
        return False, _last_entry_bar_time

    execution = TradeExecution(
        execution_id=execution_id,
        setup_id=setup_id,
        filled_entry_price=result.price,
        filled_volume=BASE_VOLUME,
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


def save_checkpoint(position_manager, strategy):
    positions = position_manager.get_strategy_positions(SYMBOL, strategy.strategy_id)
    state_manager.save_positions(
        [pos for pos, _ in positions],
        strategy.strategy_id,
    )


def main_loop(strategy_name: str, notifier: LineNotifier) -> None:
    global _should_exit
    _should_exit = False

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    bridge = MT5Bridge()
    try:
        bridge.connect()
    except Exception as exc:
        message = f"MT5 initialization failed: {exc}"
        log(message, level="ERROR")
        send_notification(notifier, message)
        raise

    strategy = load_strategy(strategy_name)
    datalogger = DataLogger(strategy_id=strategy.strategy_id, symbol=SYMBOL)
    position_manager = PositionManager(bridge, datalogger=datalogger)

    log(f"Loaded strategy: {strategy.strategy_id}")

    checkpoint_data = state_manager.load_positions(strategy.strategy_id)
    if checkpoint_data is not None:
        live_positions = position_manager.get_strategy_positions(SYMBOL, strategy.strategy_id)
        recovered = state_manager.reconcile_positions(
            bridge,
            SYMBOL,
            [pos for pos, _ in live_positions],
            checkpoint_data,
        )
        if recovered:
            message = (
                f"Checkpoint recovery detected {len(recovered)} missing position(s): "
                f"{[p['ticket'] for p in recovered]}"
            )
            log(message, level="WARNING")
            send_notification(notifier, message)

    history, tick = fetch_data(bridge)
    if history is None:
        message = "Initial market data fetch failed"
        log(message, level="ERROR")
        send_notification(notifier, message)
        raise RuntimeError(message)

    warmup_strategy(strategy, history)

    tick_counter = 0
    ticks_since_last_checkpoint = 0
    _last_entry_bar_time = None
    current_bar_time = history["timestamp"][-1]
    last_fetch_time = time.time()
    loop_start = time.time()
    _had_position = position_manager.has_open_position(SYMBOL, strategy.strategy_id)

    try:
        while not _should_exit:
            tick_counter += 1
            ticks_since_last_checkpoint += 1
            loop_iteration_start = time.time()

            if ticks_since_last_checkpoint >= CHECKPOINT_INTERVAL:
                save_checkpoint(position_manager, strategy)
                ticks_since_last_checkpoint = 0

            if time.time() - last_fetch_time > RATE_FETCH_INTERVAL:
                history, tick = fetch_data(bridge)
                if history is None or tick is None:
                    log("Failed to fetch market data, retrying...", level="WARNING")
                    time.sleep(TICK_SLEEP)
                    continue
                current_bar_time = history["timestamp"][-1]
                last_fetch_time = time.time()
                if tick_counter % 100 == 0:
                    log(
                        f"[TICK {tick_counter}] Bar time: {current_bar_time}, "
                        f"Bid: {tick.bid:.5f}, Ask: {tick.ask:.5f}",
                        level="INFO",
                    )
            else:
                tick = bridge.get_tick(SYMBOL)
                if tick is None:
                    log(f"[TICK {tick_counter}] Failed to fetch tick data", level="ERROR")
                    time.sleep(TICK_SLEEP)
                    continue
                if tick_counter % 100 == 0:
                    log(
                        f"[TICK {tick_counter}] Bid: {tick.bid:.5f}, Ask: {tick.ask:.5f}",
                        level="INFO",
                    )

            if history is None:
                log("[DATA ERROR] history is None, skipping iteration", level="ERROR")
                time.sleep(TICK_SLEEP)
                continue

            current_state = build_market_state(history, tick, use_previous=False)
            position_manager.handle_exit(strategy, current_state)
            current_has_position = position_manager.has_open_position(SYMBOL, strategy.strategy_id)

            if _had_position and not current_has_position:
                log(
                    "[POSITION CLOSED] Blocking re-entry for current bar.",
                    level="INFO",
                )
                _last_entry_bar_time = current_bar_time

            _had_position = current_has_position

            setup_state = build_market_state(history, tick, True)
            spread = bridge.get_spread(SYMBOL)

            execute, _last_entry_bar_time = try_entry(
                bridge,
                position_manager,
                strategy,
                setup_state,
                history,
                spread,
                current_bar_time,
                _last_entry_bar_time,
                datalogger,
            )

            if execute:
                _had_position = True
                loop_time = time.time() - loop_iteration_start
                log(f"Signal executed in {loop_time:.3f}s")

            time.sleep(TICK_SLEEP)

    except KeyboardInterrupt:
        log("Stopped by user", level="INFO")
    except Exception as exc:
        message = f"Unhandled exception in forward loop: {exc}"
        log(message, level="ERROR")
        send_notification(notifier, message)
        traceback.print_exc()
        raise
    finally:
        log("Graceful shutdown: saving state and closing resources", level="INFO")
        save_checkpoint(position_manager, strategy)
        datalogger.close()
        bridge.shutdown()
        elapsed = time.time() - loop_start
        log(
            f"Stopped. Processed {tick_counter} ticks in {elapsed:.1f}s "
            f"({tick_counter/elapsed:.1f} ticks/sec)",
            level="INFO",
        )


def run_forward(strategy_name: str = "bb_squeeze") -> None:
    notifier = LineNotifier()
    attempt = 0

    while MAX_RESTART_ATTEMPTS < 0 or attempt < MAX_RESTART_ATTEMPTS:
        attempt += 1
        try:
            main_loop(strategy_name, notifier)
            break
        except KeyboardInterrupt:
            log("Forward runner stopped by user", level="INFO")
            break
        except Exception as exc:
            message = (
                f"Forward runner crashed on attempt {attempt}: {exc}. "
                f"Restarting in {RESTART_DELAY_SECONDS}s."
            )
            log(message, level="ERROR")
            send_notification(notifier, message)
            traceback.print_exc()
            if MAX_RESTART_ATTEMPTS >= 0 and attempt >= MAX_RESTART_ATTEMPTS:
                log("Reached max restart attempts, exiting", level="ERROR")
                break
            time.sleep(RESTART_DELAY_SECONDS)

    log("Forward runner exiting", level="INFO")

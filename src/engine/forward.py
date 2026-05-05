"""src/engine/forward.py
 
Top-level orchestrator for the live forward-trading loop.
 
Responsibilities (and nothing else):
  - Register OS signal handlers for graceful shutdown
  - Bootstrap MT5, strategy, logger, and position manager
  - Run crash-recovery reconciliation on startup
  - Drive the tick loop: data refresh → exit check → entry attempt
  - Periodic checkpointing and graceful shutdown
  - Outer restart loop with exponential-backoff in run_forward()
 
All heavy logic lives in dedicated modules:
  trading_config  – immutable config dataclass
  data_handler    – fetch_data / build_market_state
  entry_handler   – signal → order → logging pipeline
  warmup          – indicator warm-up replay
"""
import signal
import time
import traceback
 
from src.engine.components.entry_handler import try_entry
from src.engine.components.data_fetcher import build_market_state, fetch_data
from src.engine.trading_config import TradingConfig, load_trading_config
from src.engine.components.warmup import warmup_strategy
from src.execution.mt5_bridge import MT5Bridge
from src.domain.position_manager import PositionManager
from src.strategies.strategy_loader import load_strategy
from src.infrastructure.logger.data_logger import DataLogger
from src.infrastructure.logger.logger import log
from src.infrastructure.notifier.line_notifier import LineNotifier
from src.infrastructure.state.position_storage import PositionStorage
 
 
# ── Module-level singletons (config is frozen, state_manager is stateless) ───
_config: TradingConfig = load_trading_config()
_position_storage: PositionStorage = PositionStorage()
_should_exit: bool = False
 
 
# ── Signal handling ───────────────────────────────────────────────────────────
 
def _signal_handler(signum, frame) -> None:
    global _should_exit
    _should_exit = True
    log(f"Received shutdown signal ({signum})", level="INFO")
 
 
# ── Private helpers ───────────────────────────────────────────────────────────
 
def _notify(notifier: LineNotifier, message: str) -> None:
    """Send a LINE notification if the notifier is configured."""
    if notifier and notifier.enabled:
        notifier.notify(message)
 
 
def _save_checkpoint(position_manager: PositionManager, strategy) -> None:
    """Persist current open positions to disk for crash recovery."""
    positions = position_manager.get_strategy_positions(
        _config.symbol, strategy.strategy_id
    )
    _position_storage.save_positions(
        [pos for pos, _ in positions],
        strategy_id = strategy.strategy_id,
        metadata = position_manager._position_metadata,
    )
 
 
def _run_recovery(
    bridge,
    position_manager: PositionManager,
    strategy,
    notifier: LineNotifier,
) -> None:
    """
    On startup, compare the last checkpoint with live MT5 positions.
    Logs and notifies if any positions appear missing.
    """
    checkpoint_data = _position_storage.load_positions(strategy.strategy_id)
    if checkpoint_data is None:
        return
 
    live_positions = position_manager.get_strategy_positions(
        _config.symbol, strategy.strategy_id
    )
    recovered = _position_storage.reconcile_positions(
        bridge,
        _config.symbol,
        [pos for pos, _ in live_positions],
        checkpoint_data,
    )
 
    if recovered:
        message = (
            f"Checkpoint recovery: {len(recovered)} missing position(s): "
            f"{[p['ticket'] for p in recovered]}"
        )
        log(message, level="WARNING")
        _notify(notifier, message)
 
 
# ── Core loop ─────────────────────────────────────────────────────────────────
 
def main_loop(strategy_name: str, notifier: LineNotifier) -> None:

    global _should_exit
    _should_exit = False
 
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
 
    # ── Bootstrap ─────────────────────────────────────────────────────
    bridge = MT5Bridge()
    try:
        bridge.connect()
    except Exception as exc:
        message = f"MT5 initialization failed: {exc}"
        log(message, level="ERROR")
        _notify(notifier, message)
        raise
 
    strategy = load_strategy(strategy_name)
    datalogger = DataLogger(strategy_id=strategy.strategy_id, symbol=_config.symbol)
    position_manager = PositionManager(bridge, datalogger=datalogger)
 
    log(f"Loaded strategy: {strategy.strategy_id}")
    _run_recovery(bridge, position_manager, strategy, notifier)
 
    history, tick = fetch_data(bridge, _config)
    if history is None:
        message = "Initial market data fetch failed"
        log(message, level="ERROR")
        _notify(notifier, message)
        raise RuntimeError(message)
 
    warmup_strategy(strategy, history)
 
    # ── Loop state ────────────────────────────────────────────────────
    tick_counter = 0
    ticks_since_checkpoint = 0
    last_entry_bar_time = None
    current_bar_time = history["timestamp"][-1]
    last_fetch_time = time.time()
    loop_start = time.time()
    had_position = position_manager.has_open_position(_config.symbol, strategy.strategy_id)
 
    try:
        while not _should_exit:
            tick_counter += 1
            ticks_since_checkpoint += 1
            iteration_start = time.time()
 
            # ── Periodic checkpoint ───────────────────────────────────
            if ticks_since_checkpoint >= _config.checkpoint_interval:
                _save_checkpoint(position_manager, strategy)
                ticks_since_checkpoint = 0
 
            # ── Market data refresh ───────────────────────────────────
            if time.time() - last_fetch_time > _config.rate_fetch_interval:
                history, tick = fetch_data(bridge, _config)
                if history is None or tick is None:
                    log("Failed to fetch market data, retrying...", level="WARNING")
                    time.sleep(_config.tick_sleep)
                    continue
                current_bar_time = history["timestamp"][-1]
                last_fetch_time = time.time()
                if tick_counter % 100 == 0:
                    log(
                        f"[TICK {tick_counter}] Bar: {current_bar_time}, "
                        f"Bid: {tick.bid:.5f}, Ask: {tick.ask:.5f}",
                        level="INFO",
                    )
            else:
                tick = bridge.get_tick(_config.symbol)
                if tick is None:
                    log(f"[TICK {tick_counter}] Failed to fetch tick data", level="ERROR")
                    time.sleep(_config.tick_sleep)
                    continue
                if tick_counter % 100 == 0:
                    log(
                        f"[TICK {tick_counter}] Bid: {tick.bid:.5f}, Ask: {tick.ask:.5f}",
                        level="INFO",
                    )
 
            if history is None:
                log("[DATA ERROR] history is None, skipping iteration", level="ERROR")
                time.sleep(_config.tick_sleep)
                continue
 
            # ── Exit check ────────────────────────────────────────────
            current_state = build_market_state(history, tick, _config, use_previous=False)
            position_manager.handle_exit(strategy, current_state)
 
            current_has_position = position_manager.has_open_position(
                _config.symbol, strategy.strategy_id
            )
            if had_position and not current_has_position:
                log("[POSITION CLOSED] Blocking re-entry for current bar.", level="INFO")
                last_entry_bar_time = current_bar_time
 
            had_position = current_has_position
 
            # ── Entry attempt ─────────────────────────────────────────
            setup_state = build_market_state(history, tick, _config, use_previous=True)
            spread = bridge.get_spread(_config.symbol)
 
            executed, last_entry_bar_time = try_entry(
                bridge, position_manager, strategy,
                setup_state, history, spread,
                current_bar_time, last_entry_bar_time,
                datalogger, _config,
            )
 
            if executed:
                had_position = True
                log(f"Signal executed in {time.time() - iteration_start:.3f}s")
 
            time.sleep(_config.tick_sleep)
 
    except KeyboardInterrupt:
        log("Stopped by user", level="INFO")
    except Exception as exc:
        message = f"Unhandled exception in forward loop: {exc}"
        log(message, level="ERROR")
        _notify(notifier, message)
        traceback.print_exc()
        raise
    finally:
        log("Graceful shutdown: saving state and closing resources", level="INFO")
        _save_checkpoint(position_manager, strategy)
        datalogger.close()
        bridge.shutdown()
        elapsed = time.time() - loop_start
        log(
            f"Stopped. Processed {tick_counter} ticks in {elapsed:.1f}s "
            f"({tick_counter / elapsed:.1f} ticks/sec)",
            level="INFO",
        )
 
 
# ── Restart wrapper ───────────────────────────────────────────────────────────
 
def run_forward(strategy_name: str = "bb_squeeze") -> None:

    notifier = LineNotifier()
    attempt = 0
 
    while _config.max_restart_attempts < 0 or attempt < _config.max_restart_attempts:
        attempt += 1
        try:
            main_loop(strategy_name, notifier)
            break  # Clean exit — don't restart
        except KeyboardInterrupt:
            log("Forward runner stopped by user", level="INFO")
            break
        except Exception as exc:
            message = (
                f"Forward runner crashed on attempt {attempt}: {exc}. "
                f"Restarting in {_config.restart_delay}s."
            )
            log(message, level="ERROR")
            _notify(notifier, message)
            traceback.print_exc()
 
            if _config.max_restart_attempts >= 0 and attempt >= _config.max_restart_attempts:
                log("Reached max restart attempts, exiting", level="ERROR")
                break
 
            time.sleep(_config.restart_delay)
 
    log("Forward runner exiting", level="INFO")
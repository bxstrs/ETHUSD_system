import time
from src.strategies.strategy_loader import load_strategy
from src.core.types import MarketState
import MetaTrader5 as mt5

from src.execution.mt5_bridge import MT5Bridge
from src.execution.converter import convert_position_to_trade

bridge = MT5Bridge()
bridge.connect()

strategy = load_strategy("bb_squeeze")  # or directly: strategy = BBSqueezeStrategy(config)

symbol = "ETHUSD#"
timeframe = mt5.TIMEFRAME_M1
str_timeframe = "1m"

last_bar_time = None

while True:
    print("[LOOP START]")
    history = bridge.get_rates(symbol, timeframe, 200)
    tick = bridge.get_tick(symbol)

    if history is None or tick is None:
        print("Failed to fetch market data")
        time.sleep(5)
        continue

    current_bar_time = history["timestamp"][-1]

    # prevent duplicate execution per candle
    if current_bar_time == last_bar_time:
        print("[WAIT] same candle...")
        time.sleep(5)
        continue

    last_bar_time = current_bar_time

    print(f"[BAR CHECK] current={current_bar_time}, last={last_bar_time}")

    last_idx = -2  # use CLOSED candle, not forming one

    market_state = MarketState(
        symbol=symbol,
        timestamp=history["timestamp"][last_idx],
        interval=str_timeframe,

        open=history["open"][last_idx],
        high=history["high"][last_idx],
        low=history["low"][last_idx],
        close=history["close"][last_idx],

        bid=tick.bid,
        ask=tick.ask
    )

    spread = bridge.get_spread(symbol)

    signal = strategy.generate_signal(
        market_state=market_state,
        history=history,
        spread=spread
    )

    if signal:
        direction = "BUY" if signal.direction.name == "LONG" else "SELL"
        print(f"[SIGNAL] {signal.direction} at {signal.entry_price}")
        bridge.send_order(symbol, direction, volume=0.1)

    # exits
    positions = bridge.get_positions(symbol)

    for pos in positions or []:
        trade = convert_position_to_trade(pos)  # YOU implement this

        if strategy.check_exit(trade, market_state, history["close"]):
            bridge.close_position(pos)

    time.sleep(2)
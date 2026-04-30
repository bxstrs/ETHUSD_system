'''src/strategies/bb_squeeze/signal.py'''
from typing import Optional

from src.core.types import Signal, Direction, MarketState
from src.strategies.bb_squeeze.config import BBSqueezeConfig
from src.strategies.base import Strategy
from src.indicators.incremental.volatility_live import (
    IncrementalVolatility,
    BandwidthMACalculator
)

from src.utils.logger import log
from src.utils.data_logger import DataLogger
datalogger = DataLogger()

class BBSqueeze(Strategy):
    def __init__(self,config: BBSqueezeConfig):
        super().__init__(config)

        # adaptive state
        self._last_trade_was_loss = False
        self._current_bar_time = None       # new candle log
        self._tracked_setup_bar = None      # setup bar (history[-2]) being monitored
        self._entry_window_bar = None       # current_bar_time when this setup first appeared

        self.indicators = IncrementalVolatility(
            bb_period=config.bb_period,
            bb_dev=config.bb_dev,
            atr_period=config.atr_period,
        )

        self.bandwidth_ma = BandwidthMACalculator(
            bw_ma_period=config.bw_ma_period
        )

    def on_new_bar(self, history: dict):  
        closes = history["close"]
        highs = history["high"]
        lows = history["low"]

        if len(closes) < 3:
            return

        close = closes[-1]
        high = highs[-1]
        low = lows[-1]
        prev_close = closes[-2]     # TR calculation

        self.indicators.update(close, high, low, prev_close)
        bandwidth = self.indicators.get_bandwidth()
        self.bandwidth_ma.update(bandwidth)


    # -----------------------------
    # Entry logic
    # -----------------------------
    def generate_signal(
        self,
        market_state: MarketState,
        history: dict,
        spread: float,
    ) -> Optional[Signal]:

        current_bar_time = history["timestamp"][-1]
        setup_bar_time = history["timestamp"][-2]

        if self._current_bar_time != current_bar_time:

            self.on_new_bar(history)
            self._current_bar_time = current_bar_time 

            log( f"[NEW BAR] ts={current_bar_time}, prev={self._current_bar_time}")        
        
        if not (self.indicators.is_ready() and self.bandwidth_ma.is_ready()):
            log(f"Indicators status: {self.indicators.is_ready()}, bw_ma: {self.bandwidth_ma.is_ready()}")

            return None 
        
        if spread > self.config.max_spread:
            log(f"[FILTERED] spread too high: {spread}")

            return None
        
        if self._tracked_setup_bar != setup_bar_time:
            self._tracked_setup_bar = setup_bar_time
            self._entry_window_bar = current_bar_time

        if current_bar_time != self._entry_window_bar:
            log(f"[FILTERED] Setup expired — setup={setup_bar_time}, "f"window={self._entry_window_bar}, now={current_bar_time}",)
            return None
        
        if len(history["timestamp"]) >= 3:
            bar_interval = history["timestamp"][-2] - history["timestamp"][-3]
            actual_gap   = history["timestamp"][-1] - history["timestamp"][-2]
            if bar_interval > 0 and actual_gap > bar_interval * 1.5:
                log(
                    f"[FILTERED] Data gap detected — "
                    f"expected ~{bar_interval}s, got {actual_gap}s",
                    level="WARNING"
                )
                return None
 
        
        # ===== USE INCREMENTAL VALUES =====
        prev_upper, prev_lower, _ = self.indicators.get_previous_bollinger_bands()
        atr_value = self.indicators.get_atr()
        bandwidth = self.indicators.get_bandwidth()
        bandwidth_ma = self.bandwidth_ma.get_bandwidth_ma()

        # evaluation indicator status
        if prev_upper is None or prev_lower is None or atr_value == 0 or bandwidth_ma == 0:
            return None

        # bandwidth filter
        if bandwidth >= self.config.constant * bandwidth_ma:
            datalogger.log_signal(
                ts=market_state.timestamp,
                bar_time=current_bar_time,
                bw=bandwidth,
                bw_ma=bandwidth_ma,
                spread=spread,
                filter="bandwidth",
                decision="REJECT"
            )
            return None

        closes = history["close"]
        highs = history["high"]
        lows = history["low"]
        opens = history["open"]

        prev_open = opens[-2]
        prev_close = closes[-2]
        prev_high = highs[-2]
        prev_low = lows[-2]

        # ── Adaptive filter (tighten after a loss) ───────────────────
        if self._last_trade_was_loss:
            if abs(prev_close - prev_open) <= self.config.adaptive_constant * atr_value:
                return None

        # ── Candle validity ──────────────────────────────────────────
        # Reject full-range candles that cross both bands (indecisive)
        valid_candle = not (
            (prev_open > prev_upper and prev_close < prev_upper)
            or (prev_open < prev_lower and prev_close > prev_lower)
        )

        # -----------------------------
        # BUY
        # -----------------------------
        if  prev_close > prev_upper and valid_candle:
            if market_state.ask and market_state.ask > prev_high + 0.1 * atr_value + spread:
                datalogger.log_signal(
                    ts=market_state.timestamp,
                    bar_time=current_bar_time,
                    bw=bandwidth,
                    bw_ma=bandwidth_ma,
                    spread=spread,
                    filter="PASS",
                    decision="BUY"
                )
                return Signal(
                    signal_id=f"{market_state.timestamp}_BUY",
                    symbol=market_state.symbol,
                    timestamp=market_state.timestamp,
                    direction=Direction.LONG,
                    strategy_id=self.strategy_id,
                    entry_price=market_state.ask,
                    notes="BB squeeze breakout BUY",
                )

        # -----------------------------
        # SELL
        # -----------------------------
        if prev_close < prev_lower and valid_candle:
            if market_state.bid and market_state.bid < prev_low - 0.1 * atr_value - spread:
                datalogger.log_signal(
                    ts=market_state.timestamp,
                    bar_time=current_bar_time,
                    bw=bandwidth,
                    bw_ma=bandwidth_ma,
                    spread=spread,
                    filter="PASS",
                    decision="SELL"
                )
                return Signal(
                    signal_id=f"{market_state.timestamp}_SELL",
                    symbol=market_state.symbol,
                    timestamp=market_state.timestamp,
                    direction=Direction.SHORT,
                    strategy_id=self.strategy_id,
                    entry_price=market_state.bid,
                    notes="BB squeeze breakout SELL",
                )

        return None

    # -----------------------------
    # Exit logic (returns True/False)
    # -----------------------------
    def check_exit(self, trade, market_state) -> bool:
        upper, lower, _ = self.indicators.get_bollinger_bands()

        if market_state.bid and market_state.ask:
            mid_price = (market_state.bid + market_state.ask) / 2

        if upper is None or lower is None:
            return False

        if trade.direction == Direction.LONG:
            # exit if price returns inside / below lower band
            if mid_price <= lower:
                return True

        elif trade.direction == Direction.SHORT:
            # exit if price returns inside / above upper band
            if mid_price >= upper:
                return True

        return False

    # -----------------------------
    # Update state
    # -----------------------------
    def update_trade_result(self, trade):
        if trade.net_pnl is None:
            return
        self._last_trade_was_loss = trade.net_pnl < 0
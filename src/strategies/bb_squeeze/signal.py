import numpy as np
from typing import Optional

from src.core.types import Signal, Direction, MarketState
from src.strategies.bb_squeeze.config import BBSqueezeConfig
from src.strategies.base import Strategy
from src.indicators.volatility import BollingerBands, ATR

class BBSqueezeStrategy(Strategy):
    def __init__(self,config: BBSqueezeConfig):
        self.config = config
        self.strategy_id = self.__class__.__name__

        # adaptive state
        self.last_trade_was_loss = False
        self.last_close_time = None

    # -----------------------------
    # Derived indicators
    # -----------------------------
    def bandwidth(self, closes):
        upper, lower, middle = BollingerBands(
            closes,
            self.config.bb_period,
            self.config.bb_dev
        )
        if middle == 0:
            return 0
        return (upper - lower) / middle

    def bandwidth_ma(self, closes):
        values = []
        for i in range(self.config.bw_ma_period):
            window = closes[: -(i)] if i != 0 else closes
            if len(window) < self.config.bb_period:
                break
            values.append(self.bandwidth(window))
        return np.mean(values) if values else 0


    # -----------------------------
    # Entry logic
    # -----------------------------
    def generate_signal(
        self,
        market_state: MarketState,
        history: dict,
        spread: float,
    ) -> Optional[Signal]:

        closes = history["close"]
        highs = history["high"]
        lows = history["low"]
        opens = history["open"]
        timestamps = history["timestamp"]

        if len(closes) < max(self.config.bb_period, self.config.bw_ma_period + self.config.bb_period):
            return None

        # prevent same bar re-entry
        if self.last_close_time == market_state.timestamp:
            return None

        if spread > self.config.max_spread:
            return None

        # previous candle
        open1 = opens[-2]
        close1 = closes[-2]
        high1 = highs[-2]
        low1 = lows[-2]

        # BB
        upper1, lower1, _ = BollingerBands(
            closes[:-1],
            self.config.bb_period,
            self.config.bb_dev
        )

        # bandwidth filter
        bw1 = self.bandwidth(closes[:-1])
        bw_ma1 = self.bandwidth_ma(closes[:-1])

        if bw1 >= self.config.constant * bw_ma1:
            print("[FILTER] bandwidth condition failed")
            return None

        # ATR
        atr_value = ATR(highs, lows, closes)

        # adaptive filter (only after loss)
        if self.last_trade_was_loss:
            if abs(close1 - open1) <= self.config.adaptive_constant * atr_value:
                return None

        # invalid candle
        valid_candle = not (
            (open1 > upper1 and close1 < lower1)
            or (open1 < lower1 and close1 > upper1)
        )

        # -----------------------------
        # BUY
        # -----------------------------
        if close1 > upper1 and valid_candle:
            if market_state.ask and market_state.ask > high1 + 0.1 * atr_value:
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
        if close1 < lower1 and valid_candle:
            if market_state.bid and market_state.bid < low1 - 0.1 * atr_value:
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
    def check_exit(self, trade, market_state, closes):
        upper, lower, _ = BollingerBands(
            closes,
            self.config.bb_period,
            self.config.bb_dev
        )

        if trade.direction == Direction.LONG:
            if market_state.bid <= lower:
                return True

        if trade.direction == Direction.SHORT:
            if market_state.ask >= upper:
                return True

        return False

    # -----------------------------
    # Update state
    # -----------------------------
    def update_trade_result(self, trade):
        self.last_close_time = trade.exit_time

        if trade.net_pnl is not None and trade.net_pnl < 0:
            self.last_trade_was_loss = True
        else:
            self.last_trade_was_loss = False
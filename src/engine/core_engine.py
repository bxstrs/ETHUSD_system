from src.core.types import MarketState
from src.utils.logger import log


class Engine:
    def __init__(self, strategy, position_manager, execution_handler, symbol, timeframe):
        self.strategy = strategy
        self.position_manager = position_manager
        self.execution = execution_handler

        self.symbol = symbol
        self.timeframe = timeframe

        self.last_entry_bar_time = None

    # -----------------------------
    # Build Market State
    # -----------------------------
    def build_market_state(self, history, tick, use_previous=False):
        idx = -2 if use_previous else -1

        return MarketState(
            symbol=self.symbol,
            interval=self.timeframe,
            timestamp=history["timestamp"][idx],
            open=history["open"][idx],
            high=history["high"][idx],
            low=history["low"][idx],
            close=history["close"][idx],
            bid=tick.bid,
            ask=tick.ask
        )

    # -----------------------------
    # Process ONE step
    # -----------------------------
    def process(self, history, tick, spread, current_bar_time):
        """
        This is the ONLY method forward/backtest should call.
        """

        # =========================
        # EXIT LOGIC (current candle)
        # =========================
        current_state = self.build_market_state(history, tick, use_previous=False)

        self._handle_exit(current_state, history)

        # =========================
        # ENTRY LOGIC (previous candle)
        # =========================
        previous_state = self.build_market_state(history, tick, use_previous=True)

        self._handle_entry(previous_state, history, spread, current_bar_time)

    # -----------------------------
    # EXIT
    # -----------------------------
    def _handle_exit(self, market_state, history):
        trades = self.position_manager.get_strategy_positions(
            self.symbol,
            self.strategy.strategy_id
        )

        for pos, trade in trades:
            if self.strategy.check_exit(trade, market_state, history):

                log(
                    f"[EXIT SIGNAL] {trade.direction} at "
                    f"{market_state.bid if trade.direction.name == 'LONG' else market_state.ask}",
                    level="SIGNAL"
                )

                self.execution.close_position(pos)

                trade.exit_price = pos.price_current
                trade.exit_time = market_state.timestamp
                trade.net_pnl = pos.profit

                self.strategy.update_trade_result(trade)

    # -----------------------------
    # ENTRY
    # -----------------------------
    def _handle_entry(self, market_state, history, spread, current_bar_time):

        # prevent same-bar entry
        if self.last_entry_bar_time == current_bar_time:
            return

        # prevent duplicate positions
        if self.position_manager.has_open_position(
            self.symbol,
            self.strategy.strategy_id
        ):
            return

        signal = self.strategy.generate_signal(
            market_state=market_state,
            history=history,
            spread=spread
        )

        if not signal:
            return

        direction = "BUY" if signal.direction.name == "LONG" else "SELL"

        log(
            f"[ENTRY SIGNAL] {signal.direction} at {signal.entry_price}: {signal.notes}",
            level="SIGNAL"
        )

        result = self.execution.send_order(
            symbol=self.symbol,
            direction=direction,
            volume=0.1
        )

        if result and result.retcode:
            self.last_entry_bar_time = current_bar_time
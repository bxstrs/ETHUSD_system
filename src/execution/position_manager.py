'''src/execution/position_manager.py'''
from typing import List, Tuple

from src.execution.converter import convert_position_to_trade   
from src.core.types import Trade
from src.utils.logger import log

MAX_CONSECUTIVE_LOSSES = 5
MAX_DRAWDOWN = 0.2  # 20% drawdown

class PositionManager:
    def __init__(self, bridge):
        self.bridge = bridge

        # Risk tracking state
        self._consecutive_losses: int = 0
        self._peak_balance: float = 0.0
        self._trading_halted: bool = False

    # ------------------------------------------------------------------
    # Position Queries
    # ------------------------------------------------------------------

    def get_strategy_positions(self, symbol: str, strategy_id: str) -> List[Tuple]:
        positions = self.bridge.get_positions(symbol)
        if not positions:
            return []

        result = []
        for pos in positions:
            trade = convert_position_to_trade(pos)
            if trade.strategy_id == strategy_id:
                result.append((pos, trade))
        return result

    def has_open_position(self, symbol: str, strategy_id: str) -> bool:
        return len(self.get_strategy_positions(symbol, strategy_id)) > 0
    
    # ------------------------------------------------------------------
    # Risk Guards
    # ------------------------------------------------------------------
 
    def can_trade(self) -> bool:
        """triggered if risk limits have been breached."""
        if self._trading_halted:
            log(
                "[RISK] Trading halted — risk limit reached. Restart to resume.",
                level="WARNING",
            )
        return not self._trading_halted
    
    def _update_risk(self, trade: Trade) -> None:
        """Update risk state after a trade closes."""
        pnl = trade.net_pnl or 0.0
 
        if pnl < 0:
            self._consecutive_losses += 1
            log(
                f"[RISK] Consecutive losses: {self._consecutive_losses}/{MAX_CONSECUTIVE_LOSSES}",
                level="WARNING",
            )
            if self._consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                self._trading_halted = True
                log(
                    f"[RISK] Max consecutive losses ({MAX_CONSECUTIVE_LOSSES}) reached. "
                    "Halting trading.",
                    level="WARNING",
                )
        else:
            self._consecutive_losses = 0 # reset on win
 
    # ------------------------------------------------------------------
    # Exit Handler
    # ------------------------------------------------------------------

    def handle_exit(self, strategy, market_state, history) -> None:
        trades = self.get_strategy_positions(
            market_state.symbol,
            strategy.strategy_id
        )

        for pos, trade in trades:
            if strategy.check_exit(trade, market_state, history["close"]):
                exit_price = (
                    market_state.bid
                    if trade.direction.name == "LONG"
                    else market_state.ask
                )
                log(f"[EXIT SIGNAL] {trade.direction} at {exit_price}", level="SIGNAL")
                self.bridge.close_position(pos)

                trade.exit_price = pos.price_current
                trade.exit_time = market_state.timestamp
                trade.net_pnl = pos.profit

                self._update_risk(trade)
                strategy.update_trade_result(trade)
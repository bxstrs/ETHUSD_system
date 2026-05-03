'''src/execution/position_manager.py'''
from typing import List, Tuple, Dict, Optional
from datetime import datetime

import MetaTrader5 as mt5
from src.execution.converter import mt5_position_to_trade_result
from src.core.types import TradeResult, Direction
from src.utils.logger import log
from src.utils.data_logger import DataLogger
from src.config.loader import load_yaml


class PositionManager:
    def __init__(self, bridge, datalogger: Optional[DataLogger] = None):
        self.bridge = bridge
        self.datalogger = datalogger or DataLogger()

        # Load risk config
        risk_config = load_yaml("risk.yaml")
        self.enable_consecutive_loss_limit = risk_config.get("enable_consecutive_loss_limit", False)
        self.max_consecutive_losses = risk_config.get("max_consecutive_losses", 5)
        self.enable_drawdown_limit = risk_config.get("enable_drawdown_limit", False)
        self.max_drawdown = risk_config.get("max_drawdown", 0.2)

        # Risk tracking state
        self._consecutive_losses: int = 0
        self._peak_balance: float = 0.0
        self._trading_halted: bool = False

        # Position metadata: ticket → {setup_id, execution_id, trade, mae, mfe}
        self._position_metadata: Dict[int, Dict] = {}

    # ------------------------------------------------------------------
    # Position Queries
    # ------------------------------------------------------------------

    def get_strategy_positions(self, symbol: str, strategy_id: str) -> List[Tuple]:
        """Return list of (position, trade_result) tuples for strategy."""
        positions = self.bridge.get_positions(symbol)
        if not positions:
            return []

        result = []
        for pos in positions:
            match = pos.comment == str(strategy_id)
            log(
                f"[POSITION] ticket={pos.ticket} | "
                f"raw_comment='{pos.comment}' | "
                f"expected='{strategy_id}' | "
                f"exact_match={match}",
                level="DEBUG"
            )
            if match:
                # Retrieve metadata if exists, use placeholders if new position
                meta = self._position_metadata.get(pos.ticket, {})
                setup_id = meta.get('setup_id', f'setup_{pos.ticket}')
                execution_id = meta.get('execution_id', f'exec_{pos.ticket}')
                entry_slippage = meta.get('entry_slippage', 0.0)
                entry_latency_ms = meta.get('entry_latency_ms', 0.0)

                trade = mt5_position_to_trade_result(
                    pos,
                    setup_id,
                    execution_id,
                    entry_slippage,
                    entry_latency_ms
                )
                result.append((pos, trade))

        log(f"[POSITION] {len(result)} position(s) matched strategy_id='{strategy_id}'", level="DEBUG")
        return result

    def has_open_position(self, symbol: str, strategy_id: str) -> bool:
        """Check if strategy has any open positions."""
        return len(self.get_strategy_positions(symbol, strategy_id)) > 0

    # ------------------------------------------------------------------
    # Position Lifecycle Tracking
    # ------------------------------------------------------------------

    def track_position_entry(
        self,
        position_ticket: int,
        setup_id: str,
        execution_id: str,
        entry_slippage: float = 0.0,
        entry_latency_ms: float = 0.0
    ) -> None:
        """Register position metadata when order fills."""
        self._position_metadata[position_ticket] = {
            'setup_id': setup_id,
            'execution_id': execution_id,
            'entry_slippage': entry_slippage,
            'entry_latency_ms': entry_latency_ms,
            'entry_price': None,
            'mae': 0.0,
            'mfe': 0.0,
        }
        log(f"[TRACKED] Position ticket={position_ticket} setup={setup_id}", level="DEBUG")

    # ------------------------------------------------------------------
    # Risk Guards
    # ------------------------------------------------------------------

    def can_trade(self) -> bool:
        """Return False if risk limits breached."""
        if self._trading_halted:
            log(
                "[RISK] Trading halted — risk limit reached. Restart to resume.",
                level="WARNING",
            )
        return not self._trading_halted

    def _update_risk(self, trade_result: TradeResult) -> None:
        """Update risk state after trade closes."""
        pnl = trade_result.net_pnl or 0.0

        if pnl < 0:
            self._consecutive_losses += 1
            log(
                f"[RISK] Consecutive losses: {self._consecutive_losses}/{self.max_consecutive_losses}",
                level="WARNING",
            )
            if self.enable_consecutive_loss_limit and self._consecutive_losses >= self.max_consecutive_losses:
                self._trading_halted = True
                log(
                    f"[RISK] Max consecutive losses ({self.max_consecutive_losses}) reached. "
                    "Halting trading.",
                    level="WARNING",
                )
        else:
            self._consecutive_losses = 0

    # ------------------------------------------------------------------
    # MAE/MFE Tracking
    # ------------------------------------------------------------------

    def _update_mae_mfe(self, pos, trade: TradeResult) -> None:
        """Update max adverse/favorable excursion for open position."""
        if pos.ticket not in self._position_metadata:
            return

        meta = self._position_metadata[pos.ticket]
        entry_price = trade.entry_price

        if trade.direction == Direction.LONG:
            # For longs: MAE = low from entry, MFE = high from entry
            mid_price = (pos.bid + pos.ask) / 2 if hasattr(pos, 'bid') else pos.price_current

            adverse = entry_price - mid_price  # Drawdown from entry
            favorable = mid_price - entry_price  # Profit from entry

            meta['mae'] = max(meta.get('mae', 0), adverse)
            meta['mfe'] = max(meta.get('mfe', 0), favorable)

        elif trade.direction == Direction.SHORT:
            # For shorts: MAE = high from entry, MFE = low from entry
            mid_price = (pos.bid + pos.ask) / 2 if hasattr(pos, 'bid') else pos.price_current

            adverse = mid_price - entry_price  # Drawdown from entry
            favorable = entry_price - mid_price  # Profit from entry

            meta['mae'] = max(meta.get('mae', 0), adverse)
            meta['mfe'] = max(meta.get('mfe', 0), favorable)

    # ------------------------------------------------------------------
    # Exit Handler
    # ------------------------------------------------------------------

    def handle_exit(self, strategy, market_state) -> None:
        """Check and execute exits for open positions."""
        trades = self.get_strategy_positions(
            market_state.symbol,
            strategy.strategy_id
        )

        for pos, trade in trades:
            # Update MAE/MFE for this position (every tick)
            self._update_mae_mfe(pos, trade)

            if strategy.check_exit(trade, market_state):
                exit_price = market_state.bid
                log(f"[EXIT SIGNAL] {trade.direction} at {exit_price}", level="SIGNAL")

                try:
                    result = self.bridge.close_position(pos)
                except Exception as e:
                    log(f"Error occurred while closing position: {e}", level="ERROR")
                    return

                actual_exit_price = result.price if result and result.retcode == mt5.TRADE_RETCODE_DONE else market_state.bid

                deal_ticket = result.deal
                deals = self.bridge.history_deals_get(ticket=deal_ticket)
                actual_pnl = deals[0].profit if deals and len(deals) > 0 else None

                # Populate final trade result
                trade.exit_price = actual_exit_price
                trade.exit_time = market_state.timestamp
                trade.exit_bid = market_state.bid
                trade.exit_ask = market_state.ask
                trade.net_pnl = actual_pnl
                trade.status = "CLOSED"
                trade.exit_reason = "bollinger_exit"

                # Calculate duration
                if trade.entry_time and trade.exit_time:
                    duration_seconds = (trade.exit_time - trade.entry_time).total_seconds()
                    trade.duration_minutes = duration_seconds / 60.0

                # Add MAE/MFE from tracking
                meta = self._position_metadata.get(pos.ticket, {})
                trade.max_adverse_excursion = meta.get('mae', 0.0)
                trade.max_favorable_excursion = meta.get('mfe', 0.0)

                # Log to data logger
                if self.datalogger:
                    self.datalogger.log_trade_result(trade)

                self._update_risk(trade)
                strategy.update_trade_result(trade)

                # Clean up metadata
                if pos.ticket in self._position_metadata:
                    del self._position_metadata[pos.ticket]
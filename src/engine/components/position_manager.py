'''src/domain/position_manager.py'''
from typing import List, Tuple, Dict
from datetime import datetime

from src.domain.enums import Direction
from src.domain.trading import TradeResult
from src.infrastructure.logger.logger import log
from src.infrastructure.logger.data_logger import DataLogger
from src.config.loader import load_yaml


class PositionManager:
    def __init__(self, bridge, datalogger: DataLogger | None = None):
        
        self.bridge = bridge
        self.datalogger = datalogger or DataLogger()
        
        risk_config = load_yaml("risk.yaml")

        self._position_metadata: Dict[Tuple[int, int], Dict] = {}
        self._failed_closes_queqe: List[Tuple] = []
        
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
                key = self._get_position_key(pos)
                meta = self._position_metadata.get(key, {})
                setup_id = meta.get('setup_id')
                execution_id = meta.get('execution_id')
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
    
    def load_metadata(self, metadata: Dict[Tuple[int, int], Dict]) -> None:
        """Restore metadata from checkpoint."""
        self._position_metadata = {
            k: v for k, v in metadata.items()
        }
        log(f"[RECOVERY] Restored metadata for {len(self._position_metadata)} positions", level="INFO")

    def export_metadata(self):
        return dict(self._position_metadata)

    def remove_metadata(self, ticket: int):
        keys_to_remove = [
            key for key in self._position_metadata
            if key[0] == int(ticket)
        ]

        for key in keys_to_remove:
            del self._position_metadata[key]
            log(f"[META] Removed metadata {key}", level="DEBUG")

    def ensure_metadata(self, pos):
        key = self._get_position_key(pos)

        if key not in self._position_metadata:
            log(f"[META] Creating placeholder for {key}", level="WARNING")

            self._position_metadata[key] = {
                "setup_id": None,
                "execution_id": None,
                "entry_price": pos.price_open,
                "mae": 0.0,
                "mfe": 0.0,
                "recovered": True,
            }
    
    def reconcile(self, mt5_positions, checkpoint_data, position_storage):
        if not checkpoint_data:
            return

        result = position_storage.check_positions(mt5_positions, checkpoint_data)

        for ticket in result["closed"]:
            self.remove_metadata(ticket)

        mt5_map = {int(p.ticket): p for p in mt5_positions}

        for ticket in result["new"]:
            pos = mt5_map.get(ticket)
            if pos:
                self.ensure_metadata(pos)

    def has_open_position(self, symbol: str, strategy_id: str) -> bool:
        """Check if strategy has any open positions."""
        return len(self.get_strategy_positions(symbol, strategy_id)) > 0

    # ------------------------------------------------------------------
    # Position Lifecycle Tracking
    # ------------------------------------------------------------------

    def track_entry_position(
        self,
        position_ticket: int,
        open_time: datetime,
        setup_id: str,
        execution_id: str,
        entry_slippage: float = 0.0,
        entry_latency_ms: float = 0.0
    ) -> None:
        """Register position metadata when order fills."""
        metadata_key = self._build_position_key(position_ticket, open_time)

        self._position_metadata[metadata_key] = {
            'setup_id': setup_id,
            'execution_id': execution_id,
            'entry_slippage': entry_slippage,
            'entry_latency_ms': entry_latency_ms,
            'entry_price': None,
            'mae': 0.0,
            'mfe': 0.0,
        }

        log(f"[TRACKED] Position ticket={position_ticket} setup={setup_id}", level="DEBUG")
        
# ── Private helpers ───────────────────────────────────────────────────────────

    def _get_position_key(self, pos) -> Tuple[int, int]:
        """Create stable metadata key for MT5 positions."""
        return (int(pos.ticket), int(pos.time))


    def _build_position_key(self, ticket: int, open_time) -> Tuple[int, int]:
        """Create metadata key from raw values."""

        if hasattr(open_time, "timestamp"):
            open_time = int(open_time.timestamp())

        return (int(ticket), int(open_time))
    
    # ------------------------------------------------------------------
    # MAE/MFE Tracking
    # ------------------------------------------------------------------

    def _update_mae_mfe(self, pos, trade: TradeResult) -> None:
        """Update max adverse/favorable excursion for open position."""
        key = self._get_position_key(pos)

        if key not in self._position_metadata:
            return

        meta = self._position_metadata[key]
        entry_price = trade.entry_price or meta.get('entry_price')

        if entry_price is None:
            return

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

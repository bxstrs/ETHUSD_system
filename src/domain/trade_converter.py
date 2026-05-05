'''src/domain/trade_converter.py'''
import MetaTrader5 as mt5
from src.core.types import TradeResult, Direction
from datetime import datetime, timezone
from typing import Optional


def mt5_position_to_trade_result(
    pos,
    setup_id: str,
    execution_id: str,
    entry_slippage: float = 0.0,
    entry_latency_ms: float = 0.0
) -> TradeResult:
    """Convert MT5 position to TradeResult linked to signal setup and execution."""
    direction = (
        Direction.LONG
        if pos.type == mt5.POSITION_TYPE_BUY
        else Direction.SHORT
    )

    return TradeResult(
        trade_id=str(pos.ticket),
        setup_id=setup_id,
        execution_id=execution_id,
        symbol=pos.symbol,
        direction=direction,
        entry_price=pos.price_open,
        volume=pos.volume,
        entry_time=datetime.fromtimestamp(pos.time, tz=timezone.utc),
        entry_slippage=entry_slippage,
        entry_latency_ms=entry_latency_ms,
        exit_price=None,
        exit_time=None,
        exit_bid=None,
        exit_ask=None,
        net_pnl=pos.profit,
        status="OPEN"
    )


# Deprecated: Use mt5_position_to_trade_result instead
# def convert_position_to_trade(pos) -> Trade:
#     """[DEPRECATED] Use mt5_position_to_trade_result"""
#     pass
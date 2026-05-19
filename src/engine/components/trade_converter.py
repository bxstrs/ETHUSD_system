'''src/domain/trade_converter.py'''
import MetaTrader5 as mt5

from src.domain.enums import  Direction, TradeStatus
from src.domain.trading import TradeResult, Position
from datetime import datetime, timezone



def mt5_position_to_trade_result(
    pos: Position,
    setup_id: str | None,
    execution_id: str | None,
    entry_slippage: float = 0.0,
    entry_latency_ms: float = 0.0
) -> TradeResult:
    required_attrs = ['ticket', 'direction', 'symbol', 'price_open', 'volume', 'profit', 'time']

    for attr in required_attrs:
        if not hasattr(pos, attr):
            raise ValueError(f"Position missing required attribute: {attr}")

    return TradeResult(
        setup_id            = setup_id,
        execution_id        = execution_id,
        position_id         = pos.
        symbol              = pos.symbol,
        direction           = direction,
        entry_price         = pos.price_open,
        volume              = pos.volume,
        entry_time          = datetime.fromtimestamp(pos.time, tz=timezone.utc),
        entry_slippage      = entry_slippage,
        entry_latency_ms    = entry_latency_ms,
        exit_price          = None,
        exit_time           = None,
        exit_bid            = None,
        exit_ask            = None,
        net_pnl             = pos.profit,
        status              = TradeStatus.PENDING
    )
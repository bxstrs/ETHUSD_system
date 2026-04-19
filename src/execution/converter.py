import MetaTrader5 as mt5
from src.core.types import Trade, Direction


def convert_position_to_trade(pos) -> Trade:
    direction = (
        Direction.LONG
        if pos.type == mt5.POSITION_TYPE_BUY
        else Direction.SHORT
    )

    return Trade(
        trade_id=str(pos.ticket),
        symbol=pos.symbol,
        direction=direction,
        entry_price=pos.price_open,
        exit_price=None,
        volume=pos.volume,
        entry_time=pos.time,
        exit_time=None,
        net_pnl=pos.profit
    )
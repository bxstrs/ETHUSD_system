from src.domain.enums import TradeStatus
from src.domain.market_data import MarketSnapshot
from src.domain.trading import TradeResult, TradeExecution
from src.infrastructure.logger.data_logger import DataLogger
from src.infrastructure.logger.logger import log

def try_exit(
        bridge,
        position_manager, 
        risk_manager,
        strategy, 
        snapshot: MarketSnapshot,
        datalogger: DataLogger,
) -> bool:

    trades = position_manager.get_strategy_positions(snapshot.tick.symbol, strategy.strategy_id)

    for pos, trade in trades:

        position_manager.update_mae_mfe(pos, trade)
        exit_signal = strategy.check_exit(
            trade, 
            snapshot
        )

        if not exit_signal:
            return False
        
        exit_price = snapshot.tick.bid
        log(f"[EXIT] {trade.direction} at {exit_price}",level="INFO")
        
        result = bridge.close_position(pos)

        execution = TradeExecution(
            position_id         = result.position_id,
            setup_id            = None,
            fill_price          = result.price,
            fill_volume         = result.fill_volume,
            fill_time           = result.fill_time,
            slippage            = abs(result.price - exit_price),
            latency_ms          = result.latency_ms,
            status              = result.status,
        )
        datalogger.log_trade_execution(execution)

        deals   = bridge.history_deals_get(ticket=result.ticket)
        key     = position_manager._get_position_key(pos)
        meta    = position_manager._position_metadata.get(key, {})


        # ── Build and log TradeResult ──────────────────────────────────────
        trade_result = TradeResult (
            position_id             = result.position_id,
            symbol                  = result.symbol,
            volume                  = result.volume,
            exit_price              = result.fill_price,
            exit_time               = result.fill_time,
            exit_reason             = "bollinger_exit",
            exit_bid                = snapshot.tick.bid,
            exit_ask                = snapshot.tick.ask,
            total_fees              = deals[0].fee + deals[0].swap + deals[0].commission,
            net_pnl                 = deals[0].profit if deals and len(deals) > 0 else 0.0,
            duration_minutes        = (trade.exit_time - trade.entry_time).total_seconds() / 60.0,
            risk_reward_ratio       = None,
            max_adverse_excursion   = meta.get('mae', 0.0),
            max_favorable_excursion = meta.get('mfe', 0.0),
            is_recovered            = False,
            status                  = TradeStatus.CLOSED
        )
        datalogger.log_trade_result(trade_result)

        risk_manager.update(trade)
        strategy.update_trade_result(trade)

        # Clean up metadata
        if key in position_manager._position_metadata:
            del position_manager._position_metadata[key]

        return True
    return False
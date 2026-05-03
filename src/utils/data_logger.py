"""Unified trade journal with gzip compression. Scalable for multiple strategies/assets."""
import csv
import gzip
import os
from datetime import datetime
from collections import defaultdict


class DataLogger:
    """Unified trade journal with gzip compression. Scalable for multiple strategies/assets."""
    
    _instances = {}  # Singleton storage: {(strategy_id, symbol): instance}

    TRADE_HEADERS = [
        # TradeSetup: signal intent
        "setup_id","strategy_id", "symbol", "signal_timestamp",
        "direction", "trigger_price",
        "bb_upper", "bb_lower", "bb_middle", "bandwidth", "bandwidth_ma", "atr", "spread",
        "intended_entry_price", "intended_volume",
        "hour_of_day", "candle_open", "candle_high", "candle_low", "candle_close",
        "prev_trade_pnl", "adaptive_filter_active",
        # TradeExecution: order fill details
        "execution_id", "filled_entry_price", "filled_volume", "entry_time",
        "entry_slippage", "entry_latency_ms", "execution_status",
        # TradeResult: complete lifecycle
        "trade_id", "exit_price", "exit_time", "exit_reason",
        "exit_bid", "exit_ask", "gross_pnl", "fees", "net_pnl",
        "duration_minutes", "risk_reward_ratio",
        "max_adverse_excursion", "max_favorable_excursion", "trade_status",
    ]

    PORTFOLIO_HEADERS = [
        "timestamp", "strategy_id", "symbol",
        "total_trades", "wins", "losses", "consecutive_wins", "consecutive_losses",
        "max_drawdown", "current_drawdown", "profit_factor",
        "avg_win", "avg_loss", "payoff_ratio",
        "win_rate", "expected_payoff", "daily_pnl", "cumulative_pnl",
    ]

    def __init__(self, base_path="logs", strategy_id: str = "default", symbol: str = "UNKNOWN"):
        """Initialize logger with strategy/symbol-specific file for scalability."""
        os.makedirs(base_path, exist_ok=True)

        self.base_path = base_path
        self.strategy_id = strategy_id
        self.symbol = symbol

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        # Filename encodes strategy + symbol for easy filtering and multi-strategy runs
        trade_filename = f"trades_{symbol}_{strategy_id}_{ts}.csv.gz"
        portfolio_filename = f"portfolio_{symbol}_{strategy_id}_{ts}.csv.gz"

        self.trade_filepath = os.path.join(base_path, trade_filename)
        self.portfolio_filepath = os.path.join(base_path, portfolio_filename)

        # Open gzip-compressed files in text mode
        self.trade_file = gzip.open(self.trade_filepath, "wt", newline="", encoding="utf-8")
        self.portfolio_file = gzip.open(self.portfolio_filepath, "wt", newline="", encoding="utf-8")

        self.trade_writer = csv.DictWriter(self.trade_file, fieldnames=self.TRADE_HEADERS)
        self.portfolio_writer = csv.DictWriter(self.portfolio_file, fieldnames=self.PORTFOLIO_HEADERS)

        # Write headers
        self.trade_writer.writeheader()
        self.portfolio_writer.writeheader()

        # Row cache for partial updates (setup → execution → result)
        self._pending_rows: dict = defaultdict(dict)

    @classmethod
    def get_instance(cls, base_path="logs", strategy_id: str = "default", symbol: str = "UNKNOWN"):
        """
        Get or create singleton instance per (strategy_id, symbol) pair.
        
        This ensures only one DataLogger instance per strategy/symbol combination,
        preventing duplicate CSV files and writer instances.
        """
        key = (strategy_id, symbol)
        if key not in cls._instances:
            cls._instances[key] = cls(base_path, strategy_id, symbol)
        return cls._instances[key]

    def log_trade_setup(self, setup) -> None:
        """Log trade setup (signal intent). Row remains open for execution/result updates."""
        setup_id = setup.setup_id

        row = {
            "setup_id": setup_id,
            "strategy_id": setup.strategy_id,
            "symbol": setup.symbol,
            "signal_timestamp": setup.timestamp.isoformat() if setup.timestamp else None,
            "direction": setup.direction.value if hasattr(setup.direction, 'value') else setup.direction,
            "trigger_price": setup.trigger_price,
            "bb_upper": setup.bb_upper,
            "bb_lower": setup.bb_lower,
            "bb_middle": setup.bb_middle,
            "bandwidth": setup.bandwidth,
            "bandwidth_ma": setup.bandwidth_ma,
            "atr": setup.atr,
            "spread": setup.spread,
            "intended_entry_price": setup.intended_entry_price,
            "intended_volume": setup.intended_volume,
            "hour_of_day": setup.hour_of_day,
            "candle_open": setup.candle_open,
            "candle_high": setup.candle_high,
            "candle_low": setup.candle_low,
            "candle_close": setup.candle_close,
            "prev_trade_pnl": setup.prev_trade_pnl,
            "adaptive_filter_active": setup.adaptive_filter_active,
        }

        # Cache row, don't write yet (wait for execution + result)
        self._pending_rows[setup_id].update(row)

    def log_trade_execution(self, execution) -> None:
        """Log execution details. Row cache updated, still waiting for result."""
        setup_id = execution.setup_id

        row = {
            "execution_id": execution.execution_id,
            "filled_entry_price": execution.filled_entry_price,
            "filled_volume": execution.filled_volume,
            "entry_time": execution.filled_time.isoformat() if execution.filled_time else None,
            "entry_slippage": execution.slippage,
            "entry_latency_ms": execution.latency_ms,
            "execution_status": execution.status,
        }

        self._pending_rows[setup_id].update(row)

    def log_trade_result(self, result) -> None:
        """Log trade result (complete lifecycle). Write complete row to CSV."""
        setup_id = result.setup_id

        row = {
            "trade_id": result.trade_id,
            "exit_price": result.exit_price,
            "exit_time": result.exit_time.isoformat() if result.exit_time else None,
            "exit_reason": result.exit_reason,
            "exit_bid": result.exit_bid,
            "exit_ask": result.exit_ask,
            "gross_pnl": result.gross_pnl,
            "fees": result.fees,
            "net_pnl": result.net_pnl,
            "duration_minutes": result.duration_minutes,
            "risk_reward_ratio": result.risk_reward_ratio,
            "max_adverse_excursion": result.max_adverse_excursion,
            "max_favorable_excursion": result.max_favorable_excursion,
            "trade_status": result.status,
        }

        # Merge with cached setup/execution data
        complete_row = {**self._pending_rows.get(setup_id, {}), **row}

        # Write complete row
        self.trade_writer.writerow(complete_row)
        self.trade_file.flush()
        os.fsync(self.trade_file.fileno())

        # Clean up cache
        if setup_id in self._pending_rows:
            del self._pending_rows[setup_id]

    def log_portfolio_stats(self, stats) -> None:
        """Log portfolio-level metrics for ML regime detection."""
        row = {
            "timestamp": stats.timestamp.isoformat() if stats.timestamp else None,
            "strategy_id": stats.strategy_id,
            "symbol": stats.symbol,
            "total_trades": stats.total_trades,
            "wins": stats.wins,
            "losses": stats.losses,
            "consecutive_wins": stats.consecutive_wins,
            "consecutive_losses": stats.consecutive_losses,
            "max_drawdown": stats.max_drawdown,
            "current_drawdown": stats.current_drawdown,
            "profit_factor": stats.profit_factor,
            "avg_win": stats.avg_win,
            "avg_loss": stats.avg_loss,
            "payoff_ratio": stats.payoff_ratio,
            "win_rate": stats.win_rate,
            "expected_payoff": stats.expected_payoff,
            "daily_pnl": stats.daily_pnl,
            "cumulative_pnl": stats.cumulative_pnl,
        }

        self.portfolio_writer.writerow(row)
        self.portfolio_file.flush()
        os.fsync(self.portfolio_file.fileno())

    def close(self) -> None:
        """Close all files and flush remaining data to disk."""
        if self.trade_file:
            self.trade_file.flush()
            try:
                os.fsync(self.trade_file.fileno())
            except (OSError, ValueError):
                pass  # File might already be closed or invalid
            self.trade_file.close()
        
        if self.portfolio_file:
            self.portfolio_file.flush()
            try:
                os.fsync(self.portfolio_file.fileno())
            except (OSError, ValueError):
                pass  # File might already be closed or invalid
            self.portfolio_file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
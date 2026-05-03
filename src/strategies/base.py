'''src/strategies/base.py'''
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from src.core.types import Signal, MarketState, TradeExecution, TradeResult


class Strategy(ABC):
    def __init__(self, config: Any):
        self.config = config
        self.strategy_id = self.__class__.__name__
        self.magic_number = hash(self.strategy_id) % (10 ** 8)

    # -----------------------------
    # Entry
    # -----------------------------
    @abstractmethod
    def generate_signal(
        self,
        market_state: MarketState,
        history: Dict[str, list],
        spread: float,
    ) -> Optional[Signal]:
        """
        Return a Signal or None
        """
        pass

    # -----------------------------
    # Exit
    # -----------------------------
    @abstractmethod
    def check_exit(
        self,
        trade: TradeExecution,
        market_state: MarketState,
        closes: list,
    ) -> bool:
        """
        Return True if trade should be closed
        """
        pass

    # -----------------------------
    # State update (after trade closes)
    # -----------------------------
    def update_trade_result(self, trade: TradeResult) -> None:
        """
        Optional override
        """
        pass
from src.config.loader import load_yaml
from src.infrastructure.logger.logger import log
from src.domain.trading import TradeResult

risk_config = load_yaml("risk.yaml")

class RiskManager:

    def __init__ (self, config: dict = risk_config):

        self.enable_consecutive_loss_limit  = config.get("enable_consecutive_loss_limit", False)
        self.max_consecutive_losses         = config.get("max_consecutive_losses", 5)
        self.enable_drawdown_limit          = config.get("enable_drawdown_limit", False)
        self.max_drawdown                   = config.get("max_drawdown", 0.2)

        # Risk tracking state
        self._consecutive_losses: int   = 0
        self._trading_halted: bool      = False

    # ------------------------------------------------------------------
    # Risk Guards
    # ------------------------------------------------------------------

    def can_trade(self) -> bool:
        if self._trading_halted:
            log("[RISK] Trading halted — restart required", level="WARNING")
        return not self._trading_halted

    def update(self, trade_result: TradeResult) -> None:
        pnl = trade_result.net_pnl or 0.0

        if pnl < 0:
            self._consecutive_losses += 1
            log(f"[RISK] Loss streak: {self._consecutive_losses}", level="WARNING")

            if (
                self.enable_consecutive_loss_limit
                and self._consecutive_losses >= self.max_consecutive_losses
            ):
                self._trading_halted = True
                log("[RISK] Max losses reached → halt trading", level="ERROR")
        else:
            self._consecutive_losses = 0
"""Position sizing based on risk management rules."""
from src.config.loader import load_yaml
from src.utils.logger import log
from typing import Optional


class PositionSizer:
    """Calculate position size based on account balance and risk per trade."""

    def __init__(self):
        risk_config = load_yaml("risk.yaml")
        self.risk_per_trade = risk_config.get("risk_per_trade", 0.025)  # 2.5% default
        log(f"[POSITION_SIZER] Risk per trade: {self.risk_per_trade*100}%", level="INFO")

    def calculate_volume(self, account_balance: float, entry_price: float, stop_loss_price: float, base_volume: float = 0.1) -> float:

        if not account_balance or not entry_price or entry_price == stop_loss_price:
            log(f"[POSITION_SIZER] Invalid inputs, using base volume {base_volume}", level="WARNING")
            return base_volume
        
        # Calculation factors:
        # - risk_amount = account_balance * risk_per_trade
        risk_amount = account_balance * self.risk_per_trade
        price_distance = abs(entry_price - stop_loss_price)
        points_per_lot = 100  # 100 = standard scaling
        
        calculated_volume = risk_amount / (price_distance * points_per_lot)
        volume = max(0.01, min(10.0, calculated_volume)) # -> Clamp between 0.01 and 10 lots
        
        log(
            f"[POSITION_SIZER] Balance: ${account_balance:.2f}, Risk: ${risk_amount:.2f}, "
            f"Distance: ${price_distance:.2f}, Volume: {volume:.2f}",
            level="DEBUG"
        )
        
        return volume

    def calculate_volume_fixed(self, account_balance: float, risk_percent: Optional[float] = None) -> float:
        risk = risk_percent or self.risk_per_trade
        
        # Simplified: fixed scaling for ETHUSD
        volume = (account_balance * risk) / 1000
        
        return max(0.01, min(10.0, volume))

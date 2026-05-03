"""State persistence for crash recovery"""
import json
import os
from datetime import datetime
from src.utils.logger import log

class StateManager:
    def __init__(self, checkpoint_dir="checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)
    
    def save_positions(self, positions, strategy_id):
        """Save open positions to disk for recovery after crash"""
        try:
            checkpoint = {
                "timestamp": datetime.utcnow().isoformat(),
                "strategy_id": str(strategy_id),
                "positions": [
                    {
                        "ticket": int(pos.ticket),
                        "symbol": str(pos.symbol),
                        "type": int(pos.type),  # 0=BUY, 1=SELL
                        "volume": float(pos.volume),
                        "open_price": float(pos.price_open),
                        "magic": int(pos.magic),
                        "comment": str(pos.comment),
                        "open_time": int(pos.time),
                    } for pos in positions
                ]
            }
            
            path = f"{self.checkpoint_dir}/{strategy_id}_positions.json"
            with open(path, 'w') as f:
                json.dump(checkpoint, f, indent=2)
                # Force write to disk (critical for crash recovery)
                f.flush()
                os.fsync(f.fileno())
            
            log(f"[STATE] Saved {len(positions)} positions for {strategy_id}", level="DEBUG")
            return True
        except Exception as e:
            log(f"[ERROR] Failed to save positions: {e}", level="ERROR")
            return False
    
    def load_positions(self, strategy_id):
        """Load positions from last checkpoint"""
        try:
            path = f"{self.checkpoint_dir}/{strategy_id}_positions.json"
            if not os.path.exists(path):
                return None
            
            with open(path, 'r') as f:
                checkpoint = json.load(f)
            
            log(f"[STATE] Loaded checkpoint from {checkpoint['timestamp']}", level="INFO")
            return checkpoint
        except Exception as e:
            log(f"[ERROR] Failed to load checkpoint: {e}", level="ERROR")
            return None
    
    def reconcile_positions(self, bridge, symbol, mt5_positions, checkpoint_data):
        """
        Compare MT5 live positions with checkpoint.
        Returns list of recovered positions if checkpoint has positions not in MT5.
        """
        if not checkpoint_data or not checkpoint_data.get("positions"):
            return []
        
        live_tickets = {int(p.ticket) for p in mt5_positions}
        checkpoint_tickets = {p["ticket"] for p in checkpoint_data["positions"]}
        
        missing_tickets = checkpoint_tickets - live_tickets
        
        if missing_tickets:
            log(f"[RECOVERY] Found {len(missing_tickets)} positions in checkpoint but not in MT5", 
                level="WARNING")
            log(f"Missing tickets: {missing_tickets}", level="DEBUG")
            
            # Return positions that need to be monitored/recovered
            recovered = [
                p for p in checkpoint_data["positions"] 
                if p["ticket"] in missing_tickets
            ]
            return recovered
        
        return []
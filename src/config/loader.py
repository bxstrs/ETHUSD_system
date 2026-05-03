'''src/config/loader.py'''
import yaml
from pathlib import Path
from src.utils.logger import log


BASE_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs"


def load_yaml(relative_path: str) -> dict:
    path = BASE_CONFIG_PATH / relative_path

    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, "r") as f:
        config = yaml.safe_load(f)
    
    # Validate config is not empty
    if not config:
        raise ValueError(f"Config file is empty: {path}")
    
    return config


def validate_trading_config(config: dict) -> None:
    """Validate trading.yaml has required fields."""
    required_fields = ["symbol", "timeframe", "timeframe_value", "deviation", "base_volume"]
    missing = [f for f in required_fields if f not in config]
    
    if missing:
        raise ValueError(f"trading.yaml missing required fields: {missing}")
    
    # Validate types
    if not isinstance(config.get("symbol"), str):
        raise ValueError("symbol must be a string")
    if not isinstance(config.get("base_volume"), (int, float)):
        raise ValueError("base_volume must be a number")
    if config.get("base_volume", 0) <= 0:
        raise ValueError("base_volume must be > 0")
    
    log(f"[CONFIG] trading.yaml validated: symbol={config['symbol']}, volume={config['base_volume']}", level="DEBUG")


def validate_risk_config(config: dict) -> None:
    """Validate risk.yaml has required fields."""
    required_fields = ["risk_per_trade", "max_consecutive_losses", "max_drawdown"]
    missing = [f for f in required_fields if f not in config]
    
    if missing:
        raise ValueError(f"risk.yaml missing required fields: {missing}")
    
    # Validate types
    if not isinstance(config.get("risk_per_trade"), (int, float)):
        raise ValueError("risk_per_trade must be a number")
    if not (0 < config.get("risk_per_trade", 0) < 1):
        raise ValueError("risk_per_trade must be between 0 and 1")
    
    log(f"[CONFIG] risk.yaml validated: risk_per_trade={config['risk_per_trade']}", level="DEBUG")
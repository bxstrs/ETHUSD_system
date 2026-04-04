from src.strategies.bb_squeeze.signal import BBSqueezeStrategy
from src.strategies.bb_squeeze.config import BBSqueezeConfig


STRATEGY_REGISTRY = {
    "bb_squeeze": {
        "strategy_class": BBSqueezeStrategy,
        "config_class": BBSqueezeConfig,
        "config_path": "strategies/bb_squeeze.yaml",
    }
}
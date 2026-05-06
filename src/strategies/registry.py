'''src/strategies/registry.py'''
from src.strategies.bb_squeeze.signal import BBSqueeze
from src.strategies.bb_squeeze.config import BBSqueezeConfig


STRATEGY_REGISTRY = {
    "bb_squeeze": {
        "strategy_class": BBSqueeze,
        "config_class": BBSqueezeConfig,
        "config_path": "strategies/bb_squeeze.yaml",
    }
}
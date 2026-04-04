from src.config.loader import load_yaml
from src.strategies.registry import STRATEGY_REGISTRY


def load_strategy(name: str):
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Strategy '{name}' not found")

    entry = STRATEGY_REGISTRY[name]

    config_data = load_yaml(entry["config_path"])
    config = entry["config_class"](**config_data)

    strategy = entry["strategy_class"](config)

    return strategy
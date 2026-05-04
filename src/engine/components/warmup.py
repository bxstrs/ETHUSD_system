"""src/engine/components/warmup.py"""
from src.utils.logger import log
 
 
def warmup_strategy(strategy, history: dict) -> None:

    closes = history["close"]
    highs = history["high"]
    lows = history["low"]
    opens = history["open"]
    timestamps = history["timestamp"]
 
    log(f"Warming up strategy with {len(closes)} bars...", level="INFO")
 
    for i in range(1, len(closes)):
        sub_history = {
            "close": closes[: i + 1],
            "high": highs[: i + 1],
            "low": lows[: i + 1],
            "open": opens[: i + 1],
            "timestamp": timestamps[: i + 1],
        }
        if hasattr(strategy, "on_new_bar"):
            strategy.on_new_bar(sub_history)
 
    if timestamps:
        strategy._current_bar_time = timestamps[-1]
 
    log("Strategy warmup complete.", level="INFO")
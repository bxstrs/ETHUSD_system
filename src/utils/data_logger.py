# src/utils/data_logger.py
import csv
import os
from datetime import datetime

class DataLogger:
    def __init__(self, base_path="logs"):
        os.makedirs(base_path, exist_ok=True)

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        self.signal_file = open(f"{base_path}/signals_{ts}.csv", "w", newline="")
        self.trade_file = open(f"{base_path}/trades_{ts}.csv", "w", newline="")

        self.signal_writer = csv.writer(self.signal_file)
        self.trade_writer = csv.writer(self.trade_file)

        # headers
        self.signal_writer.writerow([
            "ts", "bar_time",
            "bw", "bw_ma",
            "spread",
            "filter", "decision"
        ])

        self.trade_writer.writerow([
            "ts", "type",
            "direction",
            "price",
            "pnl",
            "note"
        ])

    def log_signal(self, **kwargs):
        self.signal_writer.writerow([
            kwargs.get("ts"),
            kwargs.get("bar_time"),
            kwargs.get("bw"),
            kwargs.get("bw_ma"),
            kwargs.get("spread"),
            kwargs.get("filter"),
            kwargs.get("decision"),
        ])
        self.signal_file.flush()

    def log_trade(self, **kwargs):
        self.trade_writer.writerow([
            kwargs.get("ts"),
            kwargs.get("type"),
            kwargs.get("direction"),
            kwargs.get("price"),
            kwargs.get("pnl"),
            kwargs.get("note"),
        ])
        self.trade_file.flush()

    def close(self):
        self.signal_file.close()
        self.trade_file.close()
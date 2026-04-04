import os
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Generator #Implement later for streaming
from dotenv import load_dotenv

from src.core.types import MarketState
from src.data.base import DataProvider


load_dotenv()

class TwelveDataProvider(DataProvider):
    """Data provider for fetching market data from Twelve Data API."""
    BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TWELVEDATA_API_KEY")
        if not self.api_key:
            raise ValueError("Twelve Data API key is required")

    def fetch_historical_data(self, symbol: str, interval: str = "1day", days: int = 30) -> List[MarketState]: 
        #REMINDER: BB_squeeze use 4hr candles, so implementing later
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        params = {
            "symbol": symbol,
            "interval": interval,
            "start_date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
            "end_date": end_date.strftime("%Y-%m-%d %H:%M:%S"),
            "apikey": self.api_key,
            "format": "JSON"
        }
        
        response = requests.get(f"{self.BASE_URL}/time_series", params=params)
        response.raise_for_status()
        
        data = response.json()

        if data.get("status") == "error":
            raise ValueError(f"API error: {data.get('message', 'Unknown error')}")

        if "values" not in data or not data["values"]:
            raise ValueError(f"Unexpected response format: {data}")
        
        response_interval = data["meta"]["interval"]
        if interval != response_interval:
            print(f"[WARN] Requested interval '{interval}' != response '{response_interval}'")
        interval = response_interval  # Update interval based on response

        return self._normalize_and_validate(data["values"], symbol, interval)
    
    def _normalize_and_validate(self, raw_data: List[dict], symbol: str, interval: str) -> List[MarketState]:
        
        market_states = []
        
        for item in raw_data:
            # Normalize field names and types
            timestamp = datetime.strptime(
                item["datetime"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)

            market_state = MarketState(
                symbol=symbol,
                interval=interval,
                timestamp=timestamp,
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item.get("volume", 0.0))
            )
            # Validation happens in MarketState.__post_init__
            market_states.append(market_state)

        market_states.sort(key=lambda x: x.timestamp)
        
        # Deduplicate + Gap detection
        market_states = self._validate_batch(market_states, interval)
        
        # remove last potentially incomplete candle
        if market_states:
            now = datetime.now(timezone.utc)
            interval_sec = self._interval_to_seconds(interval)

            last = market_states[-1]
            if last.timestamp > now - timedelta(seconds=interval_sec):
                market_states = market_states[:-1]
        
        return market_states
    
    def _interval_to_seconds(self, interval: str) -> int:
        mapping = {
            "1min": 60,
            "5min": 300,
            "15min": 900,
            "30min": 1800,
            "1h": 3600,
            "4h": 14400,
            "1day": 86400,
        }
    
        if interval not in mapping:
            raise ValueError(f"Unsupported interval: {interval}")
        
        return mapping[interval]
    
    def _validate_batch(self, data: List[MarketState], interval: str) -> List[MarketState]:
        interval_sec = self._interval_to_seconds(interval)

        cleaned = []
        prev = None

        for curr in data: 
            if prev:
                if self._is_duplicate(prev, curr):
                    if cleaned:
                        cleaned[-1] = curr
                    else:
                        cleaned.append(curr)
                    prev = curr
                    continue

                is_gap, expected = self._is_gap(prev, curr, interval_sec)
                if is_gap:
                    print(f"[WARN] Gap: missing {expected} → {curr.timestamp}")

            cleaned.append(curr)
            prev = curr

        return cleaned
    
    def _is_gap(self, prev: MarketState, curr: MarketState, interval_sec: int) -> tuple[bool, datetime]:
        expected = prev.timestamp + timedelta(seconds=interval_sec)
        return curr.timestamp > expected, expected


    def _is_duplicate(self, prev: MarketState, curr: MarketState) -> bool:
        return prev.timestamp == curr.timestamp
    
    def stream_market_data(self, symbol: str, interval: str = "1min"):
        raise NotImplementedError("Streaming not implemented for TwelveDataProvider yet")
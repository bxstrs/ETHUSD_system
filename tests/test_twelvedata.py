from src.data.providers.twelvedata import TwelveDataProvider
from src.core.types import MarketState

def test_fetch_data():
    provider = TwelveDataProvider()
    data = provider.fetch_historical_data("USD/JPY", "1day", 5)

    assert len(data) > 0
    assert all(isinstance(x, MarketState) for x in data)

def test_marketstate_validity():
    provider = TwelveDataProvider()
    data = provider.fetch_historical_data("USD/JPY", "1day", 5)

    for candle in data:
        assert candle.high >= candle.low
        assert candle.open >= 0
        assert candle.close >= 0

def test_time_order():
    provider = TwelveDataProvider()
    data = provider.fetch_historical_data("USD/JPY", "1day", 5)

    timestamps = [c.timestamp for c in data]
    assert timestamps == sorted(timestamps)
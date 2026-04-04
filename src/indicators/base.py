from abc import ABC, abstractmethod


class Indicator(ABC):
    @abstractmethod
    def update(self, *args, **kwargs):
        """Update with one new data point (live mode)"""
        pass

    @abstractmethod
    def value(self):
        """Return current indicator value"""
        pass

    @abstractmethod
    def compute(self, *args, **kwargs):
        """Compute full series (batch mode)"""
        pass
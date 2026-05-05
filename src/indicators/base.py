'''src/indicators/base.py'''
from abc import ABC, abstractmethod


class Indicator(ABC):
    @abstractmethod
    def update(self, *args, **kwargs):
        """Update with one new data point (live mode)"""
        pass

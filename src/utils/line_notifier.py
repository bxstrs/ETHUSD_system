"""LINE Notify integration for critical alerts and manual review notifications."""
import os
import requests
from typing import Optional
from src.utils.logger import log


class LineNotifier:
    API_URL = "https://notify-api.line.me/api/notify"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("LINE_NOTIFY_TOKEN")
        self.enabled = bool(self.token)
        if self.enabled:
            log("LINE Notifications enabled", level="DEBUG")
        else:
            log("LINE Notify token not set; notifications disabled", level="DEBUG")

    def notify(self, message: str) -> bool:
        """Send a LINE Notify message if a token is configured."""
        if not self.enabled:
            return False

        headers = {
            "Authorization": f"Bearer {self.token}",
        }

        payload = {
            "message": message,
        }

        try:
            response = requests.post(self.API_URL, headers=headers, data=payload, timeout=10)
        except Exception as exc:
            log(f"LINE Notify request failed: {exc}", level="ERROR")
            return False

        if response.status_code != 200:
            log(
                f"LINE Notify returned {response.status_code}: {response.text}",
                level="ERROR",
            )
            return False

        return True

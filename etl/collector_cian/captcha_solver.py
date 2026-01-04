"""Anti-Captcha integration for Yandex SmartCaptcha."""
from __future__ import annotations

import os
import time
from typing import Optional

import requests

API_URL = "https://api.anti-captcha.com"
POLL_INTERVAL = 5
MAX_WAIT = 120


class CaptchaSolver:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("ANTICAPTCHA_KEY")
        if not self.api_key:
            raise RuntimeError("ANTICAPTCHA_KEY is not set")

    def solve(self, site_key: str, page_url: str) -> str:
        create_payload = {
            "clientKey": self.api_key,
            "task": {
                "type": "YandexSmartCaptchaTaskProxyless",
                "websiteURL": page_url,
                "sitekey": site_key,
            },
        }
        resp = requests.post(f"{API_URL}/createTask", json=create_payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errorId"):
            raise RuntimeError(f"AntiCaptcha createTask failed: {data}")
        task_id = data["taskId"]

        deadline = time.time() + MAX_WAIT
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            result_payload = {"clientKey": self.api_key, "taskId": task_id}
            result = requests.post(f"{API_URL}/getTaskResult", json=result_payload, timeout=30)
            result.raise_for_status()
            body = result.json()
            if body.get("errorId"):
                raise RuntimeError(f"AntiCaptcha getTaskResult error: {body}")
            if body.get("status") == "processing":
                continue
            solution = body.get("solution", {})
            token = solution.get("token") or solution.get("captchaSolve")
            if not token:
                raise RuntimeError(f"AntiCaptcha returned empty solution: {body}")
            return token
        raise TimeoutError("Timed out waiting for captcha solution")

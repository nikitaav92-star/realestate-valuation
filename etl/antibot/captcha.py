"""Anti-Captcha integration with telemetry support."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

API_URL = "https://api.anti-captcha.com"
POLL_INTERVAL = 5
MAX_WAIT = 120

LOGGER = logging.getLogger(__name__)


@dataclass
class CaptchaTelemetry:
    """Telemetry data for captcha solving operations."""
    
    task_id: Optional[int] = None
    site_key: str = ""
    page_url: str = ""
    solve_time_sec: float = 0.0
    status: str = "pending"  # pending, solving, solved, failed
    error_message: Optional[str] = None
    cost_estimate_usd: float = 0.001  # Approximate cost per solve
    attempts: int = 0
    
    def to_dict(self) -> dict:
        """Convert telemetry to dictionary for logging/monitoring."""
        return {
            "task_id": self.task_id,
            "site_key": self.site_key,
            "page_url": self.page_url,
            "solve_time_sec": round(self.solve_time_sec, 2),
            "status": self.status,
            "error_message": self.error_message,
            "cost_estimate_usd": self.cost_estimate_usd,
            "attempts": self.attempts,
        }


class CaptchaSolver:
    """Anti-Captcha API client with telemetry."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        max_wait: int = MAX_WAIT,
        poll_interval: int = POLL_INTERVAL,
    ) -> None:
        """Initialize captcha solver.
        
        Parameters
        ----------
        api_key : str, optional
            Anti-Captcha API key (defaults to ANTICAPTCHA_KEY env var)
        max_wait : int
            Maximum time to wait for solution (seconds)
        poll_interval : int
            Time between polling attempts (seconds)
        """
        self.api_key = api_key or os.getenv("ANTICAPTCHA_KEY")
        if not self.api_key:
            raise RuntimeError("ANTICAPTCHA_KEY is not set")
        self.max_wait = max_wait
        self.poll_interval = poll_interval
        self.telemetry_history: list[CaptchaTelemetry] = []
    
    def solve(
        self,
        site_key: str,
        page_url: str,
        *,
        task_type: str = "YandexSmartCaptchaTaskProxyless",
    ) -> tuple[str, CaptchaTelemetry]:
        """Solve captcha and return token with telemetry.
        
        Parameters
        ----------
        site_key : str
            Site key from captcha element
        page_url : str
            URL of the page containing captcha
        task_type : str
            Anti-Captcha task type
            
        Returns
        -------
        tuple[str, CaptchaTelemetry]
            Captcha token and telemetry data
        """
        telemetry = CaptchaTelemetry(
            site_key=site_key,
            page_url=page_url,
        )
        start_time = time.time()
        
        try:
            telemetry.status = "solving"
            telemetry.attempts = 1
            
            # Create task
            create_payload = {
                "clientKey": self.api_key,
                "task": {
                    "type": task_type,
                    "websiteURL": page_url,
                    "sitekey": site_key,
                },
            }
            resp = requests.post(f"{API_URL}/createTask", json=create_payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("errorId"):
                raise RuntimeError(f"AntiCaptcha createTask failed: {data}")
            
            telemetry.task_id = data["taskId"]
            LOGGER.debug("Created captcha task %s for %s", telemetry.task_id, page_url)
            
            # Poll for result
            deadline = time.time() + self.max_wait
            while time.time() < deadline:
                time.sleep(self.poll_interval)
                telemetry.attempts += 1
                
                result_payload = {"clientKey": self.api_key, "taskId": telemetry.task_id}
                result = requests.post(f"{API_URL}/getTaskResult", json=result_payload, timeout=30)
                result.raise_for_status()
                body = result.json()
                
                if body.get("errorId"):
                    raise RuntimeError(f"AntiCaptcha getTaskResult error: {body}")
                
                if body.get("status") == "processing":
                    continue
                
                # Extract solution
                solution = body.get("solution", {})
                token = solution.get("token") or solution.get("captchaSolve")
                
                if not token:
                    raise RuntimeError(f"AntiCaptcha returned empty solution: {body}")
                
                telemetry.status = "solved"
                telemetry.solve_time_sec = time.time() - start_time
                self.telemetry_history.append(telemetry)
                
                LOGGER.info(
                    "Solved captcha task %s in %.2fs (attempts=%d)",
                    telemetry.task_id,
                    telemetry.solve_time_sec,
                    telemetry.attempts,
                )
                
                return token, telemetry
            
            raise TimeoutError(f"Timed out waiting for captcha solution after {self.max_wait}s")
            
        except Exception as exc:
            telemetry.status = "failed"
            telemetry.error_message = str(exc)
            telemetry.solve_time_sec = time.time() - start_time
            self.telemetry_history.append(telemetry)
            
            LOGGER.error(
                "Failed to solve captcha: %s (time=%.2fs, attempts=%d)",
                exc,
                telemetry.solve_time_sec,
                telemetry.attempts,
            )
            raise
    
    def get_total_cost_estimate(self) -> float:
        """Calculate total estimated cost from telemetry history."""
        return sum(
            t.cost_estimate_usd
            for t in self.telemetry_history
            if t.status == "solved"
        )
    
    def get_success_rate(self) -> float:
        """Calculate success rate from telemetry history."""
        if not self.telemetry_history:
            return 0.0
        solved = sum(1 for t in self.telemetry_history if t.status == "solved")
        return solved / len(self.telemetry_history)
    
    def get_avg_solve_time(self) -> float:
        """Calculate average solve time from successful solves."""
        solved = [t for t in self.telemetry_history if t.status == "solved"]
        if not solved:
            return 0.0
        return sum(t.solve_time_sec for t in solved) / len(solved)


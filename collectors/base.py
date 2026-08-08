"""
Base collector with polite HTTP, retries, hashing, and structured logging.
"""

from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from models.schemas import CollectorRunResult, Discovery

logger = logging.getLogger("clank.collectors")


class BaseCollector(ABC):
    name: str = "base"
    source_type: str = "other"

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        user_agent: str = "SmartphoneIntelClank/0.1",
        min_delay: float = 1.5,
        **kwargs,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent
        self.min_delay = min_delay
        self._last_request = 0.0
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
                http2=True,
            )
        return self._client

    def close(self):
        if self._client and not self._client.is_closed:
            self._client.close()

    def _respect_rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last_request = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    def fetch(self, url: str, method: str = "GET", **kwargs) -> httpx.Response:
        self._respect_rate_limit()
        client = self._get_client()
        resp = client.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp

    @staticmethod
    def content_hash(content: str | bytes) -> str:
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    @abstractmethod
    def collect(self) -> list[Discovery]:
        """Return list of raw discoveries. Must not raise on empty results."""
        ...

    def run(self) -> tuple[CollectorRunResult, list[Discovery]]:
        started = datetime.utcnow()
        errors: list[str] = []
        discoveries: list[Discovery] = []
        retries = 0

        try:
            logger.info(f"[{self.name}] starting collection")
            discoveries = self.collect()
            logger.info(f"[{self.name}] found {len(discoveries)} candidate(s)")
        except Exception as e:
            logger.exception(f"[{self.name}] failed: {e}")
            errors.append(str(e))
        finally:
            self.close()

        finished = datetime.utcnow()
        duration = (finished - started).total_seconds()

        result = CollectorRunResult(
            collector=self.name,
            started_at=started,
            finished_at=finished,
            duration_seconds=duration,
            discoveries=len(discoveries),
            errors=errors,
            retries=retries,
        )
        return result, discoveries

"""Simple RPM/TPM rate limiter for OpenAI calls."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Deque, Optional, Tuple

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token and request rate limiter with a moving 60s window."""

    def __init__(
        self,
        max_requests_per_minute: Optional[int],
        max_tokens_per_minute: Optional[int],
    ) -> None:
        self.max_requests_per_minute = max_requests_per_minute
        self.max_tokens_per_minute = max_tokens_per_minute
        self._lock = threading.Lock()
        self._requests: Deque[float] = deque()
        self._token_events: Deque[Tuple[float, int]] = deque()
        self._token_total = 0

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self._requests and self._requests[0] < cutoff:
            self._requests.popleft()
        while self._token_events and self._token_events[0][0] < cutoff:
            _, tokens = self._token_events.popleft()
            self._token_total -= tokens

    def wait_for_capacity(self, tokens: int) -> None:
        if not self.max_requests_per_minute and not self.max_tokens_per_minute:
            return

        tokens = max(tokens, 1)
        while True:
            wait_time = 0.0
            with self._lock:
                now = time.time()
                self._prune(now)

                if self.max_requests_per_minute:
                    if len(self._requests) + 1 > self.max_requests_per_minute:
                        wait_time = max(wait_time, self._requests[0] + 60.0 - now)

                if self.max_tokens_per_minute:
                    if self._token_total + tokens > self.max_tokens_per_minute:
                        wait_time = max(wait_time, self._token_events[0][0] + 60.0 - now)

                if wait_time <= 0:
                    self._requests.append(now)
                    self._token_events.append((now, tokens))
                    self._token_total += tokens
                    return

            sleep_for = max(wait_time, 0.1)
            logger.debug("Rate limit reached; sleeping for %.2fs", sleep_for)
            time.sleep(sleep_for)

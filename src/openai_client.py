"""Thin OpenAI client wrapper with retries and logging."""

from __future__ import annotations

import logging
import random
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from openai import OpenAI

from src.config import OpenAIConfig
from src.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class OpenAIClient:
    _prompt_lock = threading.Lock()
    _semaphore: Optional[threading.Semaphore] = None
    _rate_limiter: Optional[RateLimiter] = None
    _limit_lock = threading.Lock()

    def __init__(self, config: OpenAIConfig, *, prompt_log_path: str | None = None):
        api_key = _require_env("OPENAI_API_KEY")
        self.client = OpenAI(
            api_key=api_key,
            organization=_optional_env("OPENAI_ORG"),
            project=_optional_env("OPENAI_PROJECT"),
            timeout=config.timeout_seconds,
        )
        self.config = config
        self.prompt_log_path = Path(prompt_log_path) if prompt_log_path else None
        if self.prompt_log_path:
            self.prompt_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_limits()
        self._current_drug_id: Optional[str] = None
        self._retry_totals: dict[str, int] = {}

    def _ensure_limits(self) -> None:
        with self._limit_lock:
            if self._semaphore is None:
                self._semaphore = threading.Semaphore(max(self.config.max_concurrent_requests, 1))
            if (
                self.config.max_requests_per_minute
                or self.config.max_tokens_per_minute
            ) and self._rate_limiter is None:
                self._rate_limiter = RateLimiter(
                    self.config.max_requests_per_minute,
                    self.config.max_tokens_per_minute,
                )

    def _is_transient_error(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code is not None:
            return status_code == 429 or status_code >= 500
        if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
            return True
        message = str(exc).lower()
        return "timeout" in message or "temporarily unavailable" in message

    def _backoff(self, attempt: int) -> None:
        base = min(2 ** attempt, 20)
        jitter = random.uniform(0, 0.5)
        time.sleep(base + jitter)

    def _retry(self, func: Callable[[], str]) -> str:
        retries = 0
        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = func()
                if retries and self._current_drug_id:
                    self._retry_totals[self._current_drug_id] = (
                        self._retry_totals.get(self._current_drug_id, 0) + retries
                    )
                return result
            except Exception as exc:  # pragma: no cover - network errors
                if not self._is_transient_error(exc):
                    logger.error("OpenAI call failed with non-retryable error: %s", exc)
                    raise
                logger.warning(
                    "OpenAI call failed (attempt %s/%s): %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
                if attempt == self.config.max_retries:
                    raise
                retries += 1
                self._backoff(attempt)
        raise RuntimeError("Failed to complete OpenAI request")

    def _estimate_tokens(self, *parts: str) -> int:
        combined = "".join(parts)
        return max(1, len(combined) // 4)

    def _throttle(self, tokens: int) -> None:
        if self._rate_limiter is not None:
            self._rate_limiter.wait_for_capacity(tokens)

    def _chat_completion(
        self,
        *,
        model: str,
        max_tokens: int,
        developer_message: str,
        user_message: str,
    ) -> str:
        self._log_prompt(model=model, developer_message=developer_message, user_message=user_message)
        tokens = self._estimate_tokens(developer_message, user_message)
        if self._semaphore is None:
            self._ensure_limits()
        if self._semaphore is None:
            raise RuntimeError("Concurrency limiter not initialized")
        with self._semaphore:
            self._throttle(tokens)
            completion = self.client.chat.completions.create(
                model=model,
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "developer", "content": developer_message},
                    {"role": "user", "content": user_message},
                ],
            )
            return completion.choices[0].message.content or ""

    def _log_prompt(self, *, model: str, developer_message: str, user_message: str) -> None:
        if not self.prompt_log_path:
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"[{timestamp}] model={model}\n"
            f"Developer: {developer_message}\n"
            f"User: {user_message}\n\n"
        )
        with self._prompt_lock:
            with self.prompt_log_path.open("a", encoding="utf-8") as handle:
                handle.write(entry)

    def generate_description(self, prompt: str) -> str:
        return self._retry(
            lambda: self._chat_completion(
                model=self.config.model,
                max_tokens=self.config.max_completion_tokens,
                developer_message=(
                    "You are an expert pharmaceutical scientist who writes precise, compliant API descriptions."
                    " Use factual, concise language and never fabricate data."
                ),
                user_message=prompt,
            )
        )

    def generate_summary(self, prompt: str) -> str:
        return self._retry(
            lambda: self._chat_completion(
                model=self.config.summary_model,
                max_tokens=self.config.summary_max_completion_tokens,
                developer_message=(
                    "You condense pharmaceutical descriptions into succinct overviews for catalog cards."
                    " Maintain accuracy, avoid marketing language, and keep to 1-2 sentences."
                ),
                user_message=prompt,
            )
        )

    def generate_text(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        developer_message: str = "You generate concise, accurate pharmaceutical copy without marketing language.",
    ) -> str:
        return self._retry(
            lambda: self._chat_completion(
                model=model or self.config.summary_model,
                max_tokens=max_tokens or self.config.summary_max_completion_tokens,
                developer_message=developer_message,
                user_message=prompt,
            )
        )

    def set_context(self, drug_id: Optional[str]) -> None:
        self._current_drug_id = drug_id

    def consume_retry_total(self, drug_id: str) -> int:
        return self._retry_totals.pop(drug_id, 0)


def _require_env(key: str) -> str:
    value = _optional_env(key)
    if not value:
        raise EnvironmentError(f"Environment variable {key} is required for OpenAI access.")
    return value


def _optional_env(key: str) -> str:
    return ("" + (os.getenv(key) or "")).strip()


import os  # placed at end to avoid linting issues with optional imports

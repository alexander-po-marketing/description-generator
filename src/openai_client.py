"""Thin OpenAI client wrapper with retries and logging."""

from __future__ import annotations

import logging
import time
from typing import Callable

from openai import OpenAI

from src.config import OpenAIConfig

logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self, config: OpenAIConfig):
        api_key = _require_env("OPENAI_API_KEY")
        self.client = OpenAI(
            api_key=api_key,
            organization=_optional_env("OPENAI_ORG"),
            project=_optional_env("OPENAI_PROJECT"),
            timeout=config.timeout_seconds,
        )
        self.config = config

    def _retry(self, func: Callable[[], str]) -> str:
        for attempt in range(1, self.config.max_retries + 1):
            try:
                return func()
            except Exception as exc:  # pragma: no cover - network errors
                logger.warning("OpenAI call failed (attempt %s/%s): %s", attempt, self.config.max_retries, exc)
                if attempt == self.config.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 10))
        raise RuntimeError("Failed to complete OpenAI request")

    def generate_description(self, prompt: str) -> str:
        def _call() -> str:
            completion = self.client.chat.completions.create(
                model=self.config.model,
                max_completion_tokens=self.config.max_completion_tokens,
                messages=[
                    {
                        "role": "developer",
                        "content": (
                            "You are an expert pharmaceutical scientist who writes precise, compliant API descriptions."
                            " Use factual, concise language and never fabricate data."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            return completion.choices[0].message.content or ""

        return self._retry(_call)

    def generate_summary(self, prompt: str) -> str:
        def _call() -> str:
            completion = self.client.chat.completions.create(
                model=self.config.summary_model,
                max_completion_tokens=self.config.summary_max_completion_tokens,
                messages=[
                    {
                        "role": "developer",
                        "content": (
                            "You condense pharmaceutical descriptions into succinct overviews for catalog cards."
                            " Maintain accuracy, avoid marketing language, and keep to 1-2 sentences."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            return completion.choices[0].message.content or ""

        return self._retry(_call)


def _require_env(key: str) -> str:
    value = _optional_env(key)
    if not value:
        raise EnvironmentError(f"Environment variable {key} is required for OpenAI access.")
    return value


def _optional_env(key: str) -> str:
    return ("" + (os.getenv(key) or "")).strip()


import os  # placed at end to avoid linting issues with optional imports


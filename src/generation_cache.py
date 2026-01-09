"""Prompt-hash cache for generated OpenAI content."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


CachePayload = Dict[str, object]


def prompt_hash(model: str, prompt: str) -> str:
    payload = f"{model}:{prompt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_generation_cache(path: str) -> CachePayload:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {"entries": {}}
    if not isinstance(data, dict):
        logger.warning("Generation cache is malformed, starting fresh.")
        return {"entries": {}}
    data.setdefault("entries", {})
    return data


def save_generation_cache(path: str, cache: CachePayload) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(cache, handle, ensure_ascii=False, indent=2)


def read_cached_text(cache: CachePayload, drug_id: str, entry_key: str, expected_hash: str) -> Optional[str]:
    entries = cache.get("entries", {})
    drug_entry = entries.get(drug_id, {}) if isinstance(entries, dict) else {}
    payload = drug_entry.get(entry_key)
    if not isinstance(payload, dict):
        return None
    if payload.get("hash") != expected_hash:
        return None
    return payload.get("text")


def write_cached_text(
    cache: CachePayload,
    drug_id: str,
    entry_key: str,
    prompt_hash_value: str,
    text: str,
    model: str,
) -> None:
    entries = cache.setdefault("entries", {})
    if not isinstance(entries, dict):
        return
    drug_entry = entries.setdefault(drug_id, {})
    if not isinstance(drug_entry, dict):
        return
    drug_entry[entry_key] = {"hash": prompt_hash_value, "text": text, "model": model}

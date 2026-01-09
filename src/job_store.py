"""Checkpointing and progress tracking helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from src.path_utils import ensure_parent_dir

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProgressState:
    completed_at: Dict[str, str] = field(default_factory=dict)
    failed_at: Dict[str, str] = field(default_factory=dict)
    started_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def mark_completed(self, drug_id: str) -> None:
        self.completed_at[drug_id] = _utc_now()
        self.updated_at = _utc_now()

    def mark_failed(self, drug_id: str) -> None:
        self.failed_at[drug_id] = _utc_now()
        self.updated_at = _utc_now()

    def to_dict(self) -> Dict[str, object]:
        return {
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed": self.completed_at,
            "failed": self.failed_at,
        }


def load_progress(path: str) -> ProgressState:
    target = Path(path)
    if not target.exists():
        return ProgressState()
    with target.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        logger.warning("Progress file %s is malformed; starting fresh.", path)
        return ProgressState()
    state = ProgressState(
        completed_at=dict(payload.get("completed") or {}),
        failed_at=dict(payload.get("failed") or {}),
        started_at=payload.get("started_at") or _utc_now(),
        updated_at=payload.get("updated_at") or _utc_now(),
    )
    return state


def save_progress(path: str, state: ProgressState) -> None:
    target = Path(path)
    ensure_parent_dir(target)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state.to_dict(), handle, ensure_ascii=False, indent=2)
    tmp_path.replace(target)


def append_jsonl(path: str, payload: Dict[str, object]) -> None:
    target = Path(path)
    ensure_parent_dir(target)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")

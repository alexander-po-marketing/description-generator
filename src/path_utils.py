"""Path helpers for safe repo-local file access."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]


def normalize_repo_path(path: str, base_dir: Optional[str] = None) -> Path:
    """Resolve a repo-relative path and ensure it stays inside the repo root."""

    if not path:
        raise ValueError("Path value is required")

    candidate = Path(path)
    if not candidate.is_absolute():
        if base_dir:
            base_path = Path(base_dir)
            if candidate.parts and candidate.parts[0] == base_path.name:
                candidate = REPO_ROOT / candidate
            else:
                candidate = REPO_ROOT / base_path / candidate
        else:
            candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()

    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError(f"Path {candidate} is outside the repository root") from exc
    return candidate


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

"""Export utilities for JSON outputs."""

from __future__ import annotations

import json
import logging
from typing import Dict, Mapping

from src.models import DrugData, GeneratedContent

logger = logging.getLogger(__name__)


def export_database(path: str, data: Dict[str, DrugData]) -> None:
    logger.info("Writing parsed database to %s", path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({k: v.to_serializable() for k, v in data.items()}, handle, ensure_ascii=False, indent=2)


def export_page_models(path: str, pages: Dict[str, object]) -> None:
    logger.info("Writing structured page models to %s", path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(pages, handle, ensure_ascii=False, indent=2)


def export_clean_import(path: str, pages: Dict[str, object]) -> None:
    """Write an import-ready payload without template metadata."""

    logger.info("Writing clean import payload to %s", path)
    trimmed: Dict[str, object] = {}
    for key, value in pages.items():
        if isinstance(value, Mapping):
            trimmed[key] = value.get("blocks") or value
        else:
            trimmed[key] = value

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(trimmed, handle, ensure_ascii=False, indent=2)


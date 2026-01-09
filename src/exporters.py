"""Export utilities for JSON outputs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Mapping

from src.models import DrugData, GeneratedContent
from src.path_utils import ensure_parent_dir

logger = logging.getLogger(__name__)


def _write_json_atomic(path: Path, payload: object) -> None:
    ensure_parent_dir(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def export_database(path: str, data: Dict[str, DrugData]) -> None:
    logger.info("Writing parsed database to %s", path)
    _write_json_atomic(Path(path), {k: v.to_serializable() for k, v in data.items()})


def export_page_models(path: str, pages: Dict[str, object]) -> None:
    logger.info("Writing structured page models to %s", path)
    _write_json_atomic(Path(path), pages)


def export_clean_import(path: str, pages: Dict[str, object]) -> None:
    """Write an import-ready payload without template metadata."""

    logger.info("Writing clean import payload to %s", path)
    trimmed: Dict[str, object] = {}
    for key, value in pages.items():
        if isinstance(value, Mapping):
            trimmed[key] = value.get("blocks") or value
        else:
            trimmed[key] = value

    _write_json_atomic(Path(path), trimmed)


def load_database(path: str) -> Dict[str, DrugData]:
    logger.info("Loading parsed database JSON from %s", path)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Parsed database JSON must be a mapping of drug IDs to payloads.")
    parsed: Dict[str, DrugData] = {}
    for drug_id, payload in data.items():
        if isinstance(payload, DrugData):
            parsed[drug_id] = payload
        elif isinstance(payload, dict):
            parsed[drug_id] = DrugData.from_serializable(payload)
    logger.info("Loaded %s drugs from parsed JSON", len(parsed))
    return parsed

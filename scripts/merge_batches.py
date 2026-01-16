"""Combine batch JSON outputs into a single file."""

from __future__ import annotations

import argparse
import copy
import json
import logging
from pathlib import Path
from typing import Any, Iterable, List


logger = logging.getLogger(__name__)


def _collect_input_paths(files: Iterable[str], input_dir: str | None, pattern: str) -> List[Path]:
    paths = {Path(file).expanduser() for file in files}
    if input_dir:
        base = Path(input_dir).expanduser()
        paths.update(base.glob(pattern))
    return sorted(path for path in paths if path.exists())


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _merge_values(base: Any, incoming: Any, path: str, on_conflict: str) -> Any:
    if isinstance(base, dict) and isinstance(incoming, dict):
        merged = dict(base)
        for key, value in incoming.items():
            sub_path = f"{path}.{key}" if path else key
            if key in merged:
                merged[key] = _merge_values(merged[key], value, sub_path, on_conflict)
            else:
                merged[key] = copy.deepcopy(value)
        return merged
    if isinstance(base, list) and isinstance(incoming, list):
        return base + copy.deepcopy(incoming)
    if base == incoming:
        return base
    if on_conflict == "overwrite":
        logger.warning("Overwriting conflict at %s", path)
        return copy.deepcopy(incoming)
    if on_conflict == "skip":
        logger.warning("Skipping conflicting value at %s", path)
        return base
    raise ValueError(f"Conflict at {path}: {type(base).__name__} vs {type(incoming).__name__}")


def _merge_payloads(payloads: List[Any], on_conflict: str) -> Any:
    if not payloads:
        raise ValueError("No payloads to merge.")
    merged = copy.deepcopy(payloads[0])
    for payload in payloads[1:]:
        merged = _merge_values(merged, payload, "", on_conflict)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine batch JSON outputs into a single batch file.",
    )
    parser.add_argument("inputs", nargs="*", help="JSON batch files to combine.")
    parser.add_argument("--input-dir", help="Directory containing batch JSON files.")
    parser.add_argument("--pattern", default="*.json", help="Glob pattern for --input-dir.")
    parser.add_argument("--output", required=True, help="Path for the combined JSON output.")
    parser.add_argument(
        "--on-conflict",
        choices=["error", "overwrite", "skip"],
        default="error",
        help="How to handle conflicts when merging payloads.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    input_paths = _collect_input_paths(args.inputs, args.input_dir, args.pattern)
    if not input_paths:
        raise SystemExit("No input JSON files found.")

    payloads = []
    for path in input_paths:
        logger.info("Loading %s", path)
        payloads.append(_load_json(path))

    merged = _merge_payloads(payloads, args.on_conflict)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=2)

    logger.info("Wrote combined output to %s", output_path)


if __name__ == "__main__":
    main()

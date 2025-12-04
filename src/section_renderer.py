"""Render per-section HTML fragments from generated API page models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Mapping

from src.preview_renderer import build_section_blocks


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create section-level HTML from API page models")
    parser.add_argument(
        "--input",
        default="outputs/api_pages.json",
        help="Path to the generated api_pages.json file",
    )
    parser.add_argument(
        "--output",
        default="outputs/section_html/section_blocks.json",
        help="Destination for the section HTML dictionary",
    )
    return parser.parse_args(argv or None)


def load_api_pages(path: Path) -> Dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"API pages JSON not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object mapping API IDs to page models")
    return data


def render_sections(api_pages: Mapping[str, object]) -> Dict[str, Dict[str, str]]:
    rendered: Dict[str, Dict[str, str]] = {}
    for api_id, page in api_pages.items():
        normalized_page = page.get("raw") if isinstance(page, Mapping) and "raw" in page else page
        if not isinstance(normalized_page, Mapping):
            continue
        sections = build_section_blocks(normalized_page)
        if sections:
            rendered[str(api_id)] = sections
    return rendered


def save_sections(sections: Dict[str, Dict[str, str]], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(sections, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input)
    output_path = Path(args.output)

    api_pages = load_api_pages(input_path)
    sections = render_sections(api_pages)
    save_sections(sections, output_path)
    print(f"Wrote section HTML for {len(sections)} APIs to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

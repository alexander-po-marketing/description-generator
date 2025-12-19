"""Extract SEO metadata from API description JSON outputs."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping

logger = logging.getLogger(__name__)

FILTER_SEO_KEYS = {
    "filter_seo",
    "filterSeo",
    "filterSEO",
    "seo_filter",
    "seoFilter",
    "seo-filter",
}
FILTER_SEO_BLOCK_IDS = {
    "filter-seo",
    "seo-filter",
    "filterSeo",
    "seoFilter",
    "seo_filter",
}


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _normalize_keywords(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]


def _extract_from_block_value(value: Mapping[str, Any]) -> dict[str, Any]:
    title = value.get("Title") or value.get("title")
    meta_description = value.get("Meta description") or value.get("metaDescription") or value.get("meta_description")
    keywords = value.get("Keywords") or value.get("keywords")
    return {
        "title": str(title).strip() if title else None,
        "metaDescription": str(meta_description).strip() if meta_description else None,
        "keywords": _normalize_keywords(keywords),
    }


def _extract_from_seo_mapping(seo: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": str(seo.get("title")).strip() if seo.get("title") else None,
        "metaDescription": str(seo.get("metaDescription")).strip() if seo.get("metaDescription") else None,
        "keywords": _normalize_keywords(seo.get("keywords")),
    }


def _extract_from_blocks(blocks: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    filter_candidate = None
    seo_candidate = None
    for block in blocks:
        block_id = str(block.get("id") or "")
        value = block.get("value")
        if not isinstance(value, Mapping):
            continue
        if block_id in FILTER_SEO_BLOCK_IDS:
            filter_candidate = _extract_from_block_value(value)
        if block_id == "seo":
            seo_candidate = _extract_from_block_value(value)
    return filter_candidate or seo_candidate


def _extract_filter_seo(page: Mapping[str, Any]) -> dict[str, Any] | None:
    for key in FILTER_SEO_KEYS:
        candidate = page.get(key)
        if isinstance(candidate, Mapping):
            return _extract_from_seo_mapping(candidate)
    filter_section = page.get("filter_section")
    if isinstance(filter_section, Mapping):
        seo_candidate = filter_section.get("seo")
        if isinstance(seo_candidate, Mapping):
            return _extract_from_seo_mapping(seo_candidate)
    return None


def _extract_seo(page: Any) -> dict[str, Any] | None:
    if isinstance(page, list):
        blocks = [block for block in page if isinstance(block, Mapping)]
        return _extract_from_blocks(blocks)

    if not isinstance(page, Mapping):
        return None

    filter_seo = _extract_filter_seo(page)
    if filter_seo:
        return filter_seo

    blocks = page.get("blocks")
    if isinstance(blocks, list):
        extracted = _extract_from_blocks(blocks)
        if extracted:
            return extracted

    raw = page.get("raw")
    if isinstance(raw, Mapping):
        filter_seo = _extract_filter_seo(raw)
        if filter_seo:
            return filter_seo
        seo = raw.get("seo")
        if isinstance(seo, Mapping):
            return _extract_from_seo_mapping(seo)

    seo = page.get("seo")
    if isinstance(seo, Mapping):
        return _extract_from_seo_mapping(seo)

    return None


def _build_output(data: Any) -> Any:
    if isinstance(data, list):
        results = []
        for index, item in enumerate(data):
            seo = _extract_seo(item)
            if seo is None:
                logger.warning("Missing SEO metadata for item %s", index)
                seo = {"title": None, "metaDescription": None, "keywords": []}
            results.append(seo)
        return results

    if isinstance(data, Mapping):
        results: dict[str, Any] = {}
        for key, value in data.items():
            seo = _extract_seo(value)
            if seo is None:
                logger.warning("Missing SEO metadata for key %s", key)
                seo = {"title": None, "metaDescription": None, "keywords": []}
            results[str(key)] = seo
        return results

    raise ValueError("Unsupported JSON structure; expected a list or object mapping.")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract SEO metadata from API description JSON files.",
    )
    parser.add_argument("input", help="Path to api descriptions JSON")
    parser.add_argument("output", help="Path to write SEO metadata JSON")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.log_level)

    input_path = Path(args.input)
    output_path = Path(args.output)

    with input_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    seo_payload = _build_output(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(seo_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote SEO metadata to %s", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

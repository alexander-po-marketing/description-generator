"""Generate filter-intent overlays for API descriptions using OpenAI."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)

FILTER_LABELS = {
    "gmp": "GMP-certified",
    "cep": "with CEP available",
    "wc": "with Written Confirmation (WC)",
    "fda": "with US FDA-facing documentation",
    "coa": "with CoA provided for each batch",
    "iso9001": "with ISO 9001-certified quality systems",
    "usdmf": "with US DMF filed",
}

FILTER_EXPLAINERS = {
    "gmp": "Suppliers that report manufacturing under Good Manufacturing Practice (GMP) and can provide GMP certificates or audit documentation.",
    "cep": "APIs for which a Certificate of Suitability (CEP) is reported, indicating compliance with the relevant Ph. Eur. monograph.",
    "wc": "Suppliers that can provide Written Confirmation (WC) for export to the EU, according to applicable guidelines.",
    "fda": "Suppliers linked to US FDA-regulated markets, typically through US DMF filings or FDA-registered facilities. Do not state that the finished product is FDA-approved.",
    "coa": "Suppliers that provide a Certificate of Analysis (CoA) for each batch of the API, detailing assay, impurities and key quality parameters.",
    "iso9001": "Suppliers whose quality management systems are certified according to ISO 9001.",
    "usdmf": "APIs for which a US Drug Master File (US DMF) has been filed by at least one supplier.",
}

FILTER_BLOCK_TEXT = {
    "gmp": "filter_block_text_gmp for API_NAME",
    "cep": "filter_block_text_cep for API_NAME",
    "wc": "filter_block_text_wc for API_NAME",
    "fda": "filter_block_text_fda for API_NAME",
    "coa": "filter_block_text_coa for API_NAME",
    "iso9001": "filter_block_text_iso9001 for API_NAME",
    "usdmf": "filter_block_text_usdmf for API_NAME",
}


class FilteredIntentError(RuntimeError):
    """Raised when filter intent generation fails."""


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"Environment variable {key} is required for OpenAI access.")
    return value


def generate_filter_intent_text(api_name: str, filter_key: str, client: OpenAI) -> str:
    """Generate a short, filter-focused sourcing paragraph for the hero block."""

    if filter_key not in FILTER_LABELS:
        raise ValueError(f"Unknown filter key '{filter_key}'. Expected one of: {', '.join(FILTER_LABELS)}")

    filter_label = FILTER_LABELS[filter_key]
    template = FILTER_BLOCK_TEXT.get(filter_key)
    if not template:
        raise ValueError(f"Unknown filter key '{filter_key}'. Expected one of: {', '.join(FILTER_BLOCK_TEXT)}")
    filter_background = template.replace("API_NAME", api_name)

    prompt = f"""
You are a senior pharmaceutical API B2B content writer.

Task:
You will receive:

An API name,

A sourcing filter used by the buyer,

A background text describing what this filter means.

Write ONE short paragraph (3–5 sentences) that explains, for {api_name} API:

how the "{filter_label}" filter changes the sourcing context,

what documentation and quality signals buyers typically expect under this filter,

how this filter affects supplier selection, documentation review, or market availability.

Focus only on sourcing, regulatory and quality aspects.
Do NOT provide medical advice or treatment recommendations.
Do NOT claim that finished products are approved by any authority; stay at the API/supplier level.
Return ONLY the paragraph as plain text (no JSON, no bullet points).

API name: {api_name}
Filter label: {filter_label}

Filter background:
{filter_background}
""".strip()

    completion = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {
                "role": "developer",
                "content": (
                    "Provide a single sourcing-focused paragraph for the specified filter. Keep it concise and avoid clinical guidance."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    content = (completion.choices[0].message.content or "").strip()
    if not content:
        raise FilteredIntentError("Model returned empty content for filter intent text.")

    return content


def _normalize_page(page: Mapping[str, Any]) -> Mapping[str, Any]:
    if "raw" in page and isinstance(page.get("raw"), Mapping):
        return page["raw"]  # type: ignore[return-value]
    return page


def _stringify(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        flattened: List[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            flattened.append(text)
        return ", ".join(flattened) if flattened else None
    if isinstance(value, Mapping):
        return "; ".join(f"{k}: {v}" for k, v in value.items() if v)
    text = str(value).strip()
    return text or None


def _clean_title(value: object) -> Optional[str]:
    text = _stringify(value)
    if not text:
        return None
    return text.split("|")[0].strip()


def _extract_api_fields(page: Mapping[str, Any]) -> Tuple[str | None, str | None]:
    normalized = _normalize_page(page)
    api_name: str | None = None
    if isinstance(normalized, Mapping):
        hero = normalized.get("hero")
        if isinstance(hero, Mapping):
            api_name = _clean_title(hero.get("title")) or _stringify(hero.get("genericName"))
        if not api_name:
            api_name = _clean_title(normalized.get("name")) or _stringify(normalized.get("api_name"))

    original_description: str | None = None
    clinical_overview = normalized.get("clinicalOverview") if isinstance(normalized, Mapping) else None
    if isinstance(clinical_overview, Mapping):
        long_desc = clinical_overview.get("longDescription")
        if isinstance(long_desc, str):
            original_description = long_desc
    if not original_description and isinstance(normalized, Mapping):
        overview = normalized.get("overview")
        if isinstance(overview, Mapping):
            desc = overview.get("description")
            if isinstance(desc, str):
                original_description = desc

    return api_name, original_description


def _iter_pages(data: Any) -> Iterable[tuple[Any, MutableMapping[str, Any]]]:
    if isinstance(data, list):
        for index, item in enumerate(data):
            if isinstance(item, MutableMapping):
                yield index, item
    elif isinstance(data, MutableMapping):
        for key, value in data.items():
            if isinstance(value, MutableMapping):
                yield key, value


def generate_filter_text(api_name: str, filter_key: str) -> str:
    template = FILTER_BLOCK_TEXT.get(filter_key)
    if not template:
        raise ValueError(f"Unknown filter key '{filter_key}'. Expected one of: {', '.join(FILTER_BLOCK_TEXT)}")
    return template.replace("API_NAME", api_name)


def apply_filtered_intent_to_file(
    input_path: str,
    output_path: str,
    filter_key: str,
) -> None:
    """Apply filter-intent hero content to every entry in a JSON file."""

    if filter_key not in FILTER_LABELS:
        raise ValueError(f"Unknown filter key '{filter_key}'. Expected one of: {', '.join(FILTER_LABELS)}")

    input_file = Path(input_path)
    output_file = Path(output_path)
    with input_file.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    client = OpenAI(api_key=_require_env("OPENAI_API_KEY"))

    mutated = False
    for key, page in _iter_pages(data):
        normalized_page = _normalize_page(page)
        if not isinstance(normalized_page, MutableMapping):
            logger.warning("Skipping item %s because page structure is not a mapping.", key)
            continue

        api_name, _ = _extract_api_fields(page)
        if not api_name:
            logger.warning("Skipping item %s because API name is missing.", key)
            continue

        logger.info("Applying filter '%s' to %s", filter_key, api_name)
        filter_intent_text = generate_filter_intent_text(api_name=api_name, filter_key=filter_key, client=client)
        filter_intent_title = f"{api_name} API manufacturers: {FILTER_LABELS[filter_key]}"

        hero = normalized_page.get("hero")
        if not isinstance(hero, MutableMapping):
            logger.warning("Skipping item %s because hero block is missing.", key)
            continue

        filter_intent = hero.get("filter_intent")
        if not isinstance(filter_intent, dict):
            filter_intent = {}
            hero["filter_intent"] = filter_intent

        filter_intent["title"] = filter_intent_title
        filter_intent["text"] = filter_intent_text

        if isinstance(page, MutableMapping):
            template = page.get("template")
            if isinstance(template, MutableMapping):
                blocks = template.get("blocks")
                if isinstance(blocks, list):
                    hero_block = next(
                        (block for block in blocks if isinstance(block, MutableMapping) and block.get("id") == "hero"),
                        None,
                    )
                    if hero_block is not None:
                        children = hero_block.get("children")
                        if not isinstance(children, list):
                            children = []
                            hero_block["children"] = children

                        existing_group = next(
                            (
                                child
                                for child in children
                                if isinstance(child, MutableMapping) and child.get("id") == "hero-filter-intent"
                            ),
                            None,
                        )

                        if existing_group is None:
                            children.append(
                                {
                                    "id": "hero-filter-intent",
                                    "label": "Filter intent",
                                    "path": ["filter_intent"],
                                    "type": "group",
                                    "visible": True,
                                    "children": [
                                        {
                                            "id": "hero-filter-intent-title",
                                            "label": "Title",
                                            "path": ["title"],
                                            "type": "field",
                                        },
                                        {
                                            "id": "hero-filter-intent-text",
                                            "label": "Text",
                                            "path": ["text"],
                                            "type": "field",
                                        },
                                    ],
                                }
                            )

        if isinstance(page, MutableMapping):
            blocks_list = page.get("blocks")
            if isinstance(blocks_list, list):
                for block in blocks_list:
                    if isinstance(block, MutableMapping) and block.get("id") == "hero":
                        hero_value = block.get("value")
                        if not isinstance(hero_value, MutableMapping):
                            hero_value = {}
                        hero_value["Filter intent"] = {"Title": filter_intent_title, "Text": filter_intent_text}
                        block["value"] = hero_value
                        break

        filter_section = normalized_page.get("filter_section")
        if not isinstance(filter_section, dict):
            filter_section = {}
            normalized_page["filter_section"] = filter_section
        filter_section[filter_key] = generate_filter_text(api_name, filter_key)
        mutated = True

    if not mutated:
        logger.warning("No items were updated. Check input structure and required fields.")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    import argparse

    parser = argparse.ArgumentParser(description="Post-process API descriptions with filter-specific overlays.")
    parser.add_argument("input", help="Path to input JSON file containing API descriptions")
    parser.add_argument("output", help="Path to write JSON with filtered descriptions")
    parser.add_argument(
        "filter_key",
        choices=sorted(FILTER_LABELS.keys()),
        help="Filter key to apply",
    )
    args = parser.parse_args()

    apply_filtered_intent_to_file(args.input, args.output, args.filter_key)

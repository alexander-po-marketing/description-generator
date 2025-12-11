"""Generate filter-intent overlays for API descriptions using OpenAI."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Tuple

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


def _build_prompt(api_name: str, original_description: str, filter_key: str) -> str:
    filter_label = FILTER_LABELS[filter_key]
    filter_explainer = FILTER_EXPLAINERS[filter_key]
    return f"""
You are a senior pharmaceutical B2B content writer.

Task:
You will receive:
- An API name
- A sourcing filter applied by the buyer
- A short explanation of what this filter means
- The original API product description text

You must create TWO new short paragraphs that add filter-specific sourcing context,
without rewriting the original description.

1) filtered_intro:
   - 2–4 sentences
   - Explain that this is the {filter_label} view of {api_name} API suppliers.
   - Explain what buyers usually look for under this filter (documents, quality aspects, markets).
   - Keep it factual and sourcing-focused.

2) sourcing_note:
   - 2–3 sentences
   - Short note that can be placed AFTER the original description.
   - Explain how the filter affects supplier selection, documentation review, or market availability.
   - Do not contradict the original description.

Constraints:
- Do NOT rewrite or summarize the original description.
- Do NOT provide medical advice.
- Do NOT claim that finished products are approved by authorities (e.g. do not say 'FDA-approved drug'); keep it at the API/supplier level.
- Output valid JSON with two string fields: "filtered_intro" and "sourcing_note".

API name: {api_name}
Filter label: {filter_label}
Filter meaning: {filter_explainer}

Original description:
{original_description}
""".strip()


def _parse_model_response(raw_content: str) -> Dict[str, str]:
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:  # pragma: no cover - depends on model output
        raise FilteredIntentError(f"Model did not return valid JSON: {exc}") from exc

    if not isinstance(parsed, dict) or "filtered_intro" not in parsed or "sourcing_note" not in parsed:
        raise FilteredIntentError("Model response missing required fields: 'filtered_intro' and 'sourcing_note'.")

    filtered_intro = parsed.get("filtered_intro")
    sourcing_note = parsed.get("sourcing_note")
    if not isinstance(filtered_intro, str) or not isinstance(sourcing_note, str):
        raise FilteredIntentError("Model response fields must be strings.")

    return {"filtered_intro": filtered_intro.strip(), "sourcing_note": sourcing_note.strip()}


def apply_filtered_intent(
    api_name: str,
    original_description: str,
    filter_key: str,
    client: OpenAI,
) -> Dict[str, str]:
    """
    Generate filter-intent overlays for a single API description.

    Returns a dict with keys: 'filtered_intro', 'sourcing_note', 'filtered_description'.
    """

    if filter_key not in FILTER_LABELS:
        raise ValueError(f"Unknown filter key '{filter_key}'. Expected one of: {', '.join(FILTER_LABELS)}")

    prompt = _build_prompt(api_name=api_name, original_description=original_description, filter_key=filter_key)

    completion = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "developer", "content": "Generate filter-intent overlays without rewriting the source description."},
            {"role": "user", "content": prompt},
        ],
    )
    content = completion.choices[0].message.content or ""
    parsed = _parse_model_response(content)
    filtered_description = f"{parsed['filtered_intro']}\n\n{original_description}\n\n{parsed['sourcing_note']}"
    parsed["filtered_description"] = filtered_description
    return parsed


def _normalize_page(page: Mapping[str, Any]) -> Mapping[str, Any]:
    if "raw" in page and isinstance(page.get("raw"), Mapping):
        return page["raw"]  # type: ignore[return-value]
    return page


def _extract_api_fields(page: Mapping[str, Any]) -> Tuple[str | None, str | None]:
    normalized = _normalize_page(page)
    api_name: str | None = None
    if isinstance(normalized, Mapping):
        hero = normalized.get("hero")
        if isinstance(hero, Mapping):
            api_name = hero.get("title") or hero.get("genericName")
        if not api_name:
            api_name = normalized.get("api_name") or normalized.get("name")

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
    """Apply filtered intent overlays to every entry in a JSON file."""

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

        api_name, original_description = _extract_api_fields(page)
        if not api_name or not original_description:
            logger.warning("Skipping item %s because required fields are missing.", key)
            continue

        logger.info("Applying filter '%s' to %s", filter_key, api_name)
        overlays = apply_filtered_intent(
            api_name=api_name,
            original_description=original_description,
            filter_key=filter_key,
            client=client,
        )

        filtered_descriptions = normalized_page.get("filtered_descriptions")
        if not isinstance(filtered_descriptions, dict):
            filtered_descriptions = {}
            normalized_page["filtered_descriptions"] = filtered_descriptions
        filtered_descriptions[filter_key] = overlays["filtered_description"]

        filtered_intro = normalized_page.get("filtered_intro")
        if not isinstance(filtered_intro, dict):
            filtered_intro = {}
            normalized_page["filtered_intro"] = filtered_intro
        filtered_intro[filter_key] = overlays["filtered_intro"]

        sourcing_note = normalized_page.get("sourcing_note")
        if not isinstance(sourcing_note, dict):
            sourcing_note = {}
            normalized_page["sourcing_note"] = sourcing_note
        sourcing_note[filter_key] = overlays["sourcing_note"]

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

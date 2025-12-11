"""Render HTML sections for filtered intent API pages."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Dict, Mapping, MutableMapping, Optional

from src.filtered_intent_postprocessor import FILTER_EXPLAINERS, FILTER_LABELS
from src.preview_renderer import (
    _build_adme_section,
    _build_clinical_overview_content,
    _build_formulation_section,
    _build_identification_section,
    _build_pharmacology_section,
    _build_regulatory_section,
    _build_safety_section,
    _chip_list,
    _escape,
    _facts_table,
    _subblock,
    _unordered_list,
)


DEFAULT_INPUT = "outputs/filtered_api_pages.json"
DEFAULT_OUTPUT = "outputs/section_html/filter_section_blocks.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create section-level HTML from filter-intent API page models"
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help="Path to the generated filtered api_pages JSON file",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Destination for the filter section HTML dictionary",
    )
    parser.add_argument(
        "--filter-key",
        choices=sorted(FILTER_LABELS.keys()),
        help="Optional filter key to apply when deriving SEO metadata",
    )
    return parser.parse_args(argv or None)


def load_api_pages(path: Path) -> Dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"API pages JSON not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object mapping API IDs to page models")
    return data


def _stringify(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(items) if items else None
    if isinstance(value, Mapping):
        return "; ".join(f"{k}: {v}" for k, v in value.items() if v)
    text = str(value).strip()
    return text or None


def _clean_title(value: object) -> Optional[str]:
    text = _stringify(value)
    if not text:
        return None
    return text.split("|")[0].strip()


def _derive_api_name(page: Mapping[str, object]) -> Optional[str]:
    hero = page.get("hero") if isinstance(page, Mapping) else None
    if isinstance(hero, Mapping):
        title = _clean_title(hero.get("title"))
        if title:
            return title
        generic = _stringify(hero.get("genericName"))
        if generic:
            return generic
    if isinstance(page, Mapping):
        fallback = _clean_title(page.get("name")) or _stringify(page.get("api_name"))
        if fallback:
            return fallback
    return None


def _detect_filter_key(
    page: Mapping[str, object], override: Optional[str] = None
) -> Optional[str]:
    if override:
        return override

    filter_section = page.get("filter_section")
    if isinstance(filter_section, Mapping):
        for key in filter_section:
            if key in FILTER_LABELS:
                return str(key)

    hero = page.get("hero") if isinstance(page, Mapping) else None
    if isinstance(hero, Mapping):
        filter_intent = hero.get("filter_intent")
        if isinstance(filter_intent, Mapping):
            title = filter_intent.get("title")
            if isinstance(title, str):
                normalized_title = title.lower()
                for key, label in FILTER_LABELS.items():
                    if label.lower() in normalized_title:
                        return key

    return None


def _update_seo_metadata(page: MutableMapping[str, object], filter_key: Optional[str]) -> None:
    if not filter_key:
        return

    api_name = _derive_api_name(page)
    label = FILTER_LABELS.get(filter_key)
    explainer = FILTER_EXPLAINERS.get(filter_key)
    if not api_name or not label or not explainer:
        return

    seo_title = f"{api_name} API suppliers - {label}"
    meta_description = f"Find {api_name} API manufacturers. {explainer}"

    seo = page.get("seo")
    if not isinstance(seo, MutableMapping):
        seo = {}
        page["seo"] = seo
    seo["title"] = seo_title
    seo["metaDescription"] = meta_description

    blocks = page.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, MutableMapping):
                continue
            if block.get("id") != "seo":
                continue
            value = block.get("value")
            if not isinstance(value, MutableMapping):
                value = {}
                block["value"] = value
            value["Title"] = seo_title
            value["Meta description"] = meta_description


def _filter_block_text(page: Mapping[str, object], filter_key: Optional[str]) -> Optional[str]:
    hero = page.get("hero") if isinstance(page, Mapping) else None
    if isinstance(hero, Mapping):
        filter_intent = hero.get("filter_intent")
        if isinstance(filter_intent, Mapping):
            block_text = filter_intent.get("filter_block_text")
            if isinstance(block_text, str) and block_text.strip():
                return block_text

    filter_section = page.get("filter_section")
    if isinstance(filter_section, Mapping) and filter_key:
        block_text = filter_section.get(filter_key)
        if isinstance(block_text, str) and block_text.strip():
            return block_text
    return None


def _build_filter_hero_block(page: Mapping[str, object], filter_key: Optional[str]) -> str:
    hero = page.get("hero", {}) if isinstance(page, Mapping) else {}
    filter_intent = hero.get("filter_intent") if isinstance(hero, Mapping) else {}

    title = None
    if isinstance(filter_intent, Mapping):
        title = filter_intent.get("title")
    if not isinstance(title, str):
        title = hero.get("title") or "API overview"

    summary_sentence = None
    if isinstance(filter_intent, Mapping):
        summary_sentence = filter_intent.get("filter_summary")
    if not isinstance(summary_sentence, str):
        summary_sentence = hero.get("summarySentence") or hero.get("summary")

    categories = (hero.get("therapeuticCategories", []) or [])[:6]
    taxonomy = page.get("categoriesAndTaxonomy", {}) if isinstance(page, Mapping) else {}
    if not categories and isinstance(taxonomy, Mapping):
        categories = (taxonomy.get("therapeuticClasses", []) or [])[:6]
    category_chips = _chip_list(categories)

    facts_source = hero.get("facts") or page.get("facts") or {}
    facts_html = _facts_table(facts_source if isinstance(facts_source, Mapping) else {})

    primary_indications = _unordered_list(
        page.get("primaryIndications") or hero.get("primaryUseCases") or []
    )
    buyer_cheatsheet_list = _unordered_list(
        (page.get("buyerCheatsheet", {}) or {}).get("bullets", [])
    )
    block_text = _filter_block_text(page, filter_key)

    buyer_cheatsheet_parts = []
    if buyer_cheatsheet_list:
        buyer_cheatsheet_parts.append(buyer_cheatsheet_list)
    if block_text:
        buyer_cheatsheet_parts.append(
            f"<div class=\"raw-material-seo-filter-block\">{block_text}</div>"
        )
    buyer_cheatsheet_content = "".join(buyer_cheatsheet_parts)

    content_parts = [
        f"<h2 class=\"raw-material-seo-hero-title\">{_escape(title)}</h2>",
        f"<p class=\"raw-material-seo-lead raw-material-seo-hero-summary\">{_escape(summary_sentence)}</p>"
        if summary_sentence
        else "",
        _subblock("Therapeutic categories", category_chips),
        facts_html,
        _subblock("Primary indications", primary_indications),
        _subblock("Buyer cheatsheet", buyer_cheatsheet_content),
    ]
    body = "".join(part for part in content_parts if part)
    return (
        f"<div class=\"raw-material-seo-hero-block raw-material-seo-section raw-material-seo-section-hero\">{body}</div>"
        if body
        else ""
    )


def build_filter_section_blocks(
    page: Mapping[str, object], filter_key: Optional[str] = None
) -> Dict[str, str]:
    sections = {
        "hero": _build_filter_hero_block(page, filter_key),
        "overview": _build_clinical_overview_content(page),
        "identification": _build_identification_section(
            page.get("clinicalOverview", {}), page
        ),
        "pharmacology": _build_pharmacology_section(page.get("clinicalOverview", {}), page),
        "adme_pk": _build_adme_section(page.get("clinicalOverview", {}), page),
        "formulation": _build_formulation_section(page.get("clinicalOverview", {}), page),
        "regulatory": _build_regulatory_section(page.get("clinicalOverview", {}), page),
        "safety": _build_safety_section(page.get("clinicalOverview", {}), page),
    }
    return {key: value for key, value in sections.items() if value}


def render_filter_sections(
    api_pages: Mapping[str, object], filter_key: Optional[str] = None
) -> Dict[str, Dict[str, str]]:
    rendered: Dict[str, Dict[str, str]] = {}
    for api_id, page in api_pages.items():
        if not isinstance(page, Mapping):
            continue

        working_copy: MutableMapping[str, object] = copy.deepcopy(page)
        normalized_page = (
            working_copy.get("raw") if isinstance(working_copy, Mapping) and "raw" in working_copy else working_copy
        )
        if not isinstance(normalized_page, MutableMapping):
            continue

        derived_filter_key = _detect_filter_key(normalized_page, override=filter_key)
        _update_seo_metadata(normalized_page, derived_filter_key)
        if normalized_page is not working_copy:
            _update_seo_metadata(working_copy, derived_filter_key)

        sections = build_filter_section_blocks(working_copy, derived_filter_key)
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
    sections = render_filter_sections(api_pages, filter_key=args.filter_key)
    save_sections(sections, output_path)
    print(f"Wrote filter section HTML for {len(sections)} APIs to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

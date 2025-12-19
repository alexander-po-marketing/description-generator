"""Render HTML sections for filtered intent API pages."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Dict, Mapping, MutableMapping, Optional

from src.filtered_intent_postprocessor import (
    FILTER_EXPLAINERS,
    FILTER_LABELS,
    ORIGIN_COUNTRY_LABELS,
    ORIGIN_REGION_LABELS,
    _is_origin_country,
    _is_origin_filter,
    _is_origin_region,
)
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
            for nested_key in filter_intent:
                if nested_key in FILTER_LABELS:
                    return str(nested_key)
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


def _filter_intent_entry(
    filter_intent: Mapping[str, object], filter_key: Optional[str]
) -> Optional[Mapping[str, object]]:
    if filter_key and filter_key in filter_intent:
        nested = filter_intent.get(filter_key)
        if isinstance(nested, Mapping):
            return nested
    return filter_intent


def _filter_block_text(page: Mapping[str, object], filter_key: Optional[str]) -> Optional[str]:
    hero = page.get("hero") if isinstance(page, Mapping) else None
    if isinstance(hero, Mapping):
        filter_intent = hero.get("filter_intent")
        if isinstance(filter_intent, Mapping):
            intent_entry = _filter_intent_entry(filter_intent, filter_key)
            if isinstance(intent_entry, Mapping):
                block_text = intent_entry.get("filter_block_text")
                if isinstance(block_text, str) and block_text.strip():
                    return block_text

    filter_section = page.get("filter_section")
    if isinstance(filter_section, Mapping) and filter_key:
        block_text = filter_section.get(filter_key)
        if isinstance(block_text, str) and block_text.strip():
            return block_text
    return None


def _buyer_cheatsheet_items(source: object) -> list[str]:
    if isinstance(source, Mapping):
        bullets = source.get("bullets")
        if isinstance(bullets, list):
            return [str(item).strip() for item in bullets if str(item).strip()]
    if isinstance(source, (list, tuple)):
        return [str(item).strip() for item in source if str(item).strip()]
    if isinstance(source, str) and source.strip():
        return [line.strip() for line in source.splitlines() if line.strip()]
    return []


def _buyer_cheatsheet_html(page: Mapping[str, object], filter_key: Optional[str]) -> str:
    hero = page.get("hero") if isinstance(page, Mapping) else None
    filter_intent = hero.get("filter_intent") if isinstance(hero, Mapping) else None
    intent_entry = _filter_intent_entry(filter_intent, filter_key) if isinstance(filter_intent, Mapping) else None

    if isinstance(intent_entry, Mapping):
        buyer_cheatsheet = intent_entry.get("buyerCheatsheet")
        bullets = _buyer_cheatsheet_items(buyer_cheatsheet)
        if bullets:
            html = _unordered_list(bullets)
            if html:
                return html

    buyer_cheatsheet_source = page.get("buyerCheatsheet") if isinstance(page, Mapping) else None
    bullets = _buyer_cheatsheet_items(buyer_cheatsheet_source)
    if bullets:
        html = _unordered_list(bullets)
        if html:
            return html

    return ""


def _origin_label_from_key(filter_key: str) -> Optional[str]:
    if _is_origin_country(filter_key):
        _, _, code = filter_key.partition(":")
        return ORIGIN_COUNTRY_LABELS.get(code)
    if _is_origin_region(filter_key):
        _, _, region = filter_key.partition(":")
        return ORIGIN_REGION_LABELS.get(region)
    return None


def _build_filter_hero_block(page: Mapping[str, object], filter_key: Optional[str]) -> str:
    hero = page.get("hero", {}) if isinstance(page, Mapping) else {}
    filter_intent = hero.get("filter_intent") if isinstance(hero, Mapping) else {}
    intent_entry = _filter_intent_entry(filter_intent, filter_key) if isinstance(filter_intent, Mapping) else None

    title = None
    if isinstance(intent_entry, Mapping):
        title = intent_entry.get("title")
    if not isinstance(title, str):
        title = hero.get("title") or "API overview"

    summary_sentence = None
    if isinstance(intent_entry, Mapping):
        summary_sentence = intent_entry.get("filter_summary")
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
    buyer_cheatsheet_content = _buyer_cheatsheet_html(page, filter_key)
    block_text = _filter_block_text(page, filter_key)
    block_text_html = block_text
    if block_text and filter_key and _is_origin_filter(filter_key):
        block_text_html = _escape(block_text)

    content_parts = [
        f"<h2 class=\"raw-material-seo-hero-title\">{_escape(title)}</h2>",
        f"<p class=\"raw-material-seo-lead raw-material-seo-hero-summary\">{_escape(summary_sentence)}</p>"
        if summary_sentence
        else "",
        f"<div class=\"raw-material-seo-filter-block\">{block_text_html}</div>"
        if block_text_html
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


def _build_origin_section(page: Mapping[str, object], filter_key: Optional[str]) -> str:
    if not filter_key or not _is_origin_filter(filter_key):
        return ""

    origin_label = _origin_label_from_key(filter_key)
    api_name = _derive_api_name(page)
    if not origin_label or not api_name:
        return ""

    hero = page.get("hero") if isinstance(page, Mapping) else None
    filter_intent = hero.get("filter_intent") if isinstance(hero, Mapping) else None
    intent_entry = _filter_intent_entry(filter_intent, filter_key) if isinstance(filter_intent, Mapping) else None

    paragraph_text = None
    if isinstance(intent_entry, Mapping):
        summary_candidate = intent_entry.get("filter_summary")
        if isinstance(summary_candidate, str) and summary_candidate.strip():
            paragraph_text = summary_candidate.strip()

    if not paragraph_text:
        filter_section = page.get("filter_section") if isinstance(page, Mapping) else None
        if isinstance(filter_section, Mapping):
            section_text = filter_section.get(filter_key)
            if isinstance(section_text, str) and section_text.strip():
                paragraph_text = section_text.strip()

    if not paragraph_text:
        return ""

    heading = f"Sourcing {api_name} API produced by suppliers from {origin_label}"
    disclaimer = (
        "<p class=\"raw-material-seo-smallprint\">Origin refers to production location; supplier headquarters may differ.</p>"
    )
    return (
        "<div class=\"raw-material-seo-section raw-material-seo-section-origin\">"
        f"<h3>{_escape(heading)}</h3>"
        f"<p>{_escape(paragraph_text)}</p>"
        f"{disclaimer}"
        "</div>"
    )


def build_filter_section_blocks(
    page: Mapping[str, object], filter_key: Optional[str] = None
) -> Dict[str, str]:
    hero_block = _build_filter_hero_block(page, filter_key)
    return {"hero": hero_block} if hero_block else {}


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

        render_source: MutableMapping[str, object] = (
            normalized_page if isinstance(normalized_page, MutableMapping) else working_copy
        )

        sections = build_filter_section_blocks(render_source, derived_filter_key)
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

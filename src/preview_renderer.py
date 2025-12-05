"""Generate structured HTML previews from API page models."""

from __future__ import annotations

import html
import random
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import re


_REFERENCE_PATTERN = re.compile(r"\[L\d+(?:,\s*L\d+)*\]")


def _clean_text(value: object) -> str:
    text = str(value)
    text = _REFERENCE_PATTERN.sub("", text)
    text = " ".join(text.split())
    return text.strip(" ,;\n\t")


def _escape(value: object) -> str:
    return html.escape(_clean_text(value))


def _merge_row_values(pairs: Sequence[Tuple[str, object]]) -> List[Tuple[str, str]]:
    merged: OrderedDict[str, List[str]] = OrderedDict()
    for label, value in pairs:
        if value is None:
            continue
        clean_value = _clean_text(value)
        if not clean_value:
            continue
        merged.setdefault(label, [])
        if clean_value not in merged[label]:
            merged[label].append(clean_value)
    return [(label, " • ".join(values)) for label, values in merged.items()]


def _table_from_pairs(pairs: Sequence[Tuple[str, object]]) -> str:
    rows = [
        (
            "<tr class=\"raw-material-seo-table-row raw-material-seo-row\">"
            f"<th class=\"raw-material-seo-table-label raw-material-seo-label raw-material-seo-cell\">{_escape(label)}</th>"
            f"<td class=\"raw-material-seo-table-value raw-material-seo-value raw-material-seo-cell\">{_escape(value)}</td>"
            "</tr>"
        )
        for label, value in pairs
        if value
    ]
    if not rows:
        return ""

    table = f"<table class=\"raw-material-seo-data-table raw-material-seo-info-table\"><tbody>{''.join(rows)}</tbody></table>"
    return f"<div class=\"raw-material-seo-table-wrapper\">{table}</div>"


def _chip_list(items: Iterable[object]) -> str:
    chips = [
        f"<span class=\"raw-material-seo-chip raw-material-seo-list-item\">{_escape(item)}</span>"
        for item in items
        if item
    ]
    return (
        f"<div class=\"raw-material-seo-chip-list raw-material-seo-list raw-material-seo-list-inline\">{''.join(chips)}</div>"
        if chips
        else ""
    )


def _unordered_list(items: Iterable[object]) -> str:
    entries = [f"<li class=\"raw-material-seo-list-item\">{_escape(item)}</li>" for item in items if item]
    if not entries:
        return ""

    return "".join(
        [
            "<div class=\"raw-material-seo-list-wrapper\">",
            f"<ul class=\"raw-material-seo-list raw-material-seo-list-bulleted\">{''.join(entries)}</ul>",
            "</div>",
        ]
    )


def _subblock(title: str, body: str) -> str:
    if not body:
        return ""
    return (
        f"<div class=\"raw-material-seo-subblock raw-material-seo-section-block\">"
        f"<div class=\"raw-material-seo-subblock-header raw-material-seo-block-header\"><h4 class=\"raw-material-seo-subblock-title\">{_escape(title)}</h4></div>"
        f"<div class=\"raw-material-seo-subblock-body raw-material-seo-block-body\">{body}</div>"
        f"</div>"
    )


def _table_from_dicts(items: List[Mapping[str, object]], columns: List[Tuple[str, str]]) -> str:
    if not items:
        return ""
    active_columns = [label_key for label_key in columns if any(item.get(label_key[1]) for item in items)]
    if not active_columns:
        return ""
    header = "".join(
        f"<th class=\"raw-material-seo-table-label raw-material-seo-label raw-material-seo-cell\">{_escape(label)}</th>"
        for label, _ in active_columns
    )
    rows = []
    for item in items:
        cells = [
            f"<td class=\"raw-material-seo-table-value raw-material-seo-value raw-material-seo-cell\">{_escape(item.get(key, ''))}</td>"
            for _, key in active_columns
        ]
        rows.append(f"<tr class=\"raw-material-seo-table-row raw-material-seo-row\">{''.join(cells)}</tr>")
    table = (
        "<table class=\"raw-material-seo-data-table raw-material-seo-info-table\">"
        f"<thead><tr class=\"raw-material-seo-table-row raw-material-seo-row\">{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )
    return f"<div class=\"raw-material-seo-table-wrapper\">{table}</div>"


def _collapsible_panel(title: str, summary_text: str, body: str, *, open_default: bool = False) -> str:
    if not body:
        return ""
    open_attr = " open" if open_default else ""
    summary_body = _escape(summary_text) if summary_text else "View details"
    return (
        f"<details class=\"raw-material-seo-block raw-material-seo-panel raw-material-seo-panel-collapsible\"{open_attr}>"
        f"<summary class=\"raw-material-seo-panel-summary\">"
        f"<div class=\"raw-material-seo-summary-title raw-material-seo-panel-title\">{_escape(title)}</div>"
        f"<div class=\"raw-material-seo-summary-text raw-material-seo-panel-description\">{summary_body}</div>"
        f"</summary>"
        f"<div class=\"raw-material-seo-panel-body\">{body}</div>"
        f"</details>"
    )


def _facts_table(facts: Mapping[str, object]) -> str:
    entries = [
        ("Generic name", facts.get("genericName")),
        ("Molecule type", facts.get("moleculeType")),
        ("CAS", facts.get("casNumber")),
        ("DrugBank ID", facts.get("drugbankId")),
        ("Approval status", facts.get("approvalStatus")),
        ("ATC code", facts.get("atcCode")),
    ]
    cards = []
    for label, value in entries:
        if not value:
            continue
        cards.append(
            "<div class=\"raw-material-seo-fact-card raw-material-seo-row\">"
            f"<div class=\"raw-material-seo-fact-label raw-material-seo-label raw-material-seo-cell\">{_escape(label)}</div>"
            f"<div class=\"raw-material-seo-fact-value raw-material-seo-value raw-material-seo-cell\">{_escape(value)}</div>"
            "</div>"
        )
    return (
        f"<div class=\"raw-material-seo-facts-grid raw-material-seo-table-wrapper\">{''.join(cards)}</div>" if cards else ""
    )


def _build_hero_block(page: Mapping[str, object]) -> str:
    hero = page.get("hero", {}) if isinstance(page, Mapping) else {}
    title = hero.get("title") or "API overview"
    summary_sentence = hero.get("summarySentence") or hero.get("summary")
    categories = (hero.get("therapeuticCategories", []) or [])[:6]
    taxonomy = page.get("categoriesAndTaxonomy", {}) if isinstance(page, Mapping) else {}
    if not categories and isinstance(taxonomy, Mapping):
        categories = (taxonomy.get("therapeuticClasses", []) or [])[:6]
    category_chips = _chip_list(categories)

    facts_source = hero.get("facts") or page.get("facts") or {}
    facts_html = _facts_table(facts_source if isinstance(facts_source, Mapping) else {})

    primary_indications = _unordered_list(page.get("primaryIndications") or hero.get("primaryUseCases") or [])
    buyer_cheatsheet = _unordered_list((page.get("buyerCheatsheet", {}) or {}).get("bullets", []))

    content_parts = [
        f"<h2 class=\"raw-material-seo-hero-title\">{_escape(title)}</h2>",
        f"<p class=\"raw-material-seo-lead raw-material-seo-hero-summary\">{_escape(summary_sentence)}</p>" if summary_sentence else "",
        _subblock("Therapeutic categories", category_chips),
        facts_html,
        _subblock("Primary indications", primary_indications),
        _subblock("Buyer cheatsheet", buyer_cheatsheet),
    ]
    body = "".join(part for part in content_parts if part)
    return (
        f"<div class=\"raw-material-seo-hero-block raw-material-seo-section raw-material-seo-section-hero\">{body}</div>"
        if body
        else ""
    )


def _build_identification_section(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    id_section = clinical.get("identificationClassification", {}) if isinstance(clinical, Mapping) else {}
    identification = id_section.get("identification") if isinstance(id_section, Mapping) else {}
    if not identification and isinstance(page, Mapping):
        identification = page.get("identification", {})

    identifiers = identification.get("identifiers", {}) if isinstance(identification, Mapping) else {}
    merged_rows: List[Tuple[str, object]] = []
    if identification.get("genericName"):
        merged_rows.append(("Generic name", identification.get("genericName")))
    if identification.get("moleculeType"):
        merged_rows.append(("Molecule type", identification.get("moleculeType")))
    synonyms = identification.get("synonyms", []) if isinstance(identification, Mapping) else []
    if synonyms:
        merged_rows.append(("Synonyms", ", ".join([_clean_text(s) for s in synonyms if s])))

    if identifiers.get("casNumber"):
        merged_rows.append(("CAS", identifiers.get("casNumber")))
    if identifiers.get("unii"):
        merged_rows.append(("UNII", identifiers.get("unii")))
    if identifiers.get("drugbankId"):
        merged_rows.append(("DrugBank ID", identifiers.get("drugbankId")))
    chemistry = id_section.get("chemistry") if isinstance(id_section, Mapping) else {}
    if not chemistry and isinstance(page, Mapping):
        chemistry = page.get("chemistry", {})
    for label, key in (
        ("Formula", "formula"),
        ("Average MW", "averageMolecularWeight"),
        ("Monoisotopic mass", "monoisotopicMass"),
        ("logP", "logP"),
    ):
        if isinstance(chemistry, Mapping) and chemistry.get(key):
            merged_rows.append((label, chemistry.get(key)))

    content_parts = [
        _subblock("Identification & chemistry", _table_from_pairs(_merge_row_values(merged_rows))),
    ]
    body = "".join(part for part in content_parts if part)
    return (
        "<section class=\"raw-material-seo-section raw-material-seo-section-identification\">"
        f"<div class=\"raw-material-seo-section-body\">{body}</div>"
        "</section>"
        if body
        else ""
    )


def _regulatory_classification_rows(
    regulatory_classification: Mapping[str, object] | None, taxonomy: Mapping[str, object]
) -> List[Tuple[str, object]]:
    reg_rows: List[Tuple[str, object]] = []

    groups = regulatory_classification.get("groups", []) if isinstance(regulatory_classification, Mapping) else []
    if groups:
        reg_rows.append(("Groups", " • ".join([_clean_text(group) for group in groups if group])))

    therapeutic_classes = (taxonomy.get("therapeuticClasses") if isinstance(taxonomy, Mapping) else []) or []
    if isinstance(regulatory_classification, Mapping) and regulatory_classification.get("therapeuticClasses"):
        therapeutic_classes = regulatory_classification.get("therapeuticClasses") or therapeutic_classes
    if therapeutic_classes:
        reg_rows.append(("Therapeutic class", " • ".join(tc for tc in therapeutic_classes[:6] if tc)))

    classification = taxonomy.get("classification") if isinstance(taxonomy, Mapping) else None
    if isinstance(regulatory_classification, Mapping) and regulatory_classification.get("classification"):
        classification = regulatory_classification.get("classification")
    if isinstance(classification, Mapping):
        for key, value in classification.items():
            normalized_key = key.lower().replace(" ", "_")
            if normalized_key in {"alternative_parents", "substituents"}:
                continue
            if value:
                reg_rows.append((key.replace("_", " ").title(), value))

    atc_codes = taxonomy.get("atcCodes") if isinstance(taxonomy, Mapping) else []
    if isinstance(regulatory_classification, Mapping) and regulatory_classification.get("atcCodes"):
        atc_codes = regulatory_classification.get("atcCodes") or atc_codes
    if atc_codes:
        reg_rows.append(
            (
                "ATC code",
                " • ".join(
                    code.get("code") for code in atc_codes if isinstance(code, Mapping) and code.get("code")
                ),
            )
        )

    return _merge_row_values(reg_rows)


def _build_pharmacology_section(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    pharmacology_container: Mapping[str, object] | None = None
    if isinstance(clinical, Mapping):
        pharmacology_container = clinical.get("pharmacologyTargets") or clinical.get("pharmacology")
    if not pharmacology_container and isinstance(page, Mapping):
        pharmacology_container = page.get("pharmacologyTargets") or page.get("pharmacology")

    pharmacology: Mapping[str, object] = {}
    if isinstance(pharmacology_container, Mapping):
        pharmacology = (
            pharmacology_container.get("pharmacology")
            if "pharmacology" in pharmacology_container
            else pharmacology_container
        )

    rows = []
    summary_value = None
    if isinstance(pharmacology_container, Mapping):
        summary_value = pharmacology_container.get("summary") or pharmacology_container.get("highLevelSummary")
    if not summary_value and pharmacology.get("highLevelSummary"):
        summary_value = pharmacology.get("highLevelSummary")
    if pharmacology.get("summary"):
        rows.append(("Summary", pharmacology.get("summary")))
    elif summary_value:
        rows.append(("Summary", summary_value))
    if pharmacology.get("mechanismOfAction"):
        rows.append(("Mechanism", pharmacology.get("mechanismOfAction")))
    if pharmacology.get("pharmacodynamics"):
        rows.append(("Pharmacodynamics", pharmacology.get("pharmacodynamics")))
    summary_table = _table_from_pairs(_merge_row_values(rows))

    targets_source = None
    if isinstance(pharmacology_container, Mapping) and pharmacology_container.get("targets") is not None:
        targets_source = pharmacology_container.get("targets")
    elif pharmacology.get("targets") is not None:
        targets_source = pharmacology.get("targets")
    targets = targets_source or []
    targets_table = _table_from_dicts(
        targets if isinstance(targets, list) else [],
        [("Target", "name"), ("Organism", "organism"), ("Actions", "actions")],
    )

    content = "".join(
        part
        for part in [
            _subblock("Pharmacology", summary_table),
            _subblock("Targets", targets_table),
        ]
        if part
    )
    return (
        "<section class=\"raw-material-seo-section raw-material-seo-section-pharmacology\">"
        f"<div class=\"raw-material-seo-section-body\">{content}</div>"
        "</section>"
        if content
        else ""
    )


def _build_adme_section(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    adme = clinical.get("admePk", {}) if isinstance(clinical, Mapping) else {}
    if not adme and isinstance(page, Mapping):
        adme = page.get("admePk", {})

    table_data = adme.get("table") if isinstance(adme, Mapping) else adme
    rows = []
    for label, key in (
        ("Absorption", "absorption"),
        ("Half-life", "halfLife"),
        ("Protein binding", "proteinBinding"),
        ("Metabolism", "metabolism"),
        ("Elimination", "routeOfElimination"),
        ("Volume of distribution", "volumeOfDistribution"),
        ("Clearance", "clearance"),
    ):
        if isinstance(table_data, Mapping) and table_data.get(key):
            rows.append((label, table_data.get(key)))
    table_html = _table_from_pairs(rows)

    body = _subblock("ADME / PK", table_html)
    return (
        "<section class=\"raw-material-seo-section raw-material-seo-section-adme\">"
        f"<div class=\"raw-material-seo-section-body\">{body}</div>"
        "</section>"
        if body
        else ""
    )


def _build_safety_section(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    safety: Mapping[str, object] | None = {}
    if isinstance(clinical, Mapping):
        safety = clinical.get("safetyRisks") or clinical.get("safety") or {}
    if not safety and isinstance(page, Mapping):
        safety = page.get("safetyRisks") or page.get("safety") or {}

    safety_rows = []
    if safety.get("toxicity"):
        safety_rows.append(("Toxicity", safety.get("toxicity")))
    safety_table = _table_from_pairs(safety_rows)
    safety_bullets = _unordered_list(safety.get("highLevelWarnings", []))
    body = _subblock("Safety", safety_table + safety_bullets)
    return (
        "<section class=\"raw-material-seo-section raw-material-seo-section-safety\">"
        f"<div class=\"raw-material-seo-section-body\">{body}</div>"
        "</section>"
        if body
        else ""
    )


def _build_formulation_section(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    formulation = clinical.get("formulationHandling", {}) if isinstance(clinical, Mapping) else {}
    if not formulation and isinstance(page, Mapping):
        formulation = page.get("formulationNotes", {})

    notes = formulation.get("notes") if isinstance(formulation, Mapping) else None
    bullets = formulation.get("bullets") if isinstance(formulation, Mapping) else None
    values: List[str] = []
    if isinstance(notes, list):
        values.extend(notes)
    elif notes:
        values.append(notes)
    if isinstance(bullets, list):
        values.extend(bullets)
    body = _subblock("Formulation & handling", _unordered_list(values))
    return (
        "<section class=\"raw-material-seo-section raw-material-seo-section-formulation\">"
        f"<div class=\"raw-material-seo-section-body\">{body}</div>"
        "</section>"
        if body
        else ""
    )


def _build_regulatory_section(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    regulatory = clinical.get("regulatoryMarket", {}) if isinstance(clinical, Mapping) else {}
    if not regulatory and isinstance(page, Mapping):
        regulatory = page.get("regulatoryAndMarket", {})

    reg_rows = []
    if regulatory.get("summary"):
        reg_rows.append(("Lifecycle", regulatory.get("summary")))
    elif regulatory.get("lifecycleSummary"):
        reg_rows.append(("Lifecycle", regulatory.get("lifecycleSummary")))
    reg_table = _table_from_pairs(reg_rows)

    markets = _chip_list(regulatory.get("markets", []))
    taxonomy = page.get("categoriesAndTaxonomy", {}) if isinstance(page, Mapping) else {}
    classification_rows = _regulatory_classification_rows(
        regulatory.get("regulatoryClassification") if isinstance(regulatory, Mapping) else {}, taxonomy
    )
    classification_table = _table_from_pairs(classification_rows)
    label_highlights = _unordered_list(regulatory.get("labelHighlights", []))

    supply = regulatory.get("supplyChain", {}) if isinstance(regulatory, Mapping) else {}
    if not supply and isinstance(page, Mapping):
        supply = page.get("suppliersAndManufacturing", {})
    supply_rows = []
    if isinstance(supply, Mapping) and supply.get("supplyChainSummary"):
        supply_rows.append(("Supply chain", supply.get("supplyChainSummary")))
    if isinstance(supply, Mapping) and supply.get("externalManufacturingNotes"):
        supply_rows.append(("External notes", supply.get("externalManufacturingNotes")))
    supply_table = _table_from_pairs(supply_rows)
    manufacturers = _chip_list(supply.get("manufacturers", []) if isinstance(supply, Mapping) else [])

    content_parts = [
        _subblock("Regulatory status", reg_table + markets),
        _subblock("Regulatory classification", classification_table),
        _subblock("Label highlights", label_highlights),
        _subblock("Supply chain", supply_table + manufacturers),
    ]
    body = "".join(part for part in content_parts if part)
    return (
        "<section class=\"raw-material-seo-section raw-material-seo-section-regulatory\">"
        f"<div class=\"raw-material-seo-section-body\">{body}</div>"
        "</section>"
        if body
        else ""
    )


def _build_clinical_overview_content(page: Mapping[str, object]) -> str:
    clinical = page.get("clinicalOverview", {}) if isinstance(page, Mapping) else {}
    overview = page.get("overview", {}) if isinstance(page, Mapping) else {}
    description = clinical.get("longDescription") or overview.get("description")

    if not description:
        return ""

    return (
        "<section class=\"raw-material-seo-section raw-material-seo-section-overview\">"
        "<div class=\"raw-material-seo-section-body raw-material-seo-long-description\">"
        f"<p class=\"raw-material-seo-overview-text\">{_escape(description)}</p>"
        "</div>"
        "</section>"
    )


def _build_clinical_overview_block(page: Mapping[str, object]) -> str:
    clinical = page.get("clinicalOverview", {}) if isinstance(page, Mapping) else {}
    overview = page.get("overview", {}) if isinstance(page, Mapping) else {}
    summary_text = clinical.get("summary") or overview.get("summary")
    description_block = _build_clinical_overview_content(page)

    if not description_block:
        return ""

    return _collapsible_panel("Clinical overview", summary_text or "Key takeaway", description_block, open_default=False)


def _build_identification_panel(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    body = _build_identification_section(clinical, page)
    return _collapsible_panel(
        "Identification & classification",
        "Identity, classification, and formats",
        body,
    )


def _build_pharmacology_targets_panel(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    pharmacology_container = clinical.get("pharmacologyTargets", {}) if isinstance(clinical, Mapping) else {}
    if not pharmacology_container and isinstance(page, Mapping):
        pharmacology_container = page.get("pharmacologyTargets", {}) or page.get("pharmacology", {})
    summary_text = None
    if isinstance(pharmacology_container, Mapping):
        summary_text = pharmacology_container.get("summary") or pharmacology_container.get("highLevelSummary")
    body = _build_pharmacology_section(clinical, page)
    return _collapsible_panel("Pharmacology & targets", summary_text or "Mechanism and targets", body)


def _build_adme_panel(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    body = _build_adme_section(clinical, page)
    return _collapsible_panel("ADME & PK", "Absorption, distribution, metabolism, excretion", body)


def _build_formulation_panel(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    body = _build_formulation_section(clinical, page)
    return _collapsible_panel("Formulation & handling", "Form factors and handling notes", body)


def _build_regulatory_panel(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    body = _build_regulatory_section(clinical, page)
    return _collapsible_panel("Regulatory & market", "Lifecycle, approvals, and supply chain", body)


def _build_safety_panel(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    body = _build_safety_section(clinical, page)
    return _collapsible_panel("Safety & risks", "Toxicity and warnings", body)


def _build_seo_block(page: Mapping[str, object]) -> str:
    seo = page.get("seo", {}) if isinstance(page, Mapping) else {}
    metadata = page.get("metadata", {}) if isinstance(page, Mapping) else {}

    seo_rows = []
    if seo.get("title"):
        seo_rows.append(("SEO Title", seo.get("title")))
    if seo.get("metaDescription"):
        seo_rows.append(("Meta Description", seo.get("metaDescription")))
    seo_table = _table_from_pairs(seo_rows)
    keywords = _chip_list(seo.get("keywords", []))
    meta_rows = []
    if metadata.get("drugbankId"):
        meta_rows.append(("DrugBank ID", metadata.get("drugbankId")))
    if metadata.get("casNumber"):
        meta_rows.append(("CAS", metadata.get("casNumber")))
    if metadata.get("unii"):
        meta_rows.append(("UNII", metadata.get("unii")))
    meta_table = _table_from_pairs(meta_rows)

    content_parts = [
        _subblock("SEO Copy", seo_table),
        _subblock("Keywords", keywords),
        _subblock("Identifiers", meta_table),
    ]
    content = "".join(part for part in content_parts if part)
    return _collapsible_panel("SEO & metadata", "Search preview", content)


def _page_wrapper(page_name: str, content: str) -> str:
    return (
        f"<section class=\"raw-material-seo-api-page-preview raw-material-seo-section raw-material-seo-section-page\" data-api-name=\"{_escape(page_name)}\">"
        f"<header class=\"raw-material-seo-section-header raw-material-seo-page-header\"><h2 class=\"raw-material-seo-section-title raw-material-seo-page-title\">{_escape(page_name)}</h2></header>"
        f"{content}"
        f"</section>"
    )


def build_section_blocks(page: Mapping[str, object]) -> Dict[str, str]:
    """Return structured HTML fragments for a single API page.

    The fragments intentionally omit global styling so they can be stored and
    styled later. Section keys follow the logical groupings used throughout
    the generator.
    """

    clinical = page.get("clinicalOverview", {}) if isinstance(page, Mapping) else {}
    sections = {
        "hero": _build_hero_block(page),
        "overview": _build_clinical_overview_content(page),
        "identification": _build_identification_section(clinical, page),
        "pharmacology": _build_pharmacology_section(clinical, page),
        "adme_pk": _build_adme_section(clinical, page),
        "formulation": _build_formulation_section(clinical, page),
        "regulatory": _build_regulatory_section(clinical, page),
        "safety": _build_safety_section(clinical, page),
    }
    return {key: value for key, value in sections.items() if value}


def _is_semaglutide(page_key: object, page: Mapping[str, object]) -> bool:
    def _matches(value: object) -> bool:
        if not value:
            return False
        text = str(value).strip().lower()
        return text in {"db01323", "semaglutide"}

    if _matches(page_key):
        return True

    hero_title = page.get("hero", {}).get("title") if isinstance(page, Mapping) else None
    identifiers = (
        page.get("identification", {}).get("identifiers", {}) if isinstance(page, Mapping) else {}
    )
    metadata = page.get("metadata", {}) if isinstance(page, Mapping) else {}
    facts = page.get("facts", {}) if isinstance(page, Mapping) else {}

    return any(
        _matches(value)
        for value in (
            hero_title,
            identifiers.get("drugbankId") if isinstance(identifiers, Mapping) else None,
            metadata.get("drugbankId") if isinstance(metadata, Mapping) else None,
            facts.get("drugbankId") if isinstance(facts, Mapping) else None,
        )
    )


def _select_preview_pages(
    page_entries: Iterable[Tuple[object, Mapping[str, object]]], limit: int = 3
) -> List[Tuple[object, Mapping[str, object]]]:
    normalized: List[Tuple[object, Mapping[str, object]]] = []
    for page_key, page in page_entries:
        if isinstance(page, Mapping) and "raw" in page:
            page = page.get("raw", {})
        if not isinstance(page, Mapping):
            continue
        normalized.append((page_key, page))

    if not normalized:
        return []

    selected: List[Tuple[object, Mapping[str, object]]] = []
    semaglutide_entry = next((entry for entry in normalized if _is_semaglutide(*entry)), None)
    if semaglutide_entry:
        selected.append(semaglutide_entry)

    remaining = [entry for entry in normalized if entry != semaglutide_entry]
    rng = random.Random(17)
    remaining_needed = min(limit - len(selected), len(remaining))
    if remaining_needed > 0:
        selected.extend(rng.sample(remaining, k=remaining_needed))

    return selected


def generate_html_preview(api_pages: Dict[str, object]) -> str:
    """Render a compact HTML preview for API page models."""

    base_styles = """
    <style>
    body { font-family: Arial, sans-serif; margin: 16px; background: #f8fafc; color: #0f172a; }
    .raw-material-seo-api-page-preview { border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 16px; background: #ffffff; box-shadow: 0 2px 4px rgba(15, 23, 42, 0.06); }
    .raw-material-seo-api-page-preview .raw-material-seo-section-header { padding: 12px 16px; border-bottom: 1px solid #e5e7eb; background: #f1f5f9; }
    .raw-material-seo-api-page-preview .raw-material-seo-page-title { margin: 0; font-size: 18px; }
    .raw-material-seo-hero-block { padding: 16px; background: linear-gradient(135deg, #eef2ff 0%, #e0f2fe 100%); border-bottom: 1px solid #d9e0ef; }
    .raw-material-seo-hero-title { margin: 0 0 6px 0; }
    .raw-material-seo-hero-block .raw-material-seo-lead { margin: 4px 0 12px 0; font-size: 14px; color: #0f172a; }
    .raw-material-seo-block { border-top: 1px solid #e5e7eb; }
    .raw-material-seo-block summary { cursor: pointer; padding: 10px 14px; font-weight: 600; background: #ffffff; display: flex; flex-direction: column; gap: 4px; }
    .raw-material-seo-block[open] > summary { background: #eef2ff; }
    .raw-material-seo-block[open] > summary .raw-material-seo-summary-text { display: none; }
    .raw-material-seo-summary-title { font-size: 14px; text-transform: uppercase; letter-spacing: 0.02em; color: #475569; }
    .raw-material-seo-summary-text { font-size: 13px; color: #0f172a; }
    .raw-material-seo-subblock { padding: 0 16px 12px; }
    .raw-material-seo-subblock-title { margin: 8px 0 4px; font-size: 14px; }
    .raw-material-seo-subblock-body { font-size: 13px; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
    th, td { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; font-size: 12px; }
    ul { margin: 4px 0 8px 18px; padding: 0; }
    .raw-material-seo-chip-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 8px 0; }
    .raw-material-seo-chip { background: #e0f2fe; color: #0f172a; padding: 2px 8px; border-radius: 12px; font-size: 11px; }
    .raw-material-seo-market-group { margin-bottom: 10px; }
    .raw-material-seo-long-description { padding: 0 16px; font-size: 13px; color: #0f172a; }
    .raw-material-seo-long-description p { margin: 0 0 12px 0; }
    .raw-material-seo-facts-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; padding: 8px 0 12px; }
    .raw-material-seo-fact-card { background: #ffffff; border: 1px solid #d9e0ef; border-radius: 8px; padding: 10px 12px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }
    .raw-material-seo-fact-label { font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }
    .raw-material-seo-fact-value { font-size: 14px; font-weight: 600; color: #0f172a; word-break: break-word; }
    </style>
    """

    page_entries = api_pages.items() if isinstance(api_pages, Mapping) else enumerate(api_pages)
    selected_pages = _select_preview_pages(page_entries, limit=3)

    page_sections: List[str] = []
    for page_key, page in selected_pages:
        page_name = page.get("hero", {}).get("title") or str(page_key)
        blocks = [
            _build_hero_block(page),
            _build_clinical_overview_block(page),
            _build_identification_panel(page.get("clinicalOverview", {}), page),
            _build_pharmacology_targets_panel(page.get("clinicalOverview", {}), page),
            _build_adme_panel(page.get("clinicalOverview", {}), page),
            _build_formulation_panel(page.get("clinicalOverview", {}), page),
            _build_regulatory_panel(page.get("clinicalOverview", {}), page),
            _build_safety_panel(page.get("clinicalOverview", {}), page),
            _build_seo_block(page),
        ]
        content = "".join(block for block in blocks if block)
        if content:
            page_sections.append(_page_wrapper(page_name, content))

    body = "".join(page_sections)
    return f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">{base_styles}</head><body>{body}</body></html>"


def save_html_preview(api_pages: Dict[str, object], output_path: str) -> str:
    """Generate the preview HTML and persist it to ``output_path``.

    Args:
        api_pages: Parsed JSON content from ``api_pages.json``.
        output_path: Destination file path for the generated HTML preview.

    Returns:
        The generated HTML string for further reuse.
    """

    html_preview = generate_html_preview(api_pages)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html_preview, encoding="utf-8")
    return html_preview

"""Generate structured HTML previews from API page models."""

from __future__ import annotations

import html
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
    rows = [f"<tr><th>{_escape(label)}</th><td>{_escape(value)}</td></tr>" for label, value in pairs if value]
    return f"<table>{''.join(rows)}</table>" if rows else ""


def _chip_list(items: Iterable[object]) -> str:
    chips = [f"<span class=\"chip\">{_escape(item)}</span>" for item in items if item]
    return f"<div class=\"chip-list\">{''.join(chips)}</div>" if chips else ""


def _unordered_list(items: Iterable[object]) -> str:
    entries = [f"<li>{_escape(item)}</li>" for item in items if item]
    return f"<ul>{''.join(entries)}</ul>" if entries else ""


def _unordered_html_list(items: Iterable[str]) -> str:
    entries = [f"<li>{item}</li>" for item in items if item]
    return f"<ul>{''.join(entries)}</ul>" if entries else ""


def _anchor(label: str, url: str) -> str:
    if not label or not url:
        return ""
    return f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{_escape(label)}</a>'


def _article_entry(article: Mapping[str, object] | object) -> str:
    citation = article.get("citation") if isinstance(article, Mapping) else None
    pubmed_id = None
    ref_id = None
    if isinstance(article, Mapping):
        pubmed_id = article.get("pubmed_id") or article.get("pubmedId")
        ref_id = article.get("ref_id") or article.get("refId")

    label = citation or pubmed_id or ref_id
    url: str | None = None
    if pubmed_id:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/"
    elif isinstance(ref_id, str) and ref_id.startswith("http"):
        url = ref_id

    if url and label:
        return _anchor(str(label), url)
    return _escape(label) if label else ""


def _link_entry(link: Mapping[str, object] | object) -> str:
    if not isinstance(link, Mapping):
        return ""
    label = link.get("title") or link.get("url")
    url = link.get("url")
    if url and label:
        return _anchor(str(label), str(url))
    return _escape(label) if label else ""


def _subblock(title: str, body: str) -> str:
    if not body:
        return ""
    return (
        f"<div class=\"subblock\">"
        f"<div class=\"subblock-header\"><h4>{_escape(title)}</h4></div>"
        f"<div class=\"subblock-body\">{body}</div>"
        f"</div>"
    )


def _table_from_dicts(items: List[Mapping[str, object]], columns: List[Tuple[str, str]]) -> str:
    if not items:
        return ""
    active_columns = [label_key for label_key in columns if any(item.get(label_key[1]) for item in items)]
    if not active_columns:
        return ""
    header = "".join(f"<th>{_escape(label)}</th>" for label, _ in active_columns)
    rows = []
    for item in items:
        cells = [f"<td>{_escape(item.get(key, ''))}</td>" for _, key in active_columns]
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _collapsible_panel(title: str, summary_text: str, body: str, *, open_default: bool = False) -> str:
    if not body:
        return ""
    open_attr = " open" if open_default else ""
    summary_body = _escape(summary_text) if summary_text else "View details"
    return (
        f"<details class=\"block\"{open_attr}>"
        f"<summary><div class=\"summary-title\">{_escape(title)}</div>"
        f"<div class=\"summary-text\">{summary_body}</div></summary>"
        f"{body}</details>"
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
            "<div class=\"fact-card\">"
            f"<div class=\"fact-label\">{_escape(label)}</div>"
            f"<div class=\"fact-value\">{_escape(value)}</div>"
            "</div>"
        )
    return f"<div class=\"facts-grid\">{''.join(cards)}</div>" if cards else ""


def _build_hero_block(page: Mapping[str, object]) -> str:
    hero = page.get("hero", {}) if isinstance(page, Mapping) else {}
    title = hero.get("title") or "API overview"
    summary_sentence = hero.get("summarySentence") or hero.get("summary")
    categories = hero.get("therapeuticCategories", [])
    taxonomy = page.get("categoriesAndTaxonomy", {}) if isinstance(page, Mapping) else {}
    if not categories and isinstance(taxonomy, Mapping):
        categories = taxonomy.get("therapeuticClasses", []) or []
    category_chips = _chip_list(categories)

    facts_source = hero.get("facts") or page.get("facts") or {}
    facts_html = _facts_table(facts_source if isinstance(facts_source, Mapping) else {})

    primary_indications = _unordered_list(page.get("primaryIndications") or hero.get("primaryUseCases") or [])
    buyer_cheatsheet = _unordered_list((page.get("buyerCheatsheet", {}) or {}).get("bullets", []))

    content_parts = [
        f"<h2>{_escape(title)}</h2>",
        f"<p class=\"lead\">{_escape(summary_sentence)}</p>" if summary_sentence else "",
        _subblock("Therapeutic categories", category_chips),
        facts_html,
        _subblock("Primary indications", primary_indications),
        _subblock("Buyer cheatsheet", buyer_cheatsheet),
    ]
    body = "".join(part for part in content_parts if part)
    return f"<div class=\"hero-block\">{body}</div>" if body else ""


def _brands_block(products: Mapping[str, object]) -> str:
    brands_by_market = products.get("brandsByMarket") if isinstance(products, Mapping) else None
    brand_lists: List[str] = []
    if isinstance(brands_by_market, Mapping):
        for market, brands in brands_by_market.items():
            if not brands:
                continue
            entries = []
            for brand in brands:
                if not isinstance(brand, Mapping):
                    continue
                brand_label = brand.get("brand") or brand.get("dosageForm") or "Brand"
                details: List[str] = []
                if brand.get("dosageForm"):
                    details.append(str(brand.get("dosageForm")))
                if brand.get("strength"):
                    details.append(str(brand.get("strength")))
                if brand.get("route"):
                    details.append(str(brand.get("route")))
                details_text = " • ".join(details)
                entries.append(
                    f"<li><strong>{_escape(brand_label)}</strong>{f' — {details_text}' if details_text else ''}</li>"
                )
            if entries:
                brand_lists.append(
                    f"<div class=\"market-group\"><div class=\"subblock-header\">{_escape(market)}</div><ul>{''.join(entries)}</ul></div>"
                )
    return "".join(brand_lists)


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
    groups = identification.get("groups", []) if isinstance(identification, Mapping) else []
    if groups:
        merged_rows.append(("Group", " • ".join([_clean_text(group) for group in groups if group])))
    synonyms = identification.get("synonyms", []) if isinstance(identification, Mapping) else []
    if synonyms:
        merged_rows.append(("Synonyms", ", ".join([_clean_text(s) for s in synonyms if s])))

    if identifiers.get("casNumber"):
        merged_rows.append(("CAS", identifiers.get("casNumber")))
    if identifiers.get("unii"):
        merged_rows.append(("UNII", identifiers.get("unii")))
    if identifiers.get("drugbankId"):
        merged_rows.append(("DrugBank ID", identifiers.get("drugbankId")))
    if identifiers.get("external"):
        merged_rows.append(("External", identifiers.get("external")))

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

    regulatory_class = id_section.get("regulatoryClassification") if isinstance(id_section, Mapping) else {}
    taxonomy = page.get("categoriesAndTaxonomy", {}) if isinstance(page, Mapping) else {}
    reg_rows: List[Tuple[str, object]] = []
    if isinstance(regulatory_class, Mapping):
        if regulatory_class.get("approvalStatus"):
            reg_rows.append(("Approval status", regulatory_class.get("approvalStatus")))
        if regulatory_class.get("markets"):
            reg_rows.append(("Markets", ", ".join(regulatory_class.get("markets") or [])))
    therapeutic_classes = taxonomy.get("therapeuticClasses") if isinstance(taxonomy, Mapping) else []
    if therapeutic_classes:
        reg_rows.append(("Therapeutic class", " • ".join(tc for tc in therapeutic_classes if tc)))
    classification = taxonomy.get("classification") if isinstance(taxonomy, Mapping) else None
    if isinstance(regulatory_class, Mapping) and regulatory_class.get("classification"):
        classification = regulatory_class.get("classification")
    if isinstance(classification, Mapping):
        for key, value in classification.items():
            if value:
                reg_rows.append((key.replace("_", " ").title(), value))
    atc_codes = taxonomy.get("atcCodes") if isinstance(taxonomy, Mapping) else []
    if atc_codes:
        reg_rows.append(
            (
                "ATC code",
                " • ".join(
                    code.get("code") for code in atc_codes if isinstance(code, Mapping) and code.get("code")
                ),
            )
        )

    exp_props = chemistry.get("experimentalProperties") or [] if isinstance(chemistry, Mapping) else []
    experimental_table = _table_from_dicts(
        exp_props if isinstance(exp_props, list) else [],
        [("Name", "name"), ("Value", "value")],
    )

    products = id_section.get("productsAndDosageForms") if isinstance(id_section, Mapping) else {}
    if not products and isinstance(page, Mapping):
        products = page.get("productsAndDosageForms", {})
    dosage_forms = products.get("dosageForms") or [] if isinstance(products, Mapping) else []
    dosage_table = _table_from_dicts(
        dosage_forms if isinstance(dosage_forms, list) else [],
        [("Form", "form"), ("Route", "route"), ("Strength", "strength")],
    )
    brand_block = _brands_block(products if isinstance(products, Mapping) else {})

    content_parts = [
        _subblock("Identification & chemistry", _table_from_pairs(_merge_row_values(merged_rows))),
        _subblock("Regulatory classification", _table_from_pairs(_merge_row_values(reg_rows))),
        _subblock("Experimental properties", experimental_table),
        _subblock("Products & dosage forms", dosage_table + brand_block),
    ]
    return "".join(part for part in content_parts if part)


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
    if pharmacology.get("details"):
        for entry in pharmacology.get("details"):
            if isinstance(entry, Mapping) and entry.get("value"):
                rows.append((entry.get("label") or "Detail", entry.get("value")))
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

    return "".join(
        part
        for part in [
            _subblock("Pharmacology", summary_table),
            _subblock("Targets", targets_table),
        ]
        if part
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

    return _subblock("ADME / PK", table_html)


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
    return _subblock("Safety", safety_table + safety_bullets)


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
    return _subblock("Formulation & handling", _unordered_list(values))


def _build_regulatory_section(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    regulatory = clinical.get("regulatoryMarket", {}) if isinstance(clinical, Mapping) else {}
    if not regulatory and isinstance(page, Mapping):
        regulatory = page.get("regulatoryAndMarket", {})

    reg_rows = []
    if regulatory.get("approvalStatus"):
        reg_rows.append(("Approval status", regulatory.get("approvalStatus")))
    if regulatory.get("summary"):
        reg_rows.append(("Lifecycle", regulatory.get("summary")))
    elif regulatory.get("lifecycleSummary"):
        reg_rows.append(("Lifecycle", regulatory.get("lifecycleSummary")))
    reg_table = _table_from_pairs(reg_rows)

    markets = _chip_list(regulatory.get("markets", []))
    label_highlights = _unordered_list(regulatory.get("labelHighlights", []))

    patents = regulatory.get("patents") or []
    patents_table = _table_from_dicts(
        patents if isinstance(patents, list) else [],
        [
            ("Number", "number"),
            ("Country", "country"),
            ("Approved", "approvedDate"),
            ("Expires", "expiresDate"),
            ("Pediatric Ext.", "pediatricExtension"),
        ],
    )

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
    packagers = _chip_list(supply.get("packagers", []) if isinstance(supply, Mapping) else [])

    content_parts = [
        _subblock("Regulatory status", reg_table + markets),
        _subblock("Label highlights", label_highlights),
        _subblock("Patents", patents_table),
        _subblock("Supply chain", supply_table + manufacturers + packagers),
    ]
    return "".join(part for part in content_parts if part)


def _build_references_section(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    references = clinical.get("references", {}) if isinstance(clinical, Mapping) else {}
    if not references and isinstance(page, Mapping):
        references = page.get("references", {})

    articles = references.get("scientificArticles") or [] if isinstance(references, Mapping) else []
    article_items = [_article_entry(article) for article in articles]
    articles_list = _unordered_html_list(article_items)

    links = references.get("regulatoryLinks") or [] if isinstance(references, Mapping) else []
    other_links = references.get("otherLinks") or [] if isinstance(references, Mapping) else []
    link_entries = [_link_entry(link) for link in [*links, *other_links]]
    links_list = _unordered_html_list(link_entries)

    return "".join(
        part
        for part in [
            _subblock("Key references", articles_list),
            _subblock("Links", links_list),
        ]
        if part
    )


def _build_experimental_section(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    experimental = clinical.get("experimentalProperties", {}) if isinstance(clinical, Mapping) else {}
    if not experimental and isinstance(page, Mapping):
        experimental = page.get("experimentalProperties", {})

    properties = experimental.get("properties") if isinstance(experimental, Mapping) else []
    properties_table = _table_from_dicts(
        properties if isinstance(properties, list) else [],
        [("Property", "name"), ("Value", "value")],
    )
    return _subblock("Experimental properties", properties_table)


def _build_clinical_overview_block(page: Mapping[str, object]) -> str:
    clinical = page.get("clinicalOverview", {}) if isinstance(page, Mapping) else {}
    overview = page.get("overview", {}) if isinstance(page, Mapping) else {}
    summary_text = clinical.get("summary") or overview.get("summary")
    description = clinical.get("longDescription") or overview.get("description")

    description_block = ""
    if description:
        description_block += f"<div class=\"long-description\"><p>{_escape(description)}</p></div>"

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


def _build_references_panel(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    body = _build_references_section(clinical, page)
    return _collapsible_panel("References", "Source articles and links", body)


def _build_experimental_panel(clinical: Mapping[str, object], page: Mapping[str, object]) -> str:
    body = _build_experimental_section(clinical, page)
    return _collapsible_panel("Experimental properties", "Assays and reported properties", body)


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
        f"<section class=\"api-page-preview\" data-api-name=\"{_escape(page_name)}\">"
        f"<header><h2>{_escape(page_name)}</h2></header>"
        f"{content}"
        f"</section>"
    )


def generate_html_preview(api_pages: Dict[str, object]) -> str:
    """Render a compact HTML preview for API page models."""

    base_styles = """
    <style>
    body { font-family: Arial, sans-serif; margin: 16px; background: #f8fafc; color: #0f172a; }
    .api-page-preview { border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 16px; background: #ffffff; box-shadow: 0 2px 4px rgba(15, 23, 42, 0.06); }
    .api-page-preview header { padding: 12px 16px; border-bottom: 1px solid #e5e7eb; background: #f1f5f9; }
    .api-page-preview h2 { margin: 0; font-size: 18px; }
    .hero-block { padding: 16px; background: linear-gradient(135deg, #eef2ff 0%, #e0f2fe 100%); border-bottom: 1px solid #d9e0ef; }
    .hero-block h2 { margin: 0 0 6px 0; }
    .hero-block .lead { margin: 4px 0 12px 0; font-size: 14px; color: #0f172a; }
    .block { border-top: 1px solid #e5e7eb; }
    .block summary { cursor: pointer; padding: 10px 14px; font-weight: 600; background: #ffffff; display: flex; flex-direction: column; gap: 4px; }
    .block[open] > summary { background: #eef2ff; }
    .block[open] > summary .summary-text { display: none; }
    .summary-title { font-size: 14px; text-transform: uppercase; letter-spacing: 0.02em; color: #475569; }
    .summary-text { font-size: 13px; color: #0f172a; }
    .subblock { padding: 0 16px 12px; }
    .subblock-header h4 { margin: 8px 0 4px; font-size: 14px; }
    .subblock-body { font-size: 13px; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
    th, td { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; font-size: 12px; }
    ul { margin: 4px 0 8px 18px; padding: 0; }
    .chip-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 8px 0; }
    .chip { background: #e0f2fe; color: #0f172a; padding: 2px 8px; border-radius: 12px; font-size: 11px; }
    .market-group { margin-bottom: 10px; }
    .long-description { padding: 0 16px; font-size: 13px; color: #0f172a; }
    .long-description p { margin: 0 0 12px 0; }
    .facts-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; padding: 8px 0 12px; }
    .fact-card { background: #ffffff; border: 1px solid #d9e0ef; border-radius: 8px; padding: 10px 12px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }
    .fact-label { font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }
    .fact-value { font-size: 14px; font-weight: 600; color: #0f172a; word-break: break-word; }
    </style>
    """

    page_entries = api_pages.items() if isinstance(api_pages, Mapping) else enumerate(api_pages)

    page_sections: List[str] = []
    for page_key, page in page_entries:
        if isinstance(page, Mapping) and "raw" in page:
            page = page.get("raw", {})
        if not isinstance(page, Mapping):
            continue
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
            _build_references_panel(page.get("clinicalOverview", {}), page),
            _build_experimental_panel(page.get("clinicalOverview", {}), page),
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

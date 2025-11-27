"""Generate structured HTML previews from API page models."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


def _escape(value: object) -> str:
    return html.escape(str(value))


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


def _article_entry(article: Mapping[str, object]) -> str:
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


def _details_block(title: str, class_name: str, body: str, *, open_default: bool = False) -> str:
    if not body:
        return ""
    open_attr = " open" if open_default else ""
    return f"<details class=\"block {class_name}\"{open_attr}><summary>{_escape(title)}</summary>{body}</details>"


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


def _build_summary_block(page: Mapping[str, object]) -> str:
    hero = page.get("hero", {}) if isinstance(page, Mapping) else {}
    overview = page.get("overview", {}) if isinstance(page, Mapping) else {}

    hero_rows = []
    if hero.get("title"):
        hero_rows.append(("Title", hero.get("title")))
    if hero.get("summarySentence"):
        hero_rows.append(("Summary", hero.get("summarySentence")))
    hero_table = _table_from_pairs(hero_rows)

    tag_chips = _chip_list(hero.get("tags", []))
    use_cases_list = _unordered_list(hero.get("primaryUseCases", []))

    overview_rows = []
    if overview.get("summary"):
        overview_rows.append(("Key Takeaway", overview.get("summary")))
    overview_table = _table_from_pairs(overview_rows)

    content_parts = [
        _subblock("Hero", hero_table + tag_chips),
        _subblock("Primary Use Cases", use_cases_list),
        _subblock("Overview", overview_table),
    ]
    content = "".join(part for part in content_parts if part)
    return _details_block("Summary", "block-summary", content, open_default=True)


def _build_specs_block(page: Mapping[str, object]) -> str:
    identification = page.get("identification", {}) if isinstance(page, Mapping) else {}
    chemistry = page.get("chemistry", {}) if isinstance(page, Mapping) else {}
    products = page.get("productsAndDosageForms", {}) if isinstance(page, Mapping) else {}
    overview = page.get("overview", {}) if isinstance(page, Mapping) else {}

    identifiers = identification.get("identifiers", {}) if isinstance(identification, Mapping) else {}
    id_rows = []
    if identifiers.get("casNumber"):
        id_rows.append(("CAS", identifiers.get("casNumber")))
    if identifiers.get("unii"):
        id_rows.append(("UNII", identifiers.get("unii")))
    if identifiers.get("drugbankId"):
        id_rows.append(("DrugBank ID", identifiers.get("drugbankId")))
    id_table = _table_from_pairs(id_rows)

    identity_rows = []
    if identification.get("genericName"):
        identity_rows.append(("Generic name", identification.get("genericName")))
    if identification.get("moleculeType"):
        identity_rows.append(("Molecule type", identification.get("moleculeType")))
    identity_rows.extend(("Group", group) for group in identification.get("groups", []) if group)
    identity_table = _table_from_pairs(identity_rows)

    synonyms = _chip_list(identification.get("synonyms", []))

    description_body = ""
    if overview.get("description"):
        description_body = f"<p>{_escape(overview.get('description'))}</p>"

    chemistry_rows = []
    if chemistry.get("formula"):
        chemistry_rows.append(("Formula", chemistry.get("formula")))
    if chemistry.get("averageMolecularWeight"):
        chemistry_rows.append(("Average MW", chemistry.get("averageMolecularWeight")))
    if chemistry.get("monoisotopicMass"):
        chemistry_rows.append(("Monoisotopic Mass", chemistry.get("monoisotopicMass")))
    if chemistry.get("logP"):
        chemistry_rows.append(("logP", chemistry.get("logP")))
    chemistry_table = _table_from_pairs(chemistry_rows)

    exp_props = chemistry.get("experimentalProperties") or []
    experimental_table = _table_from_dicts(
        exp_props if isinstance(exp_props, list) else [],
        [("Name", "name"), ("Value", "value")],
    )

    dosage_forms = products.get("dosageForms") or []
    dosage_table = _table_from_dicts(
        dosage_forms if isinstance(dosage_forms, list) else [],
        [("Form", "form"), ("Route", "route"), ("Strength", "strength")],
    )

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
                entries.append(f"<li><strong>{_escape(brand_label)}</strong>{f' — {details_text}' if details_text else ''}</li>")
            if entries:
                brand_lists.append(f"<div class=\"market-group\"><div class=\"subblock-header\">{_escape(market)}</div><ul>{''.join(entries)}</ul></div>")
    brand_block = "".join(brand_lists)

    content_parts = [
        _subblock("Description", description_body),
        _subblock("Identifiers", id_table),
        _subblock("Identity", identity_table + synonyms),
        _subblock("Chemistry", chemistry_table + experimental_table),
        _subblock("Dosage Forms", dosage_table + brand_block),
    ]
    content = "".join(part for part in content_parts if part)
    return _details_block("Specs", "block-specs", content)


def _build_regulatory_block(page: Mapping[str, object]) -> str:
    regulatory = page.get("regulatoryAndMarket", {}) if isinstance(page, Mapping) else {}

    reg_rows = []
    if regulatory.get("approvalStatus"):
        reg_rows.append(("Approval status", regulatory.get("approvalStatus")))
    if regulatory.get("lifecycleSummary"):
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

    content_parts = [
        _subblock("Regulatory Status", reg_table + markets),
        _subblock("Label Highlights", label_highlights),
        _subblock("Patents", patents_table),
    ]
    content = "".join(part for part in content_parts if part)
    return _details_block("Regulatory", "block-regulatory", content)


def _build_quality_block(page: Mapping[str, object]) -> str:
    taxonomy = page.get("categoriesAndTaxonomy", {}) if isinstance(page, Mapping) else {}
    pharmacology = page.get("pharmacology", {}) if isinstance(page, Mapping) else {}
    adme = page.get("admePk", {}) if isinstance(page, Mapping) else {}
    safety = page.get("safety", {}) if isinstance(page, Mapping) else {}

    therapeutic_classes = _chip_list(taxonomy.get("therapeuticClasses", []))
    classification = taxonomy.get("classification") if isinstance(taxonomy, Mapping) else None
    class_rows = []
    if isinstance(classification, Mapping):
        for key, value in classification.items():
            if value:
                class_rows.append((key.replace("_", " ").title(), value))
    classification_table = _table_from_pairs(class_rows)

    atc_codes = taxonomy.get("atcCodes") or []
    atc_table = _table_from_dicts(
        atc_codes if isinstance(atc_codes, list) else [],
        [("ATC Code", "code")],
    )

    pharmacology_rows = []
    if pharmacology.get("highLevelSummary"):
        pharmacology_rows.append(("Summary", pharmacology.get("highLevelSummary")))
    if pharmacology.get("mechanismOfAction"):
        pharmacology_rows.append(("Mechanism", pharmacology.get("mechanismOfAction")))
    if pharmacology.get("pharmacodynamics"):
        pharmacology_rows.append(("Pharmacodynamics", pharmacology.get("pharmacodynamics")))
    pharmacology_table = _table_from_pairs(pharmacology_rows)

    pk_snapshot = adme.get("pkSnapshot", {}) if isinstance(adme, Mapping) else {}
    pk_list = _unordered_list(pk_snapshot.get("keyPoints", [])) if isinstance(pk_snapshot, Mapping) else ""
    adme_rows = []
    for label, key in (
        ("Absorption", "absorption"),
        ("Half-life", "halfLife"),
        ("Protein binding", "proteinBinding"),
        ("Metabolism", "metabolism"),
        ("Elimination", "routeOfElimination"),
        ("Volume of distribution", "volumeOfDistribution"),
        ("Clearance", "clearance"),
    ):
        if adme.get(key):
            adme_rows.append((label, adme.get(key)))
    adme_table = _table_from_pairs(adme_rows)

    safety_rows = []
    if safety.get("toxicity"):
        safety_rows.append(("Toxicity", safety.get("toxicity")))
    safety_table = _table_from_pairs(safety_rows)
    safety_bullets = _unordered_list(safety.get("highLevelWarnings", []))

    content_parts = [
        _subblock("Therapeutic Classes", therapeutic_classes),
        _subblock("Classification", classification_table),
        _subblock("ATC Codes", atc_table),
        _subblock("Pharmacology", pharmacology_table),
        _subblock("ADME / PK", adme_table + pk_list),
        _subblock("Safety", safety_table + safety_bullets),
    ]
    content = "".join(part for part in content_parts if part)
    return _details_block("Quality & Science", "block-quality", content)


def _build_supply_block(page: Mapping[str, object]) -> str:
    formulation = page.get("formulationNotes", {}) if isinstance(page, Mapping) else {}
    supply = page.get("suppliersAndManufacturing", {}) if isinstance(page, Mapping) else {}

    formulation_list = _unordered_list(formulation.get("bullets", []))

    supply_rows = []
    if supply.get("supplyChainSummary"):
        supply_rows.append(("Supply chain", supply.get("supplyChainSummary")))
    if supply.get("externalManufacturingNotes"):
        supply_rows.append(("External notes", supply.get("externalManufacturingNotes")))
    supply_table = _table_from_pairs(supply_rows)

    manufacturers = _chip_list(supply.get("manufacturers", []))
    packagers = _chip_list(supply.get("packagers", []))

    content_parts = [
        _subblock("Formulation Notes", formulation_list),
        _subblock("Supply Chain", supply_table),
        _subblock("Manufacturers", manufacturers),
        _subblock("Packagers", packagers),
    ]
    content = "".join(part for part in content_parts if part)
    return _details_block("Supply", "block-supply", content)


def _build_supplier_block(page: Mapping[str, object]) -> str:
    buyer = page.get("buyerCheatsheet", {}) if isinstance(page, Mapping) else {}
    references = page.get("references", {}) if isinstance(page, Mapping) else {}

    buyer_list = _unordered_list(buyer.get("bullets", []))

    articles = references.get("scientificArticles") or [] if isinstance(references, Mapping) else []
    article_items = [_article_entry(article) for article in articles]
    articles_list = _unordered_html_list(article_items)

    links = references.get("regulatoryLinks") or [] if isinstance(references, Mapping) else []
    other_links = references.get("otherLinks") or [] if isinstance(references, Mapping) else []
    link_entries = [_link_entry(link) for link in [*links, *other_links]]
    links_list = _unordered_html_list(link_entries)

    content_parts = [
        _subblock("Buyer Cheatsheet", buyer_list),
        _subblock("Key References", articles_list),
        _subblock("Links", links_list),
    ]
    content = "".join(part for part in content_parts if part)
    return _details_block("Supplier Notes", "block-supplier", content)


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
    return _details_block("SEO", "block-seo", content)


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
    .block { border-top: 1px solid #e5e7eb; }
    .block summary { cursor: pointer; padding: 10px 14px; font-weight: 600; background: #ffffff; }
    .block[open] > summary { background: #eef2ff; }
    .subblock { padding: 0 16px 12px; }
    .subblock-header h4 { margin: 8px 0 4px; font-size: 14px; }
    .subblock-body { font-size: 13px; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
    th, td { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; font-size: 12px; }
    ul { margin: 4px 0 8px 18px; padding: 0; }
    .chip-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 8px 0; }
    .chip { background: #e0f2fe; color: #0f172a; padding: 2px 8px; border-radius: 12px; font-size: 11px; }
    .market-group { margin-bottom: 10px; }
    </style>
    """

    page_entries = api_pages.items() if isinstance(api_pages, Mapping) else enumerate(api_pages)

    page_sections: List[str] = []
    for page_key, page in page_entries:
        if not isinstance(page, Mapping):
            continue
        page_name = page.get("hero", {}).get("title") or str(page_key)
        blocks = [
            _build_summary_block(page),
            _build_specs_block(page),
            _build_regulatory_block(page),
            _build_quality_block(page),
            _build_supply_block(page),
            _build_supplier_block(page),
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

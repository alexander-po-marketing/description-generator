"""Build structured API page models from parsed drug data and generated text."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from typing import Dict, List, Optional, Sequence

from src.generators import (
    build_description_prompt,
    build_buyer_cheatsheet_prompt,
    build_lifecycle_summary_prompt,
    build_formulation_notes_prompt,
    build_pharmacology_summary_prompt,
    build_safety_highlights_prompt,
    build_seo_description_prompt,
    build_supply_chain_prompt,
    build_summary_prompt,
    build_summary_sentence_prompt,
)
from src.models import DrugData, ExternalIdentifier, GeneratedContent, Patent, Target
from src.openai_client import OpenAIClient


def _sanitize_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\[.*?\]", "", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _unique(items: Sequence[Optional[str]]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if not item:
            continue
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _split_to_list(value: Optional[str], max_items: int = 4) -> List[str]:
    if not value:
        return []
    parts = re.split(r"[;\.\n]", value)
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return cleaned[:max_items]


def _synonym_list(drug: DrugData) -> List[str]:
    synonyms_raw = getattr(drug, "synonyms", None) or drug.raw_fields.get("synonyms")
    if synonyms_raw is None:
        return []
    if isinstance(synonyms_raw, list):
        return [str(item) for item in synonyms_raw if str(item).strip()]
    return [item.strip() for item in re.split(r",|;|\n", str(synonyms_raw)) if item.strip()]


def _brand_names(drug: DrugData) -> List[str]:
    brands = list(drug.international_brands)
    brands.extend(p.brand for p in drug.products if getattr(p, "brand", None))
    return _unique(brands)


def _product_markets(drug: DrugData) -> List[str]:
    markets = [p.country for p in drug.products if getattr(p, "country", None)]
    markets.extend(
        approval.region for approval in getattr(drug, "regulatory_approvals", []) if getattr(approval, "region", None)
    )
    return _unique(markets)


def _patent_rows(patents: List[Patent]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for patent in patents:
        rows.append(
            {
                "number": patent.number,
                "country": patent.country,
                "approvedDate": patent.approved_date,
                "expiresDate": patent.expires_date,
                "pediatricExtension": patent.pediatric_extension,
            }
        )
    return rows


def _pk_snapshot(drug: DrugData) -> List[str]:
    pk_fields = [
        ("Absorption", drug.absorption),
        ("Half-life", drug.half_life or drug.raw_fields.get("half-life")),
        ("Protein binding", drug.protein_binding),
        ("Metabolism", drug.metabolism),
        ("Elimination", drug.route_of_elimination),
        ("Volume of distribution", drug.volume_of_distribution),
        ("Clearance", drug.clearance),
    ]
    bullets = [f"{label}: {value}" for label, value in pk_fields if value]
    return bullets[:6]


def _dosage_forms(drug: DrugData) -> List[Dict[str, Optional[str]]]:
    forms: List[Dict[str, Optional[str]]] = []
    seen = set()

    for dosage in drug.dosages:
        key = (dosage.form, dosage.route, dosage.strength)
        if key in seen:
            continue
        seen.add(key)
        forms.append({"form": dosage.form, "route": dosage.route, "strength": dosage.strength})

    for product in drug.products:
        key = (product.dosage_form, product.route, product.strength)
        if key in seen:
            continue
        seen.add(key)
        forms.append({"form": product.dosage_form, "route": product.route, "strength": product.strength})

    return forms


def _brands_by_market(drug: DrugData) -> Dict[str, List[Dict[str, object]]]:
    markets: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for product in drug.products:
        country = product.country or "Unspecified"
        markets[country].append(
            {
                "brand": product.brand,
                "dosageForm": product.dosage_form,
                "route": product.route,
                "strength": product.strength,
                "startedMarketingOn": product.started_marketing_on,
                "endedMarketingOn": product.ended_marketing_on,
                "generic": product.generic,
                "regulatorySource": product.regulatory_source,
            }
        )
    return dict(markets)


def _experimental_properties(drug: DrugData) -> List[Dict[str, object]]:
    properties: List[Dict[str, object]] = []
    raw_props = drug.raw_fields.get("experimental-properties") or drug.raw_fields.get("experimental_properties")
    if isinstance(raw_props, list):
        for prop in raw_props:
            properties.append({"name": str(prop)})
    elif isinstance(raw_props, dict):
        for key, value in raw_props.items():
            properties.append({"name": key, "value": value})
    elif raw_props:
        properties.append({"name": "Experimental property", "value": raw_props})

    chemistry_backfill = [
        ("logP", drug.logp),
        ("Water solubility", drug.water_solubility),
        ("Melting point", drug.melting_point),
    ]
    for name, value in chemistry_backfill:
        if value:
            properties.append({"name": name, "value": value})
    return properties


def _targets_to_dict(targets: List[Target]) -> List[Dict[str, object]]:
    data: List[Dict[str, object]] = []
    for target in targets:
        data.append(
            {
                "name": target.name,
                "organism": target.organism,
                "actions": list(target.actions),
                "goProcesses": list(target.go_processes),
            }
        )
    return data


def _atc_codes_to_dict(atc_codes: List[object]) -> List[Dict[str, object]]:
    codes: List[Dict[str, object]] = []
    for code in atc_codes:
        levels = getattr(code, "levels", [])
        codes.append(
            {
                "code": getattr(code, "code", None),
                "levels": [asdict(level) if is_dataclass(level) else level for level in levels],
            }
        )
    return codes


def _identifier_table(drug: DrugData) -> Dict[str, object]:
    table: Dict[str, object] = {
        "casNumber": drug.cas_number or drug.raw_fields.get("casNumber") or drug.raw_fields.get("cas-number"),
        "unii": drug.unii,
        "drugbankId": getattr(drug, "drugbank_id", None)
        or drug.raw_fields.get("drugbankId")
        or drug.raw_fields.get("drugbank-id"),
    }
    external: List[Dict[str, object]] = []
    for identifier in drug.external_identifiers:
        if isinstance(identifier, ExternalIdentifier):
            external.append({"resource": identifier.resource, "identifier": identifier.identifier})
    if external:
        table["external"] = external
    return table


def _serialize_list(items: List[object]) -> List[object]:
    serialized: List[object] = []
    for item in items:
        if is_dataclass(item):
            serialized.append(asdict(item))
        else:
            serialized.append(item)
    return serialized


def _ensure_generated_fields(
    drug: DrugData,
    client: OpenAIClient,
    *,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    summary_sentence: Optional[str] = None,
) -> GeneratedContent:
    description_text = description
    summary_text = summary
    summary_sentence_text = summary_sentence

    if description_text is None:
        desc_prompt = build_description_prompt(drug)
        description_text = client.generate_description(desc_prompt)

    if summary_text is None:
        summary_prompt = build_summary_prompt(drug, description_text)
        summary_text = client.generate_summary(summary_prompt)

    if summary_sentence_text is None:
        sentence_prompt = build_summary_sentence_prompt(drug)
        summary_sentence_text = client.generate_text(sentence_prompt)

    return GeneratedContent(
        description=_sanitize_text(description_text) or "",
        summary=_sanitize_text(summary_text) or "",
        summary_sentence=_sanitize_text(summary_sentence_text),
    )


def build_page_model(
    drug: DrugData,
    client: OpenAIClient,
    *,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    summary_sentence: Optional[str] = None,
) -> Dict[str, object]:
    generated = _ensure_generated_fields(
        drug,
        client,
        summary=summary,
        description=description,
        summary_sentence=summary_sentence,
    )

    primary_use_cases = _split_to_list(drug.indication, max_items=4)
    tags = _unique(list(drug.categories) + list(drug.groups))
    brands = _brand_names(drug)
    markets = _product_markets(drug)
    patents_table = _patent_rows(drug.patents)

    lifecycle_summary: Optional[str] = None
    if patents_table or markets:
        lifecycle_prompt = build_lifecycle_summary_prompt(drug, drug.patents, markets)
        lifecycle_summary = _sanitize_text(client.generate_text(lifecycle_prompt))

    pharmacology_summary: Optional[str] = None
    if drug.mechanism_of_action or drug.pharmacodynamics:
        pharmacology_prompt = build_pharmacology_summary_prompt(drug)
        pharmacology_summary = _sanitize_text(client.generate_text(pharmacology_prompt))

    safety_highlights: List[str] = []
    if drug.toxicity:
        safety_prompt = build_safety_highlights_prompt(drug)
        highlights = _sanitize_text(client.generate_text(safety_prompt))
        safety_highlights = _split_to_list(highlights, max_items=3)

    formulation_notes: List[str] = []
    formulation_prompt = build_formulation_notes_prompt(drug)
    formulation_output = _sanitize_text(client.generate_text(formulation_prompt))
    formulation_notes = _split_to_list(formulation_output, max_items=3)

    supply_chain_summary: Optional[str] = None
    if drug.manufacturers or drug.packagers or drug.products or drug.patents:
        supply_prompt = build_supply_chain_prompt(drug)
        supply_chain_summary = _sanitize_text(client.generate_text(supply_prompt))

    buyer_cheatsheet: List[str] = []
    cheatsheet_prompt = build_buyer_cheatsheet_prompt(drug)
    cheatsheet_output = _sanitize_text(client.generate_text(cheatsheet_prompt))
    buyer_cheatsheet = _split_to_list(cheatsheet_output, max_items=3)

    seo_meta_description = generated.summary or generated.summary_sentence
    seo_prompt = build_seo_description_prompt(drug)
    seo_meta_description = _sanitize_text(client.generate_text(seo_prompt)) or seo_meta_description

    approval_status = None
    if drug.groups:
        approval_status = ", ".join(
            f"{group.capitalize()} drug" if "drug" not in (group or "").lower() else group.capitalize()
            for group in drug.groups
            if group
        )

    page = {
        "hero": {
            "title": drug.name,
            "summarySentence": generated.summary_sentence,
            "tags": tags,
            "primaryUseCases": primary_use_cases,
        },
        "overview": {
            "summary": generated.summary,
            "description": generated.description,
        },
        "identification": {
            "genericName": drug.name,
            "brandNames": brands,
            "synonyms": _synonym_list(drug),
            "identifiers": _identifier_table(drug),
            "moleculeType": drug.drug_type or drug.type,
            "groups": list(drug.groups),
        },
        "chemistry": {
            "formula": drug.molecular_formula,
            "averageMolecularWeight": drug.average_mass,
            "monoisotopicMass": drug.monoisotopic_mass,
            "logP": drug.logp,
            "experimentalProperties": _experimental_properties(drug),
        },
        "regulatoryAndMarket": {
            "approvalStatus": approval_status,
            "markets": markets,
            "labelHighlights": primary_use_cases,
            "patents": patents_table,
            "lifecycleSummary": lifecycle_summary,
        },
        "formulationNotes": {
            "bullets": formulation_notes,
        },
        "categoriesAndTaxonomy": {
            "therapeuticClasses": list(drug.categories),
            "atcCodes": _atc_codes_to_dict(drug.atc_codes),
            "classification": drug.classification,
        },
        "pharmacology": {
            "mechanismOfAction": drug.mechanism_of_action,
            "pharmacodynamics": drug.pharmacodynamics,
            "targets": _targets_to_dict(drug.targets),
            "highLevelSummary": pharmacology_summary,
        },
        "admePk": {
            "absorption": drug.absorption,
            "halfLife": drug.half_life or drug.raw_fields.get("half-life"),
            "proteinBinding": drug.protein_binding,
            "metabolism": drug.metabolism,
            "routeOfElimination": drug.route_of_elimination,
            "volumeOfDistribution": drug.volume_of_distribution,
            "clearance": drug.clearance,
            "pkSnapshot": {"keyPoints": _pk_snapshot(drug)},
        },
        "productsAndDosageForms": {
            "dosageForms": _dosage_forms(drug),
            "brandsByMarket": _brands_by_market(drug),
            "marketPresenceSummary": None,
        },
        "clinicalTrials": {
            "trialsByPhase": {},
            "hasClinicalTrialsData": False,
        },
        "suppliersAndManufacturing": {
            "manufacturers": list(drug.manufacturers),
            "packagers": list(drug.packagers),
            "externalManufacturingNotes": drug.raw_fields.get("manufacturing-notes"),
            "pharmaofferSuppliers": [],
            "supplyChainSummary": supply_chain_summary,
        },
        "safety": {
            "toxicity": drug.toxicity,
            "highLevelWarnings": safety_highlights,
        },
        "experimentalProperties": {
            "properties": _experimental_properties(drug),
        },
        "references": {
            "scientificArticles": _serialize_list(drug.scientific_articles),
            "regulatoryLinks": _serialize_list(drug.regulatory_links),
            "otherLinks": _serialize_list(getattr(drug.general_references, "links", [])),
        },
        "seo": {
            "title": f"{drug.name} API suppliers, regulatory and technical information" if drug.name else None,
            "metaDescription": seo_meta_description,
            "keywords": _unique(
                [
                    drug.name,
                    *(brands or []),
                    drug.cas_number,
                    *(drug.categories or []),
                    *[atc.code for atc in drug.atc_codes if atc.code],
                ]
            ),
        },
        "buyerCheatsheet": {"bullets": buyer_cheatsheet},
        "metadata": {
            "drugbankId": getattr(drug, "drugbank_id", None),
            "casNumber": drug.cas_number,
            "unii": drug.unii,
            "createdAt": drug.raw_fields.get("created-at"),
            "updatedAt": drug.raw_fields.get("updated-at"),
            "sourceSystems": ["DrugBank"],
        },
    }

    return page

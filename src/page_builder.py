"""Build structured API page models from parsed drug data and generated text."""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from src.generators import (
    build_description_prompt,
    build_buyer_cheatsheet_prompt,
    build_lifecycle_summary_prompt,
    build_formulation_notes_prompt,
    build_meta_description,
    build_pharmacology_summary_prompt,
    build_safety_highlights_prompt,
    build_supply_chain_prompt,
    build_summary_prompt,
    build_summary_sentence_prompt,
)
from src.models import DrugData, GeneratedContent, Patent, Target
from src.openai_client import OpenAIClient
from src.template_engine import DEFAULT_TEMPLATE, TemplateDefinition


def _sanitize_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\[.*?\]", "", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _build_seo_title(drug_name: Optional[str]) -> Optional[str]:
    if not drug_name:
        return None

    full_title = f"{drug_name} API manufacturers - Verified GMP suppliers and quotes"
    if len(full_title) > 66:
        return f"{drug_name} API manufacturers - Verified GMP suppliers"
    return full_title


def _classification_description_text(drug: DrugData) -> Optional[str]:
    classification = getattr(drug, "classification", None)
    if isinstance(classification, dict):
        return classification.get("description")
    if hasattr(classification, "description"):
        return getattr(classification, "description")
    return None


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

    def _normalize_fragment(fragment: str) -> Optional[str]:
        cleaned = fragment or ""
        cleaned = re.sub(r"^[\s\-•*\u2022\u2023\uf0b7]+", "", cleaned)
        cleaned = re.sub(r"^\d+[\.)]\s*", "", cleaned)
        cleaned = cleaned.strip(" \t-–—")
        if not cleaned:
            return None
        if cleaned[0].isalpha():
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    cleaned = []
    for part in parts:
        normalized = _normalize_fragment(part)
        if normalized:
            cleaned.append(normalized)
        if len(cleaned) >= max_items:
            break
    return cleaned


def _limited_therapeutic_classes(categories: Sequence[str], limit: int = 6) -> List[str]:
    return _unique(categories)[:limit]


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
    return {
        "casNumber": drug.cas_number or drug.raw_fields.get("casNumber") or drug.raw_fields.get("cas-number"),
        "unii": drug.unii,
        "drugbankId": getattr(drug, "drugbank_id", None)
        or drug.raw_fields.get("drugbankId")
        or drug.raw_fields.get("drugbank-id"),
    }


def _sanitize_classification(classification: object) -> object:
    if classification is None:
        return None
    if is_dataclass(classification):
        classification = asdict(classification)
    if not isinstance(classification, Mapping):
        return classification

    disallowed_keys = {"alternative_parents", "alternativeParents", "substituents"}
    cleaned = {}
    for key, value in classification.items():
        if key in disallowed_keys:
            continue
        if key.lower().replace(" ", "_") in {"alternative_parents", "substituents"}:
            continue
        cleaned[key] = value
    return cleaned


def _ensure_generated_fields(
    drug: DrugData,
    client: OpenAIClient,
    *,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    summary_sentence: Optional[str] = None,
    generation_enabled: Callable[[str], bool],
) -> GeneratedContent:
    description_text = description
    summary_text = summary
    summary_sentence_text = summary_sentence

    if not description_text and generation_enabled("description"):
        desc_prompt = build_description_prompt(drug)
        description_text = client.generate_description(desc_prompt)

    if not summary_text and generation_enabled("summary"):
        summary_prompt = build_summary_prompt(drug, description_text or "")
        summary_text = client.generate_summary(summary_prompt)

    if not summary_sentence_text and generation_enabled("summary_sentence"):
        sentence_prompt = build_summary_sentence_prompt(drug)
        summary_sentence_text = client.generate_text(sentence_prompt)

    description_clean = _sanitize_text(description_text) or ""
    summary_clean = _sanitize_text(summary_text) or ""
    summary_sentence_clean = _sanitize_text(summary_sentence_text)

    if not summary_sentence_clean and summary_clean and generation_enabled("summary_sentence"):
        summary_sentences = _split_to_list(summary_clean, max_items=1)
        summary_sentence_clean = summary_sentences[0] if summary_sentences else None

    if not summary_sentence_clean and description_clean and generation_enabled("summary_sentence"):
        description_sentences = _split_to_list(description_clean, max_items=1)
        summary_sentence_clean = description_sentences[0] if description_sentences else None

    return GeneratedContent(
        description=description_clean,
        summary=summary_clean,
        summary_sentence=summary_sentence_clean,
    )


def _build_openapi_snapshot(drug: DrugData, page_model: Dict[str, object]) -> Dict[str, object]:
    overview = page_model.get("clinicalOverview", {}) if isinstance(page_model, Mapping) else {}
    legacy_overview = page_model.get("overview", {}) if isinstance(page_model, Mapping) else {}
    summary_text = overview.get("summary") or legacy_overview.get("summary")
    description_text = overview.get("longDescription") or legacy_overview.get("description")

    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"{drug.name} reference" if drug.name else "API reference",
            "version": "1.0.0",
            "summary": summary_text,
            "description": description_text,
        },
        "paths": {
            "/pageModel": {
                "get": {
                    "summary": "Retrieve the generated API page model",
                    "responses": {
                        "200": {
                            "description": "Structured API page output",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "pageModel": {"type": "object", "description": "Raw structured API page", "example": page_model}
            }
        },
    }


def build_page_model(
    drug: DrugData,
    client: OpenAIClient,
    *,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    summary_sentence: Optional[str] = None,
    template: Optional[TemplateDefinition] = None,
) -> Dict[str, object]:
    template_definition = template or DEFAULT_TEMPLATE
    generation_flags = template_definition.generation_flags()
    has_generation_controls = template_definition.has_generation_ids()

    def generation_enabled(key: str) -> bool:
        if not has_generation_controls:
            return True
        return generation_flags.get(key, False)

    generated = _ensure_generated_fields(
        drug,
        client,
        summary=summary,
        description=description,
        summary_sentence=summary_sentence,
        generation_enabled=generation_enabled,
    )

    primary_use_cases = _split_to_list(drug.indication, max_items=4)
    tags = _unique(list(drug.categories) + list(drug.groups))
    brands = _brand_names(drug)
    markets = _product_markets(drug)
    patents_table = _patent_rows(drug.patents)

    lifecycle_summary: Optional[str] = None
    if generation_enabled("lifecycle_summary") and (patents_table or markets):
        lifecycle_prompt = build_lifecycle_summary_prompt(drug, drug.patents, markets)
        lifecycle_summary = _sanitize_text(client.generate_text(lifecycle_prompt))

    pharmacology_summary: Optional[str] = None
    if generation_enabled("pharmacology_summary") and (drug.mechanism_of_action or drug.pharmacodynamics):
        pharmacology_prompt = build_pharmacology_summary_prompt(drug)
        pharmacology_summary = _sanitize_text(client.generate_text(pharmacology_prompt))

    safety_highlights: List[str] = []
    if generation_enabled("safety_highlights") and drug.toxicity:
        safety_prompt = build_safety_highlights_prompt(drug)
        highlights = _sanitize_text(client.generate_text(safety_prompt))
        safety_highlights = _split_to_list(highlights, max_items=3)

    formulation_notes: List[str] = []
    if generation_enabled("formulation_notes"):
        formulation_prompt = build_formulation_notes_prompt(drug)
        formulation_output = _sanitize_text(client.generate_text(formulation_prompt))
        formulation_notes = _split_to_list(formulation_output, max_items=3)

    supply_chain_summary: Optional[str] = None
    if generation_enabled("supply_chain_summary") and (
        drug.manufacturers or drug.packagers or drug.products or drug.patents
    ):
        supply_prompt = build_supply_chain_prompt(drug)
        supply_chain_summary = _sanitize_text(client.generate_text(supply_prompt))

    buyer_cheatsheet: List[str] = []
    if generation_enabled("buyer_cheatsheet"):
        cheatsheet_prompt = build_buyer_cheatsheet_prompt(drug)
        cheatsheet_output = _sanitize_text(client.generate_text(cheatsheet_prompt))
        buyer_cheatsheet = _split_to_list(cheatsheet_output, max_items=3)

    cas_number = drug.cas_number or drug.raw_fields.get("casNumber") or drug.raw_fields.get("cas-number")
    seo_meta_description = build_meta_description(
        api_name=drug.name or "",
        cas_number=cas_number or "",
        drug_type=drug.drug_type or drug.type or "",
        state=drug.state or "",
        therapeutic_class=drug.categories,
        classification_description=_classification_description_text(drug),
    )

    approval_status = None
    if drug.groups:
        approval_status = ", ".join(
            f"{group.capitalize()} drug" if "drug" not in (group or "").lower() else group.capitalize()
            for group in drug.groups
            if group
        )
    if drug.cas_number:
        drug_title = f"{drug.name} | CAS No: {drug.cas_number} | GMP-certified suppliers"
    else:
        drug_title = f"{drug.name} | GMP-certified suppliers"
        
    identification_block = {
        "genericName": drug.name,
        "brandNames": brands,
        "synonyms": _synonym_list(drug),
        "identifiers": _identifier_table(drug),
        "moleculeType": drug.drug_type or drug.type,
        "groups": list(drug.groups),
    }

    chemistry_block = {
        "formula": drug.molecular_formula,
        "averageMolecularWeight": drug.average_mass,
        "monoisotopicMass": drug.monoisotopic_mass,
        "logP": drug.logp,
    }

    regulatory_block = {
        "lifecycleSummary": lifecycle_summary,
        "approvalStatus": approval_status,
        "markets": markets,
        "labelHighlights": primary_use_cases,
    }

    taxonomy_block = {
        "therapeuticClasses": _limited_therapeutic_classes(drug.categories),
        "atcCodes": _atc_codes_to_dict(drug.atc_codes),
        "classification": _sanitize_classification(drug.classification),
    }

    pharmacology_block = {
        "highLevelSummary": pharmacology_summary,
        "mechanismOfAction": drug.mechanism_of_action,
        "pharmacodynamics": drug.pharmacodynamics,
        "targets": _targets_to_dict(drug.targets),
        "summary": pharmacology_summary,
    }

    pk_snapshot = {"keyPoints": _pk_snapshot(drug)}
    adme_table = {
        "absorption": drug.absorption,
        "halfLife": drug.half_life or drug.raw_fields.get("half-life"),
        "proteinBinding": drug.protein_binding,
        "metabolism": drug.metabolism,
        "routeOfElimination": drug.route_of_elimination,
        "volumeOfDistribution": drug.volume_of_distribution,
        "clearance": drug.clearance,
    }
    adme_pk_block = {
        **adme_table,
        "pkSnapshot": pk_snapshot,
        "table": {**adme_table, "pkSnapshot": pk_snapshot},
    }

    supply_block = {
        "supplyChainSummary": supply_chain_summary,
        "manufacturers": list(drug.manufacturers),
        "packagers": list(drug.packagers),
        "externalManufacturingNotes": drug.raw_fields.get("manufacturing-notes"),
        "pharmaofferSuppliers": [],
    }

    safety_block = {
        "toxicity": drug.toxicity,
        "highLevelWarnings": safety_highlights,
    }

    seo_block = {
        "title": _build_seo_title(drug.name),
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
    }

    metadata_block = {
        "drugbankId": getattr(drug, "drugbank_id", None),
        "casNumber": drug.cas_number,
        "unii": drug.unii,
        "createdAt": drug.raw_fields.get("created-at"),
        "updatedAt": drug.raw_fields.get("updated-at"),
        "sourceSystems": ["DrugBank"],
    }

    hero_facts = {
        "genericName": drug.name,
        "moleculeType": identification_block.get("moleculeType"),
        "casNumber": identification_block.get("identifiers", {}).get("casNumber"),
        "drugbankId": identification_block.get("identifiers", {}).get("drugbankId"),
        "approvalStatus": approval_status,
        "atcCode": (taxonomy_block.get("atcCodes") or [{}])[0].get("code") if taxonomy_block.get("atcCodes") else None,
    }

    hero_block = {
        "title": drug_title,
        "summarySentence": generated.summary_sentence,
        "summary": generated.summary,
        "tags": tags,
        "primaryUseCases": primary_use_cases,
        "therapeuticCategories": taxonomy_block.get("therapeuticClasses"),
        "facts": hero_facts,
    }

    overview_block = {
        "summary": generated.summary,
        "description": generated.description,
    }

    clinical_overview = {
        "summary": generated.summary,
        "longDescription": generated.description,
        "identificationClassification": {
            "identification": identification_block,
            "regulatoryClassification": {
                "approvalStatus": approval_status,
                "groups": list(drug.groups),
                "classification": taxonomy_block.get("classification"),
                "therapeuticClasses": taxonomy_block.get("therapeuticClasses"),
                "atcCodes": taxonomy_block.get("atcCodes"),
                "markets": markets,
            },
            "chemistry": chemistry_block,
        },
        "pharmacologyTargets": {
            "summary": pharmacology_summary,
            "pharmacology": pharmacology_block,
            "targets": pharmacology_block.get("targets"),
        },
        "admePk": {
            "table": {**adme_table, "pkSnapshot": adme_pk_block.get("pkSnapshot")},
            "pkSnapshot": adme_pk_block.get("pkSnapshot"),
        },
        "formulationHandling": {"notes": formulation_notes},
        "regulatoryMarket": {
            "summary": lifecycle_summary,
            "approvalStatus": approval_status,
            "markets": markets,
            "labelHighlights": primary_use_cases,
            "details": regulatory_block,
            "supplyChain": supply_block,
        },
        "safetyRisks": safety_block,
        "safety": safety_block,
    }

    page = {
        "hero": hero_block,
        "facts": hero_facts,
        "primaryIndications": primary_use_cases,
        "buyerCheatsheet": {"bullets": buyer_cheatsheet},
        "clinicalOverview": clinical_overview,
        "overview": overview_block,
        "identification": identification_block,
        "chemistry": chemistry_block,
        "regulatoryAndMarket": regulatory_block,
        "formulationNotes": {"bullets": formulation_notes},
        "categoriesAndTaxonomy": taxonomy_block,
        "pharmacology": pharmacology_block,
        "pharmacologyTargets": clinical_overview.get("pharmacologyTargets"),
        "admePk": adme_pk_block,
        "suppliersAndManufacturing": supply_block,
        "safety": safety_block,
        "safetyRisks": safety_block,
        "seo": seo_block,
        "metadata": metadata_block,
    }

    openapi_snapshot = _build_openapi_snapshot(drug, page)
    rendered_blocks = template_definition.render({**page, "openapi": openapi_snapshot}, openapi_snapshot)

    return {
        "template": template_definition.to_dict(),
        "blocks": rendered_blocks,
        "raw": {**page, "openapi": openapi_snapshot},
    }

"""Prompt and content generation helpers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from textwrap import dedent
from typing import Dict, Iterable, List, Optional, Sequence

from src.models import DrugData, Patent, Product


def _format_optional(value) -> str:
    if value is None:
        return "Not specified"
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, list):
        return ", ".join(_format_optional(item) for item in value) if value else "Not specified"
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items()) if value else "Not specified"
    return str(value)


def _context_lines(context: Dict[str, object]) -> str:
    lines: List[str] = []
    for key, value in context.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            cleaned = [str(item) for item in value if item]
            if not cleaned:
                continue
            value = ", ".join(cleaned)
        elif isinstance(value, dict):
            if not value:
                continue
            value = "; ".join(f"{k}: {v}" for k, v in value.items() if v)
            if not value:
                continue
        if str(value).strip():
            lines.append(f"{key}: {value}")
    return "\n".join(lines)

def _classification_description(drug: DrugData) -> str:
    classification = getattr(drug, "classification", None)
    if isinstance(classification, dict):
        return classification.get("description") or ""
    if hasattr(classification, "description"):
        return getattr(classification, "description") or ""
    return ""


def unique_countries_from_products(products: Iterable[Product]) -> List[str]:
    seen = set()
    countries: List[str] = []
    for product in products:
        country = getattr(product, "country", None)
        if country and country not in seen:
            seen.add(country)
            countries.append(country)
    return countries


def build_description_prompt(drug: DrugData) -> str:
    fields: Dict[str, str] = {
        "API Name": _format_optional(drug.name),
        "CAS Number": _format_optional(drug.cas_number),
        "Description": _format_optional(drug.description),
        "Classification description": _format_optional(_classification_description(drug)),
        "Indication": _format_optional(drug.indication),
        "Pharmacodynamics": _format_optional(drug.pharmacodynamics),
        "Mechanism of Action": _format_optional(drug.mechanism_of_action),
        "Groups/Approval": _format_optional(drug.groups),
        "Drug Categories": _format_optional(drug.categories),
    }

    formatted = "\n".join(f"- {key}: {value}" for key, value in fields.items())
    return dedent(
        f"""
        You are a senior pharmaceutical medical writer crafting authoritative product content for formulation scientists, pharma API sourcing managers, and regulatory affairs teams.
        Write a 260-320 word description in plain text (no HTML or Markdown) using short paragraphs separated by blank lines.
        The writing must be technically rigorous, globally relevant, and avoid promotional claims.
        Emphasize: clinical indication, pharmacology, mechanism of action, key ADME parameters, safety/toxicity considerations, and any notable brands or usage contexts.
        Close with a concise note on sourcing or quality considerations relevant to API procurement.

        Use this structured DrugBank-derived data:
        {formatted}

        Output requirements:
        - Plain text only. Do NOT include HTML, Markdown, headings, or bullet symbols.
        - Keep language neutral and compliant.
        - Avoid placeholder text; omit any unknown details rather than fabricating.
        """
    ).strip()


def build_summary_prompt(drug: DrugData, description: str) -> str:
    return dedent(
        f"""
        Summarize the following API description for quick B2B API catalog previews for pharma API sourcing managers.
        Output 1-2 sentences highlighting indication, mechanism, and sourcing/quality notes.
        Avoid marketing language and do not exceed 60 words.

        Drug: {drug.name or 'Unknown'}
        CAS: {drug.cas_number or 'N/A'}
        Description:
        {description}
        """
    ).strip()


def build_summary_sentence_context(drug: DrugData) -> Dict[str, object]:
    return {
        "Name": drug.name,
        "Indications": drug.indication,
        "Therapeutic classes": drug.categories,
        "Key markets": unique_countries_from_products(drug.products),
        
    }


def build_summary_sentence_prompt(drug: DrugData, description: str) -> str:
    context = build_summary_sentence_context(drug)
    return dedent(
        f"""
        You are a medical copywriter. Based on the following data, write exactly one simple, pharma API sourcing managers-friendly sentence (18–30 words) that introduces the medication for a B2B API catalog.
        Start with 'A medication that ...'. Focus on the main disease areas and benefits, and do not mention dosage, brands, molecular details, or mechanisms.

        { _context_lines(context) or 'Name: Unknown' }
        Description:
        {description}

        Sentence:
        """
    ).strip()


def build_formulation_notes_context(drug: DrugData) -> Dict[str, object]:
    routes = sorted({dosage.route for dosage in drug.dosages if getattr(dosage, "route", None)})
    classification_description = _classification_description(drug)
    return {
        "Name": drug.name,
        "Drug type": drug.drug_type or drug.type,
        "Classification description": classification_description,
        "State": drug.state,
        "Molecular weight": drug.average_mass,
        "Melting point": drug.melting_point,
        "LogP": drug.logp,
        "Water solubility": drug.water_solubility,
        "Dosages": [asdict(dosage) for dosage in drug.dosages if any(asdict(dosage).values())],
        "Routes": routes,
        "Groups": drug.groups,
        "Food interactions": drug.food_interactions,
        
    }


def build_formulation_notes_prompt(drug: DrugData) -> str:
    context = build_formulation_notes_context(drug)
    return dedent(
        f"""
        You are writing technical notes for formulation scientists and API buyers (B2B). Based on the data below, write 2–3 concise sentences separated by new lines (no bullet symbols or numbering) about formulation and handling considerations for this API.
        Mention only high-level aspects such as: injectable vs oral use, peptide/biologic nature, sensitivity to food, stability/handling (if relevant). Do not provide dosing advice.

        { _context_lines(context) or 'Name: Unknown' }

        Sentences (each on a new line, no bullet characters):
        """
    ).strip()


def _compact_patent_lines(patents: Sequence[Patent], limit: int = 5) -> List[str]:
    lines: List[str] = []
    for patent in patents[:limit]:
        parts = [patent.number, patent.country, patent.expires_date or patent.approved_date]
        compact = " | ".join(part for part in parts if part)
        if compact:
            lines.append(compact)
    return lines


def build_supply_chain_context(drug: DrugData) -> Dict[str, object]:
    markets = unique_countries_from_products(drug.products)
    brand_samples = [product.brand for product in drug.products if product.brand][:5]
    return {
        "Name": drug.name,
        "Manufacturers": drug.manufacturers,
        "Packagers": drug.packagers,
        "Markets": markets,
        "Brand samples": brand_samples,
        "Patents": _compact_patent_lines(drug.patents),
    }


def build_supply_chain_prompt(drug: DrugData) -> str:
    context = build_supply_chain_context(drug)
    return dedent(
        f"""
        You are preparing a high-level supply chain overview for an API B2B sourcing marketplace. Based on the data below, write 2–3 sentences about the manufacturing/supply landscape: number and role of originator companies, global presence of branded products (US/EU/other), and whether patent expiry suggests upcoming or existing generic competition.
        Do not mention any specific company opinions or give business advice.

        { _context_lines(context) or 'No supply chain data provided' }

        Overview:
        """
    ).strip()


def build_pharmacology_summary_context(drug: DrugData) -> Dict[str, object]:
    return {
        "Mechanism of action": drug.mechanism_of_action,
        "Pharmacodynamics": drug.pharmacodynamics,
        "Targets": [t.name for t in drug.targets if t.name],
        "Indication": drug.indication,
    }


def build_pharmacology_summary_prompt(drug: DrugData) -> str:
    context = build_pharmacology_summary_context(drug)
    return dedent(
        f"""
        Create 2-3 concise sentences that summarize this drug's pharmacology and mechanism in high-level, non-promotional language for a B2B API catalog.
        Focus on therapeutic intent, primary targets, and major pharmacodynamic themes. Avoid dosing guidance and clinical advice.

        { _context_lines(context) }

        Summary:
        """
    ).strip()


def build_lifecycle_summary_context(patents: List[Patent], markets: List[str]) -> Dict[str, object]:
    return {
        "Patents": _compact_patent_lines(patents),
        "Markets": markets,
    }


def build_lifecycle_summary_prompt(drug: DrugData, patents: List[Patent], markets: List[str]) -> str:
    context = build_lifecycle_summary_context(patents, markets)
    return dedent(
        f"""
        Draft a short lifecycle summary (1-2 sentences) for an API based on patent expiry timing and where products are marketed.
        Keep it neutral, non-promotional, and focused on market maturity.

        { _context_lines(context) or 'Patents: None listed' }

        Summary:
        """
    ).strip()


def build_safety_highlights_context(drug: DrugData) -> Dict[str, object]:
    return {
        "Toxicity": drug.toxicity,
        "Indication": drug.indication,
    }


def build_safety_highlights_prompt(drug: DrugData) -> str:
    context = build_safety_highlights_context(drug)
    return dedent(
        f"""
        Provide 2-3 succinct, non-prescriptive safety or handling highlights for a B2B API catalog.
        Base the points on toxicity or adverse effect information. Avoid patient advice and stick to technical tone.

        { _context_lines(context) or 'No toxicity data provided' }

        Highlights:
        """
    ).strip()


def _select_main_functional_class(
    therapeutic_class: Optional[Sequence[str]], classification_description: Optional[str]
) -> Optional[str]:
    if therapeutic_class:
        for entry in therapeutic_class:
            if entry and str(entry).strip():
                return str(entry).strip()

    if classification_description:
        cleaned = " ".join(classification_description.split()).strip()
        if not cleaned:
            return None

        for delimiter in (".", ";", ",", "|"):
            if delimiter in cleaned:
                cleaned = cleaned.split(delimiter)[0]
                break

        if len(cleaned) > 80:
            cleaned = cleaned[:80].rsplit(" ", 1)[0] or cleaned[:80]

        return cleaned.strip()

    return None


def _normalize_spacing(text: str) -> str:
    return " ".join(text.split())


def build_meta_description(
    api_name: str,
    cas_number: str,
    drug_type: str,
    state: str,
    therapeutic_class: Sequence[str] | None,
    classification_description: Optional[str],
    max_length: int = 155,
) -> str:
    main_class = _select_main_functional_class(therapeutic_class, classification_description)

    tech_parts = []
    if main_class:
        tech_parts.append(main_class)
    if drug_type:
        tech_parts.append(drug_type)
    if state:
        tech_parts.append(state)
    tech_parts.append("API")

    tech_phrase = " ".join(part.strip() for part in tech_parts if part and str(part).strip())

    safe_api = api_name or ""
    safe_cas = cas_number or ""
    safe_type = drug_type or ""
    safe_state = state or ""

    candidates = [
        f"CAS: {safe_cas} | {tech_phrase} | Find GMP {safe_api} API manufacturers. Review supplier docs, certifications and request quotes",
        f"CAS: {safe_cas} | Find GMP {safe_api} {safe_type} {safe_state} API manufacturers. Review supplier docs, certifications and request quotes",
        f"CAS: {safe_cas} | Find GMP {safe_api} {safe_type} API manufacturers. Review supplier docs, certifications and request quotes",
        f"CAS: {safe_cas} | Find {safe_api} {safe_type} API manufacturers. Review supplier docs and request quotes",
        f"Find {safe_api} {safe_type} API manufacturers. Review supplier docs and request quotes",
    ]

    cleaned_candidates = [_normalize_spacing(candidate).strip(" |") for candidate in candidates]

    for candidate in cleaned_candidates:
        if len(candidate) <= max_length:
            return candidate

    return cleaned_candidates[-1]


def build_buyer_cheatsheet_context(drug: DrugData) -> Dict[str, object]:
    return {
        "Name": drug.name,
        "Indication": drug.indication,
        "Dosage forms": [d.form for d in drug.dosages if getattr(d, "form", None)],
        "Routes": sorted({d.route for d in drug.dosages if getattr(d, "route", None)}),
        "Markets": unique_countries_from_products(drug.products),
        "Approval status": drug.groups,
    }


def build_buyer_cheatsheet_prompt(drug: DrugData) -> str:
    context = build_buyer_cheatsheet_context(drug)
    return dedent(
        f"""
        You are writing a quick cheatsheet for B2B pharma API buyers (sourcing managers). Based on the data below, write exactly 3 plain-text sentences (one per line, no bullet symbols or numbering) that cover: (1) formulation type (e.g. injectable peptide or oral small molecule), (2) main therapeutic use(s), and (3) key regulatory markets or approval status (e.g. FDA/EMA approved).
        Use non-clinical, B2B language. Do not give dosing or treatment recommendations.

        { _context_lines(context) or 'No product data provided' }

        3 sentences (one per line, no bullet characters):
        """
    ).strip()

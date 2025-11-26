"""Prompt and content generation helpers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from textwrap import dedent
from typing import Dict, List

from src.models import DrugData, Patent


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


def build_description_prompt(drug: DrugData) -> str:
    fields: Dict[str, str] = {
        "API Name": _format_optional(drug.name),
        "CAS Number": _format_optional(drug.cas_number),
        "UNII": _format_optional(drug.unii),
        "Indication": _format_optional(drug.indication),
        "Pharmacodynamics": _format_optional(drug.pharmacodynamics),
        "Mechanism of Action": _format_optional(drug.mechanism_of_action),
        "Absorption": _format_optional(drug.absorption),
        "Distribution": _format_optional(drug.volume_of_distribution),
        "Metabolism": _format_optional(drug.metabolism),
        "Elimination": _format_optional(drug.route_of_elimination),
        "Half-life": _format_optional(drug.half_life),
        "Clearance": _format_optional(drug.clearance),
        "Protein Binding": _format_optional(drug.protein_binding),
        "Groups/Approval": _format_optional(drug.groups),
        "Drug Categories": _format_optional(drug.categories),
        "International Brands": _format_optional(drug.international_brands),
        "Top Products": _format_optional(drug.products),
        "Classification": _format_optional(drug.classification),
        "Toxicity": _format_optional(drug.toxicity),
        "Chemical Properties": _format_optional(
            {
                "Molecular Formula": drug.molecular_formula,
                "Average Mass": drug.average_mass,
                "LogP": drug.logp,
                "Water Solubility": drug.water_solubility,
                "SMILES": drug.smiles,
            }
        ),
    }

    formatted = "\n".join(f"- {key}: {value}" for key, value in fields.items())
    return dedent(
        f"""
        You are a senior pharmaceutical medical writer crafting authoritative product content for formulation scientists, sourcing managers, and regulatory affairs teams.
        Write a 260-320 word description contained entirely within a single <p> tag.
        The writing must be technically rigorous, globally relevant, and avoid promotional claims.
        Emphasize: clinical indication, pharmacology, mechanism of action, key ADME parameters, safety/toxicity considerations, and any notable brands or usage contexts.
        Close with a concise note on sourcing or quality considerations relevant to API procurement.

        Use this structured DrugBank-derived data:
        {formatted}

        Output requirements:
        - Produce clean HTML with no inline styles.
        - Use short paragraphs separated by <br> elements inside the <p>.
        - Avoid placeholder text; omit any unknown details rather than fabricating.
        - Keep language neutral and compliant.
        """
    ).strip()


def build_summary_prompt(drug: DrugData, description: str) -> str:
    return dedent(
        f"""
        Summarize the following API description for quick catalog previews.
        Output 1-2 sentences highlighting indication, mechanism, and sourcing/quality notes.
        Avoid marketing language and do not exceed 60 words.

        Drug: {drug.name or 'Unknown'}
        CAS: {drug.cas_number or 'N/A'}
        Description:
        {description}
        """
    ).strip()


def build_summary_sentence_prompt(drug: DrugData) -> str:
    return dedent(
        f"""
        Write exactly one simple, patient-friendly sentence (18-30 words) that introduces the medication.
        Start with 'A medication that ...' and describe only the high-level therapeutic effect and use-cases.
        Avoid brand or company names and keep it informational.

        Drug name: {drug.name or 'Unknown'}
        Indication: {_format_optional(drug.indication)}
        Mechanism: {_format_optional(drug.mechanism_of_action)}
        Pharmacodynamics: {_format_optional(drug.pharmacodynamics)}
        """
    ).strip()


def build_pharmacology_summary_prompt(drug: DrugData) -> str:
    return dedent(
        f"""
        Create 2-3 concise sentences that summarize this drug's pharmacology and mechanism in high-level, non-promotional language.
        Focus on therapeutic intent, primary targets, and major pharmacodynamic themes. Avoid dosing guidance and clinical advice.

        Mechanism of action: {_format_optional(drug.mechanism_of_action)}
        Pharmacodynamics: {_format_optional(drug.pharmacodynamics)}
        Targets: {_format_optional([t.name for t in drug.targets if t.name])}
        Indication: {_format_optional(drug.indication)}
        """
    ).strip()


def build_lifecycle_summary_prompt(drug: DrugData, patents: List[Patent], markets: List[str]) -> str:
    patent_lines = []
    for patent in patents[:5]:
        parts = [patent.number or "", patent.country or "", patent.approved_date or "", patent.expires_date or ""]
        patent_lines.append(" | ".join(part for part in parts if part))
    patent_block = "\n".join(f"- {line}" for line in patent_lines) if patent_lines else "- None listed"
    markets_text = ", ".join(markets) if markets else "Unknown"
    return dedent(
        f"""
        Draft a short lifecycle summary (1-2 sentences) for an API based on patent expiry timing and where products are marketed.
        Keep it neutral, non-promotional, and focused on market maturity.

        Patents:
        {patent_block}
        Markets: {markets_text}
        """
    ).strip()


def build_safety_highlights_prompt(drug: DrugData) -> str:
    return dedent(
        f"""
        Provide 2-3 succinct, non-prescriptive safety or handling highlights for a B2B API catalog.
        Base the points on toxicity or adverse effect information. Avoid patient advice and stick to technical tone.

        Toxicity: {_format_optional(drug.toxicity)}
        Indication: {_format_optional(drug.indication)}
        """
    ).strip()

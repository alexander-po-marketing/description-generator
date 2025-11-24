"""Prompt and content generation helpers."""

from __future__ import annotations

from textwrap import dedent
from typing import Dict

from models import DrugData


def _format_optional(value) -> str:
    if value is None:
        return "Not specified"
    if isinstance(value, list):
        return ", ".join(value) if value else "Not specified"
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

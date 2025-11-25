"""Render DrugData and GeneratedContent to structured HTML."""

from __future__ import annotations

import html
from typing import List, Tuple

from src.models import DrugData, GeneratedContent


def _dl(entries: List[Tuple[str, str]]) -> str:
    safe_entries = [
        (html.escape(label), value)
        for label, value in entries
        if value
    ]
    if not safe_entries:
        return ""
    rows = "".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in safe_entries)
    return f"<dl>{rows}</dl>"


def _join_list(values: List[str]) -> str:
    return ", ".join(html.escape(v) for v in values if v)


def render_section(title: str, content: str) -> str:
    if not content:
        return ""
    return f"<section><h3>{html.escape(title)}</h3>{content}</section>"


def render_identification(drug: DrugData, generated: GeneratedContent) -> str:
    entries = [
        ("Summary", generated.summary),
        ("Groups", _join_list(drug.groups)),
        ("Drug Categories", _join_list(drug.categories)),
        ("Brand Names", _join_list(drug.international_brands or drug.products)),
        ("State", html.escape(drug.state) if drug.state else ""),
        ("Average Mass", html.escape(drug.average_mass) if drug.average_mass else ""),
    ]
    return render_section("Identification", _dl(entries))


def render_pharmacology(drug: DrugData) -> str:
    entries = [
        ("Indication", drug.indication or ""),
        ("Pharmacodynamics", drug.pharmacodynamics or ""),
        ("Mechanism of Action", drug.mechanism_of_action or ""),
        ("Absorption", drug.absorption or ""),
        ("Volume of Distribution", drug.volume_of_distribution or ""),
        ("Protein Binding", drug.protein_binding or ""),
        ("Metabolism", drug.metabolism or ""),
        ("Route of Elimination", drug.route_of_elimination or ""),
        ("Half-life", drug.half_life or ""),
        ("Clearance", drug.clearance or ""),
        ("Toxicity", drug.toxicity or ""),
    ]
    return render_section("Pharmacology", _dl(entries))


def render_taxonomy(drug: DrugData) -> str:
    if not drug.classification:
        return ""
    entries = [(key.title(), value) for key, value in drug.classification.items()]
    return render_section("Chemical Taxonomy", _dl(entries))


def render_references(drug: DrugData) -> str:
    parts = []
    if drug.general_references:
        entries = [(key.replace("_", " ").title(), value) for key, value in drug.general_references.items()]
        parts.append(render_section("General References", _dl(entries)))

    if drug.external_links:
        items = [link.strip() for link in drug.external_links.split("|") if link.strip()]
        rows = "".join(
            f"<li>{html.escape(item)}</li>"
            for item in items
        )
        parts.append(render_section("External Links", f"<ul>{rows}</ul>"))

    return "".join(parts)


def render_html(drug: DrugData, generated: GeneratedContent) -> str:
    description = generated.description_html
    identification = render_identification(drug, generated)
    pharmacology = render_pharmacology(drug)
    taxonomy = render_taxonomy(drug)
    references = render_references(drug)

    sections = "".join(
        part for part in [identification, taxonomy, pharmacology, references] if part
    )
    return f"<h3>General Description</h3>{description}{sections}"

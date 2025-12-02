"""Generate structured HTML previews from API page models."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence, Tuple


def _escape(value: object) -> str:
    return html.escape(str(value))


def _chip_list(items: Iterable[object]) -> str:
    chips = [f"<span class=\"tag\">{_escape(item)}</span>" for item in items if item]
    return f"<div class=\"tag-list\">{''.join(chips)}</div>" if chips else ""


def _bullet_list(items: Iterable[object]) -> str:
    entries = [f"<li>{_escape(item)}</li>" for item in items if item]
    return f"<ul class=\"bullet-list\">{''.join(entries)}</ul>" if entries else ""


def _table_from_mapping(values: Mapping[str, object], labels: Sequence[Tuple[str, str]]) -> str:
    rows = []
    for key, label in labels:
        if key not in values:
            continue
        value = values.get(key)
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            rendered_value = ", ".join(str(item) for item in value if item)
        else:
            rendered_value = str(value)
        if rendered_value:
            rows.append(f"<div class=\"fact\"><div class=\"fact__label\">{_escape(label)}</div><div class=\"fact__value\">{_escape(rendered_value)}</div></div>")
    return f"<div class=\"api-profile__grid\">{''.join(rows)}</div>" if rows else ""


def _targets_table(targets: Sequence[Mapping[str, object]] | None) -> str:
    if not targets:
        return ""
    rows = []
    for target in targets:
        if not isinstance(target, Mapping):
            continue
        name = target.get("name") or target.get("id")
        organism = target.get("organism")
        actions = target.get("actions") if isinstance(target.get("actions"), list) else []
        cells = [
            _escape(name) if name else "",
            _escape(organism) if organism else "",
            _escape(", ".join(actions)) if actions else "",
        ]
        rows.append(f"<tr><td>{cells[0]}</td><td>{cells[1]}</td><td>{cells[2]}</td></tr>")
    if not rows:
        return ""
    header = "<tr><th>Name</th><th>Organism</th><th>Actions</th></tr>"
    return f"<table class=\"data-table\"><thead>{header}</thead><tbody>{''.join(rows)}</tbody></table>"


def _section(title: str, *, summary: str | None = None, body: str = "", open_default: bool = False) -> str:
    if not summary and not body:
        return ""
    caret = "⌄"
    hint = f"<div class=\"api-section__hint\">{_escape(summary)}</div>" if summary else ""
    return (
        f"<details class=\"api-section\"{' open' if open_default else ''}>"
        f"<summary class=\"api-section__header\">"
        f"<div class=\"api-section__title\"><h3>{_escape(title)}</h3>"
        f"{hint}</div>"
        f"<span class=\"api-section__icon\">{caret}</span>"
        f"</summary>"
        f"<div class=\"api-section__body\">{body}</div>"
        f"</details>"
    )


def _section_body(*parts: str) -> str:
    return "".join(part for part in parts if part)


def _build_sections(sections: Mapping[str, object]) -> str:
    rendered = []

    clinical = sections.get("clinicalOverview", {}) if isinstance(sections, Mapping) else {}
    clinical_body = _section_body(
        f"<p>{_escape(clinical.get('summary'))}</p>" if clinical.get("summary") else "",
        _bullet_list(clinical.get("details", [])),
    )
    rendered.append(_section("Clinical overview", summary=clinical.get("summary"), body=clinical_body, open_default=True))

    identification = sections.get("identificationClassification", {}) if isinstance(sections, Mapping) else {}
    identification_table = _table_from_mapping(
        identification.get("table", {}) if isinstance(identification, Mapping) else {},
        [
            ("synonyms", "Synonyms"),
            ("brandNames", "Brand names"),
            ("groups", "Groups"),
            ("categories", "Categories"),
        ],
    )
    identification_body = _section_body(
        f"<p>{_escape(identification.get('summary'))}</p>" if identification.get("summary") else "",
        identification_table,
        _bullet_list(identification.get("details", [])),
    )
    rendered.append(_section("Identification & classification", summary=identification.get("summary"), body=identification_body))

    pharmacology = sections.get("pharmacologyTargets", {}) if isinstance(sections, Mapping) else {}
    pharmacology_body = _section_body(
        f"<p>{_escape(pharmacology.get('summary'))}</p>" if pharmacology.get("summary") else "",
        _bullet_list(pharmacology.get("details", [])),
        _targets_table(pharmacology.get("targets")),
    )
    rendered.append(_section("Pharmacology & targets", summary=pharmacology.get("summary"), body=pharmacology_body))

    adme = sections.get("admePk", {}) if isinstance(sections, Mapping) else {}
    adme_table = _table_from_mapping(
        adme.get("table", {}) if isinstance(adme, Mapping) else {},
        [
            ("absorption", "Absorption"),
            ("halfLife", "Half-life"),
            ("proteinBinding", "Protein binding"),
            ("metabolism", "Metabolism"),
            ("routeOfElimination", "Route of elimination"),
            ("volumeOfDistribution", "Volume of distribution"),
            ("clearance", "Clearance"),
        ],
    )
    adme_body = _section_body(
        f"<p>{_escape(adme.get('summary'))}</p>" if adme.get("summary") else "",
        adme_table,
    )
    rendered.append(_section("ADME / PK", summary=adme.get("summary"), body=adme_body))

    formulation = sections.get("formulationHandling", {}) if isinstance(sections, Mapping) else {}
    formulation_body = _section_body(
        f"<p>{_escape(formulation.get('summary'))}</p>" if formulation.get("summary") else "",
        _bullet_list(formulation.get("bullets", [])),
    )
    rendered.append(_section("Formulation & handling", summary=formulation.get("summary"), body=formulation_body))

    regulatory = sections.get("regulatoryMarket", {}) if isinstance(sections, Mapping) else {}
    regulatory_body = _section_body(
        f"<p>{_escape(regulatory.get('summary'))}</p>" if regulatory.get("summary") else "",
        _bullet_list(regulatory.get("details", [])),
    )
    rendered.append(_section("Regulatory & market", summary=regulatory.get("summary"), body=regulatory_body))

    safety = sections.get("safetyRisks", {}) if isinstance(sections, Mapping) else {}
    safety_body = _section_body(
        f"<p>{_escape(safety.get('summary'))}</p>" if safety.get("summary") else "",
        _bullet_list(safety.get("warnings", [])),
        f"<div class=\"pill-section-title\">Toxicity</div><p>{_escape(safety.get('toxicity'))}</p>" if safety.get("toxicity") else "",
    )
    rendered.append(_section("Safety & risks", summary=safety.get("summary"), body=safety_body))

    buyer = sections.get("buyerCheatsheet", {}) if isinstance(sections, Mapping) else {}
    buyer_body = _section_body(_bullet_list(buyer.get("bullets", [])))
    rendered.append(_section("Buyer cheatsheet", summary=None, body=buyer_body))

    return "".join(part for part in rendered if part)


def _page_wrapper(page_name: str, content: str) -> str:
    return (
        f"<section class=\"api-profile\" data-api-name=\"{_escape(page_name)}\">"
        f"{content}"
        f"</section>"
    )


def generate_html_preview(api_pages: Dict[str, object]) -> str:
    """Render an HTML preview for the new technical profile structure."""

    base_styles = """
    <style>
    :root {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
      color: #111827;
      background-color: #f3f4f6;
    }
    body { margin: 0; padding: 24px; }
    .api-profile { max-width: 1080px; margin: 0 auto 24px; background: #ffffff; border-radius: 16px; padding: 24px 24px 32px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08); border: 1px solid #e5e7eb; }
    .api-profile__label { text-transform: uppercase; font-size: 11px; letter-spacing: 0.12em; font-weight: 600; color: #6b7280; margin-bottom: 4px; }
    .api-profile__title { font-size: 24px; font-weight: 700; margin: 0 0 8px; color: #111827; }
    .api-profile__subtitle { font-size: 14px; color: #4b5563; margin-bottom: 16px; }
    .api-profile__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px 24px; margin-bottom: 16px; }
    .fact { font-size: 13px; }
    .fact__label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #9ca3af; margin-bottom: 2px; }
    .fact__value { font-weight: 500; color: #111827; }
    .tag-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 16px; }
    .tag { font-size: 11px; padding: 4px 8px; border-radius: 999px; background: #f3f4f6; color: #374151; border: 1px solid #e5e7eb; white-space: nowrap; }
    .pill-section-title { font-size: 13px; font-weight: 600; color: #6b7280; margin-top: 8px; margin-bottom: 4px; }
    .bullet-list { margin: 0; padding-left: 18px; font-size: 13px; color: #111827; }
    .bullet-list li { margin-bottom: 4px; }
    .api-sections { margin-top: 24px; border-top: 1px solid #e5e7eb; padding-top: 8px; }
    .api-section { border-radius: 12px; border: 1px solid #e5e7eb; margin-top: 12px; overflow: hidden; background: #f9fafb; }
    .api-section__header { width: 100%; display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: #f3f4f6; border: none; outline: none; cursor: pointer; }
    .api-section__title { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }
    .api-section__title h3 { margin: 0; font-size: 14px; font-weight: 600; color: #111827; }
    .api-section__hint { font-size: 12px; color: #9ca3af; }
    .api-section__icon { font-size: 18px; color: #9ca3af; transition: transform 0.15s ease; }
    details[open] .api-section__icon { transform: rotate(180deg); }
    .api-section__body { padding: 12px 14px 16px; font-size: 14px; color: #111827; }
    .data-table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    .data-table th, .data-table td { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; font-size: 12px; }
    </style>
    """

    page_entries = api_pages.items() if isinstance(api_pages, Mapping) else enumerate(api_pages)
    page_sections = []

    for page_key, page in page_entries:
        if isinstance(page, Mapping) and "raw" in page:
            page = page.get("raw", {})
        if not isinstance(page, Mapping):
            continue

        tech_profile = page.get("technicalProfile", {}) if isinstance(page, Mapping) else {}
        hero = tech_profile.get("hero", {}) if isinstance(tech_profile, Mapping) else {}
        sections = tech_profile.get("sections", {}) if isinstance(tech_profile, Mapping) else {}
        page_name = hero.get("title") or str(page_key)

        tags = _chip_list(hero.get("tags", []))
        facts = _table_from_mapping(
            hero.get("facts", {}) if isinstance(hero, Mapping) else {},
            [
                ("genericName", "Generic name"),
                ("moleculeType", "Molecule type"),
                ("casNumber", "CAS number"),
                ("drugbankId", "DrugBank ID"),
                ("approvalStatus", "Approval status"),
                ("atcCode", "ATC code"),
            ],
        )

        primary_indications = _bullet_list(tech_profile.get("primaryIndications", []))
        sections_html = _build_sections(sections)

        content_parts = [
            "<div class=\"api-profile__label\">Technical profile</div>",
            f"<h1 class=\"api-profile__title\">{_escape(hero.get('title') or page_name)}</h1>",
            f"<p class=\"api-profile__subtitle\">{_escape(hero.get('shortDesc'))}</p>" if hero.get("shortDesc") else "",
            tags,
            facts,
            f"<div class=\"pill-section-title\">Primary indications</div>{primary_indications}" if primary_indications else "",
            f"<div class=\"api-sections\">{sections_html}</div>" if sections_html else "",
        ]

        page_sections.append(_page_wrapper(page_name, "".join(part for part in content_parts if part)))

    body = "".join(page_sections)
    return f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">{base_styles}</head><body>{body}</body></html>"


def save_html_preview(api_pages: Dict[str, object], output_path: str) -> str:
    """Generate the preview HTML and persist it to ``output_path``."""

    html_preview = generate_html_preview(api_pages)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html_preview, encoding="utf-8")
    return html_preview


__all__ = ["generate_html_preview", "save_html_preview"]

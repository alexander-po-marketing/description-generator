"""Render grouped FAQ HTML blocks from generated FAQs."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from src.faq_generator import FAQ_TEMPLATES

GROUP_ORDER: Sequence[str] = ("technical", "regulatory", "sourcing", "pharmaoffer")
FAQ_ORDER: Mapping[str, Sequence[str]] = {
    "technical": (
        "basic_use",
        "primary_indications",
        "therapeutic_class",
        "mechanism_of_action",
        "safety_toxicity",
        "formulation_handling",
        "stability_concerns",
        "small_molecule",
    ),
    "regulatory": ("regions_approved", "regulatory_patent", "patent_expiry"),
    "sourcing": (
        "sourcing",
        "sourcing_documents",
        "manufacturers",
        "producing_countries",
        "supplier_count",
        "gmp_certifications",
        "gmp_audit",
        "typical_moq",
        "quote_requests",
    ),
    "pharmaoffer": ("smart_sourcing", "pro_data", "market_report"),
}
GROUP_TITLES: Mapping[str, str] = {
    "technical": "Technical",
    "regulatory": "Regulatory",
    "sourcing": "Sourcing",
    "pharmaoffer": "Pharmaoffer",
}
ID_TO_GROUP: Mapping[str, str] = {template.id: template.group for template in FAQ_TEMPLATES}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render FAQ HTML blocks from generated FAQs")
    parser.add_argument("--input", default="outputs/api_faqs.json", help="Path to generated FAQs JSON")
    parser.add_argument(
        "--output", default="outputs/section_html/faq_blocks.json", help="Destination for FAQ HTML blocks"
    )
    return parser.parse_args(argv or None)


def _escape(value: object) -> str:
    return html.escape(str(value))


def load_faqs(path: Path) -> Dict[str, List[Mapping[str, object]]]:
    if not path.exists():
        raise FileNotFoundError(f"FAQ JSON not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object mapping API IDs to FAQ arrays")
    return data


def _determine_group(faq: Mapping[str, object]) -> str:
    faq_id = str(faq.get("id", ""))
    group = ID_TO_GROUP.get(faq_id) or faq.get("group") or ""
    return str(group)


def _sort_faqs_by_order(faqs: Sequence[Mapping[str, object]], group: str) -> List[Mapping[str, object]]:
    order = {faq_id: index for index, faq_id in enumerate(FAQ_ORDER.get(group, ()))}
    return sorted(
        faqs,
        key=lambda item: (
            order.get(str(item.get("id")), len(order)),
            str(item.get("question", "")),
        ),
    )


def _render_faq_item(faq: Mapping[str, object]) -> str:
    faq_id = _escape(faq.get("id", ""))
    question = _escape(faq.get("question", ""))
    answer = _escape(faq.get("answer", ""))
    return (
        f"<details class=\"raw-material-seo-faq-item\" data-faq-id=\"{faq_id}\">"
        f"<summary class=\"raw-material-seo-faq-item__question\">{question}</summary>"
        f"<div class=\"raw-material-seo-faq-item__answer\"><p>{answer}</p></div>"
        "</details>"
    )


def _render_group(group: str, faqs: Sequence[Mapping[str, object]]) -> str:
    if not faqs:
        return ""
    items = [_render_faq_item(faq) for faq in faqs]
    title = _escape(GROUP_TITLES.get(group, group.title()))
    group_class = _escape(group)
    return (
        f"<article class=\"raw-material-seo-faq-group raw-material-seo-faq-group--{group_class}\">"
        "<header class=\"raw-material-seo-faq-group__header\">"
        f"<h3 class=\"raw-material-seo-faq-group__title\">{title}</h3>"
        "</header>"
        "<div class=\"raw-material-seo-faq-group__body\">"
        f"{''.join(items)}"
        "</div>"
        "</article>"
    )


def _group_faqs(faqs: Sequence[Mapping[str, object]]) -> Dict[str, List[Mapping[str, object]]]:
    grouped: Dict[str, List[Mapping[str, object]]] = {}
    for faq in faqs:
        group = _determine_group(faq)
        if not group:
            continue
        grouped.setdefault(group, []).append(faq)
    return grouped


def _render_faq_section(drug_id: str, faqs: Sequence[Mapping[str, object]]) -> str:
    grouped = _group_faqs(faqs)
    ordered_groups = []
    for group in GROUP_ORDER:
        if group not in grouped:
            continue
        sorted_group = _sort_faqs_by_order(grouped[group], group)
        group_html = _render_group(group, sorted_group)
        if group_html:
            ordered_groups.append(group_html)
    if not ordered_groups:
        return ""

    groups_html = "".join(ordered_groups)
    title = _escape(drug_id)
    return (
        "<section class=\"raw-material-seo-faq\" id=\"raw-material-seo-faq\">"
        f"<h2 class=\"raw-material-seo-faq__title\">Frequently asked questions about {title} API</h2>"
        "<div class=\"raw-material-seo-faq__groups\">"
        f"{groups_html}"
        "</div>"
        "</section>"
    )


def render_faq_blocks(api_faqs: Mapping[str, object]) -> Dict[str, Dict[str, str]]:
    rendered: Dict[str, Dict[str, str]] = {}
    for drug_id, faqs in api_faqs.items():
        if not isinstance(faqs, list):
            continue
        section_html = _render_faq_section(str(drug_id), faqs)
        if section_html:
            rendered[str(drug_id)] = {"full": section_html}
    return rendered


def save_blocks(blocks: Mapping[str, Dict[str, str]], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(blocks, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(list(argv) if argv is not None else None)

    input_path = Path(args.input)
    output_path = Path(args.output)

    api_faqs = load_faqs(input_path)
    blocks = render_faq_blocks(api_faqs)
    save_blocks(blocks, output_path)
    print(f"Wrote FAQ HTML blocks for {len(blocks)} APIs to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

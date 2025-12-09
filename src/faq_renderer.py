"""Render grouped FAQ HTML blocks from generated FAQs, with schema.org markup,
Twig placeholders, and per-group collapse (3 visible questions + teaser)."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from src.faq_generator import FAQ_TEMPLATES

# Order of groups in the output
GROUP_ORDER: Sequence[str] = ("technical", "regulatory", "sourcing", "pharmaoffer")

# Order of questions within each group
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

# Human-readable titles for groups
GROUP_TITLES: Mapping[str, str] = {
    "technical": "Technical",
    "regulatory": "Regulatory",
    "sourcing": "Sourcing",
    "pharmaoffer": "Pharmaoffer",
}

# Mapping of FAQ id → group from FAQ_TEMPLATES
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


# [[placeholder]] → {{ placeholder }} for Twig
_PLACEHOLDER_PATTERN = re.compile(r"\[\[([a-zA-Z0-9_]+)\]\]")


def _replace_placeholders_with_twig(answer: str) -> str:
    return _PLACEHOLDER_PATTERN.sub(r"{{ \1 }}", answer)


# Patterns for extracting API name from questions
NAME_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"^What is\s+(.+?)\s*\(CAS\b", re.IGNORECASE),
    re.compile(r"^What is\s+(.+?)\s+API\b", re.IGNORECASE),
    re.compile(r"^What conditions is\s+(.+?)\s+mainly prescribed for\?", re.IGNORECASE),
    re.compile(r"^Which therapeutic class does\s+(.+?)\s+fall into\?", re.IGNORECASE),
    re.compile(r"^How does\s+(.+?)\s+work\?", re.IGNORECASE),
)


def _infer_drug_name(drug_id: str, faqs: Sequence[Mapping[str, object]]) -> str:
    """
    Try to extract a readable API name from the question texts.
    If extraction fails, fallback to using drug_id.
    """
    for faq in faqs:
        question = str(faq.get("question", "")).strip()
        if not question:
            continue
        for pattern in NAME_PATTERNS:
            match = pattern.search(question)
            if match:
                name = match.group(1).strip()
                if name:
                    return name
    return drug_id


def _slugify_id(raw: str) -> str:
    """
    Create a safe fragment id based on drug_id.
    """
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or raw


def _render_faq_item(faq: Mapping[str, object]) -> str:
    """
    Render a single FAQ item with microdata (Question + Answer).
    The .raw-material-seo-faq-item class can be modified externally (teaser/extra).
    """
    faq_id = _escape(faq.get("id", ""))
    question = _escape(faq.get("question", ""))

    raw_answer = str(faq.get("answer", ""))
    answer_with_twig = _replace_placeholders_with_twig(raw_answer)
    # Do not escape so Twig placeholders {{ var }} remain functional.
    # It is assumed the answer comes from a controlled pipeline.

    return (
        '<details class="raw-material-seo-faq-item" '
        f'data-faq-id="{faq_id}" '
        'itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">'
        f'<summary class="raw-material-seo-faq-item__question" itemprop="name">{question}</summary>'
        '<div class="raw-material-seo-faq-item__answer" '
        'itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">'
        f'<p itemprop="text">{answer_with_twig}</p>'
        '</div>'
        '</details>'
    )


def _render_group(group: str, faqs: Sequence[Mapping[str, object]]) -> str:
    """
    Render a single group:
    - first 3 questions are shown normally
    - the 4th question gets .raw-material-seo-faq-item--teaser
    - questions 5+ get .raw-material-seo-faq-item--extra (hidden by CSS until expanded)
    - if there are more than 3 questions, add a "Show all questions" button
    """
    if not faqs:
        return ""

    items_html: List[str] = []
    for idx, faq in enumerate(faqs):
        extra_class = ""
        if idx == 2:  # 3rd
            extra_class = " raw-material-seo-faq-item--teaser"
        elif idx > 2:  # 4+
            extra_class = " raw-material-seo-faq-item--extra"

        base_html = _render_faq_item(faq)
        # Insert the modifier class only into the first occurrence of class="raw-material-seo-faq-item"
        if extra_class:
            item_html = base_html.replace(
                'class="raw-material-seo-faq-item"',
                f'class="raw-material-seo-faq-item{extra_class}"',
                1,
            )
        else:
            item_html = base_html

        items_html.append(item_html)

    title = _escape(GROUP_TITLES.get(group, group.title()))
    group_class = _escape(group)

    body_html = "".join(items_html)

    # 'Show all questions' button only if questions > 3
    if len(faqs) > 2:
        toggle_html = (
            '<button type="button" class="raw-material-seo-faq-group__toggle" '
            'data-faq-toggle="group">Show all questions</button>'
        )
    else:
        toggle_html = ""

    return (
        f'<article class="raw-material-seo-faq-group raw-material-seo-faq-group--{group_class}">'
        '<header class="raw-material-seo-faq-group__header">'
        f'<h3 class="raw-material-seo-faq-group__title">{title}</h3>'
        '</header>'
        '<div class="raw-material-seo-faq-group__body">'
        f'{body_html}'
        '</div>'
        f'{toggle_html}'
        '</article>'
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
    ordered_groups_html: List[str] = []

    for group in GROUP_ORDER:
        if group not in grouped:
            continue
        sorted_group = _sort_faqs_by_order(grouped[group], group)
        group_html = _render_group(group, sorted_group)
        if group_html:
            ordered_groups_html.append(group_html)

    if not ordered_groups_html:
        return ""

    groups_html = "".join(ordered_groups_html)

    # Human-readable drug name for the title
    drug_name = _infer_drug_name(drug_id, faqs)
    title_text = f"Frequently asked questions about {drug_name} API"
    section_id = _slugify_id(f"raw-material-seo-faq-{drug_id}")

    return (
        f'<section class="raw-material-seo-faq" id="{section_id}" '
        'itemscope itemtype="https://schema.org/FAQPage">'
        f'<h2 class="raw-material-seo-faq__title">{_escape(title_text)}</h2>'
        '<div class="raw-material-seo-faq__groups">'
        f"{groups_html}"
        "</div>"
        "</section>"
    )


def render_faq_blocks(api_faqs: Mapping[str, object]) -> Dict[str, Dict[str, str]]:
    """
    Input: dict[drug_id] -> list[faq]
    Output: dict[drug_id] -> {"full": "<section ...>...</section>"}
    """
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

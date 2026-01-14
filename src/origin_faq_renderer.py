"""Render origin FAQ HTML blocks and schema from generated origin FAQs."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from src.filtered_intent_postprocessor import ORIGIN_COUNTRY_LABELS, ORIGIN_REGION_LABELS

GROUP_ORDER: Sequence[str] = ("origin",)

FAQ_ORDER: Sequence[str] = (
    "origin_meaning",
    "origin_scope",
    "origin_not_guarantee",
    "origin_qualification",
    "origin_documents",
    "origin_documentation_check",
    "origin_logistics",
    "origin_risks",
    "origin_tradeoffs",
    "origin_rfq",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render origin FAQ HTML blocks from generated FAQs"
    )
    parser.add_argument(
        "--input",
        default="outputs/origin_faqs.json",
        help="Path to origin FAQs JSON",
    )
    parser.add_argument(
        "--output",
        default="outputs/section_html/origin_faq_blocks.json",
        help="Destination for origin FAQ HTML blocks",
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


NAME_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\bsourcing\s+(.+?)\s+from\b", re.IGNORECASE),
    re.compile(r"\bfor\s+(.+?)\s+manufacturers\b", re.IGNORECASE),
    re.compile(r"\bfor\s+(.+?)\s+suppliers\b", re.IGNORECASE),
    re.compile(r"\bfor\s+(.+?)\s+API\b", re.IGNORECASE),
)


def _infer_drug_name(drug_id: str, faqs: Sequence[Mapping[str, object]]) -> str:
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


def _origin_geo_from_key(origin_key: str) -> str:
    if origin_key.startswith("origin_country:"):
        _, _, code = origin_key.partition(":")
        return ORIGIN_COUNTRY_LABELS.get(code, code)
    if origin_key.startswith("origin_region:"):
        _, _, code = origin_key.partition(":")
        return ORIGIN_REGION_LABELS.get(code, code)
    return "origin"


def _infer_origin_meta(faqs: Sequence[Mapping[str, object]]) -> tuple[str, str]:
    for faq in faqs:
        origin_key = faq.get("origin_key")
        if isinstance(origin_key, str) and origin_key:
            return _origin_geo_from_key(origin_key), str(faq.get("origin_label") or "")
    return "origin", ""


def _slugify_id(raw: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or raw


def _sort_faqs(faqs: Sequence[Mapping[str, object]]) -> List[Mapping[str, object]]:
    order = {faq_id: index for index, faq_id in enumerate(FAQ_ORDER)}

    def _key(item: Mapping[str, object]) -> tuple[int, str]:
        template_id = str(item.get("template_id") or item.get("id") or "")
        base_id = template_id.split("__", 1)[0]
        return (order.get(base_id, len(order)), str(item.get("question", "")))

    return sorted(faqs, key=_key)


def _render_faq_item(faq: Mapping[str, object]) -> str:
    faq_id = _escape(faq.get("id", ""))
    question = _escape(faq.get("question", ""))
    answer = html.escape(str(faq.get("answer", "")))
    return (
        '<details class="raw-material-seo-faq-item" '
        f'data-faq-id="{faq_id}" '
        'itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">'
        f'<summary class="raw-material-seo-faq-item__question" itemprop="name">{question}</summary>'
        '<div class="raw-material-seo-faq-item__answer" '
        'itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">'
        f'<p itemprop="text">{answer}</p>'
        "</div>"
        "</details>"
    )


def _render_group(faqs: Sequence[Mapping[str, object]]) -> str:
    if not faqs:
        return ""
    items_html = "".join(_render_faq_item(faq) for faq in faqs)
    return (
        '<article class="raw-material-seo-faq-group raw-material-seo-faq-group--origin">'
        '<header class="raw-material-seo-faq-group__header">'
        "<h3 class=\"raw-material-seo-faq-group__title\">Origin</h3>"
        "</header>"
        '<div class="raw-material-seo-faq-group__body">'
        f"{items_html}"
        "</div>"
        "</article>"
    )


def _render_faq_section(api_id: str, faqs: Sequence[Mapping[str, object]]) -> str:
    if not faqs:
        return ""
    sorted_faqs = _sort_faqs(faqs)
    group_html = _render_group(sorted_faqs)
    if not group_html:
        return ""

    drug_name = _infer_drug_name(api_id, faqs)
    origin_geo, origin_label = _infer_origin_meta(faqs)
    if origin_label:
        title_text = (
            f"Frequently asked questions about {drug_name} API manufacturers in {origin_geo} — "
            f"{origin_label}"
        )
    else:
        title_text = f"Frequently asked questions about {drug_name} API manufacturers in {origin_geo}"
    section_id = _slugify_id(f"raw-material-seo-origin-faq-{api_id}")
    return (
        f'<section class="raw-material-seo-faq raw-material-seo-faq--origin" id="{section_id}" '
        'itemscope itemtype="https://schema.org/FAQPage">'
        f'<h2 class="raw-material-seo-faq__title">{_escape(title_text)}</h2>'
        '<div class="raw-material-seo-faq__groups">'
        f"{group_html}"
        "</div>"
        "</section>"
    )


def render_faq_blocks(api_faqs: Mapping[str, object]) -> Dict[str, Dict[str, str]]:
    rendered: Dict[str, Dict[str, str]] = {}
    for api_id, faqs in api_faqs.items():
        if not isinstance(faqs, list):
            continue
        section_html = _render_faq_section(str(api_id), faqs)
        if section_html:
            rendered[str(api_id)] = {"full": section_html}
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
    print(f"Wrote origin FAQ HTML blocks for {len(blocks)} APIs to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

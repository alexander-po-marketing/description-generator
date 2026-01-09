"""Certificate-focused FAQ generator for filtered API pages.

To add a new certificate filter, update FILTER_LABELS/FILTER_EXPLAINERS in
src/filtered_intent_postprocessor.py and include the new key in CERT_FILTER_KEYS
below.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.config import OpenAIConfig
from src.faq_generator import FAQTemplate, _extract_context, _has_required_fields
from src.filtered_intent_postprocessor import FILTER_EXPLAINERS, FILTER_LABELS
from src.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

CERT_FILTER_KEYS: Sequence[str] = (
    "gmp",
    "cep",
    "wc",
    "fda",
    "coa",
    "iso9001",
    "usdmf",
)

CERT_FAQ_TEMPLATES: List[FAQTemplate] = [
    FAQTemplate(
        id="cert_meaning",
        mode="llm",
        question="What does '{filter_label}' mean when sourcing {drug_name} API?",
        group="certification",
        context_keys=["regulatory", "supply"],
        tags=["meaning", "qualification"],
    ),
    FAQTemplate(
        id="cert_verification",
        mode="llm",
        question="How can buyers verify '{filter_label}' for {drug_name} suppliers?",
        group="certification",
        context_keys=["regulatory", "supply"],
        tags=["verification", "quality"],
    ),
    FAQTemplate(
        id="cert_documents",
        mode="llm",
        question="Which documents should be requested to confirm '{filter_label}' for {drug_name}?",
        group="certification",
        context_keys=["regulatory", "supply"],
        tags=["documentation", "buyer_actions"],
    ),
    FAQTemplate(
        id="cert_limitations",
        mode="llm",
        question="What are the limitations of '{filter_label}' for {drug_name}?",
        group="certification",
        context_keys=["regulatory"],
        tags=["limitations", "compliance"],
    ),
    FAQTemplate(
        id="cert_workflow",
        mode="llm",
        question="How does the '{filter_label}' filter change qualification steps for {drug_name} sourcing?",
        group="certification",
        context_keys=["regulatory", "supply"],
        tags=["workflow", "qualification"],
    ),
]


def _normalize_page(page: Mapping[str, object]) -> Mapping[str, object]:
    raw = page.get("raw")
    if isinstance(raw, Mapping):
        return raw
    return page


def _coerce_pages(data: object) -> Dict[str, object]:
    if isinstance(data, Mapping):
        if "pages" in data and isinstance(data.get("pages"), list):
            return _coerce_pages(data.get("pages"))
        return dict(data)
    if isinstance(data, list):
        pages: Dict[str, object] = {}
        for index, entry in enumerate(data):
            if isinstance(entry, Mapping):
                entry_id = entry.get("id") or entry.get("drug_id") or entry.get("drugId")
                key = str(entry_id) if entry_id is not None else str(index)
            else:
                key = str(index)
            pages[key] = entry
        return pages
    raise ValueError("Input JSON must be a mapping of ID to page model or a list of page entries")


def _load_json(path: str) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return _coerce_pages(data)


def _detect_filter_key(page: Mapping[str, object], override: Optional[str] = None) -> Optional[str]:
    if override:
        return override

    for candidate in _page_variants(page):
        filter_section = candidate.get("filter_section")
        if isinstance(filter_section, Mapping):
            for key in filter_section:
                if key in CERT_FILTER_KEYS:
                    return str(key)

        hero = candidate.get("hero")
        if isinstance(hero, Mapping):
            filter_intent = hero.get("filter_intent")
            if isinstance(filter_intent, Mapping):
                for nested_key in filter_intent:
                    if nested_key in CERT_FILTER_KEYS:
                        return str(nested_key)
                title = filter_intent.get("title")
                if isinstance(title, str):
                    normalized_title = title.lower()
                    for key, label in FILTER_LABELS.items():
                        if key in CERT_FILTER_KEYS and label.lower() in normalized_title:
                            return key

        filter_key = candidate.get("filter_key")
        if isinstance(filter_key, str) and filter_key in CERT_FILTER_KEYS:
            return filter_key

    return None


def _page_variants(page: Mapping[str, object]) -> Tuple[Mapping[str, object], ...]:
    normalized = _normalize_page(page)
    if normalized is page:
        return (page,)
    return (page, normalized)


def _format_context(context_slices: Mapping[str, str], context_keys: Sequence[str]) -> str:
    ordered_keys = list(context_keys) if context_keys else ["regulatory", "supply"]
    lines = []
    for key in ordered_keys:
        value = context_slices.get(key, "")
        if value:
            lines.append(f"- {key.title()}: {value}")
    return "\n".join(lines)


def _guardrails_for_filter(filter_key: str) -> List[str]:
    guardrails = [
        "Avoid clinical indications, side effects, or dosing guidance.",
        "Focus on sourcing, qualification, documentation, and compliance scope.",
    ]
    if filter_key == "fda":
        guardrails.append("Do not state or imply FDA approval of the product.")
    if filter_key == "iso9001":
        guardrails.append("State that ISO 9001 does not replace GMP requirements.")
    if filter_key == "coa":
        guardrails.append("Emphasize that CoA is batch-specific and not a long-term qualification document.")
    if filter_key == "cep":
        guardrails.append("Clarify that a CEP supports compliance but is not a marketing authorization.")
    if filter_key == "wc":
        guardrails.append("Explain that a Written Confirmation is tied to EU import GMP compliance.")
    if filter_key == "usdmf":
        guardrails.append("Note that a DMF is confidential and not an approval by itself.")
    return guardrails


def _build_llm_prompt(
    *,
    question: str,
    context: Mapping[str, str],
    context_slices: Mapping[str, str],
    template: FAQTemplate,
    filter_key: str,
) -> str:
    context_block = _format_context(context_slices, template.context_keys)
    guardrails = "\n".join(f"- {item}" for item in _guardrails_for_filter(filter_key))
    return (
        "You are an expert pharmaceutical procurement writer creating certificate-focused FAQs. "
        "Answer only the certificate qualification question using the provided context.\n\n"
        f"Question: {question}\n\n"
        "Certificate filter context:\n"
        f"- API name: {context.get('drug_name')}\n"
        f"- CAS: {context.get('cas')}\n"
        f"- Filter label: {context.get('filter_label')}\n"
        f"- Filter explainer: {context.get('filter_explainer')}\n"
        f"- Filter key: {context.get('filter_key')}\n"
        f"Additional context:\n{context_block}\n\n"
        "Constraints:\n"
        "- Keep the answer to 2-4 sentences.\n"
        "- Avoid marketing language, speculation, or promises.\n"
        "- Do not restate long intro copy.\n"
        f"{guardrails}\n"
        "- If context is insufficient, stay high-level and factual without inventing details."
    )


def _generate_llm_answer(
    *,
    template: FAQTemplate,
    question: str,
    context: Mapping[str, str],
    context_slices: Mapping[str, str],
    client: Optional[OpenAIClient],
    model: Optional[str],
    filter_key: str,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    if client is None:
        logger.warning("No OpenAI client available; skipping certificate FAQ %s", template.id)
        return None
    prompt = _build_llm_prompt(
        question=question,
        context=context,
        context_slices=context_slices,
        template=template,
        filter_key=filter_key,
    )
    return client.generate_text(prompt, model=model, max_tokens=max_tokens)


def generate_certificate_faqs_for_page(
    api_id: str,
    page: Mapping[str, object],
    *,
    templates: Sequence[FAQTemplate],
    client: Optional[OpenAIClient],
    model: Optional[str],
    max_faqs: Optional[int],
    filter_key: Optional[str],
) -> List[Dict[str, object]]:
    context, context_slices = _extract_context(api_id, page)
    detected_filter_key = _detect_filter_key(page, override=filter_key)
    if not detected_filter_key or detected_filter_key not in CERT_FILTER_KEYS:
        logger.info("Skipping %s due to missing certificate filter key", api_id)
        return []

    filter_label = FILTER_LABELS.get(detected_filter_key)
    filter_explainer = FILTER_EXPLAINERS.get(detected_filter_key)
    if not filter_label or not filter_explainer:
        logger.warning("Missing filter metadata for %s", detected_filter_key)
        return []

    context["filter_key"] = detected_filter_key
    context["filter_label"] = filter_label
    context["filter_explainer"] = filter_explainer

    faqs: List[Dict[str, object]] = []
    for template in templates:
        if max_faqs is not None and len(faqs) >= max_faqs:
            break
        if not _has_required_fields(template, context):
            continue

        try:
            question_text = template.question.format(**context)
        except KeyError as exc:
            logger.debug("Missing placeholder %s for question %s", exc, template.id)
            continue

        answer = _generate_llm_answer(
            template=template,
            question=question_text,
            context=context,
            context_slices=context_slices,
            client=client,
            model=model,
            filter_key=detected_filter_key,
            max_tokens=client.config.max_completion_tokens if client else None,
        )
        if not answer:
            logger.debug("Skipping FAQ %s for %s due to empty answer", template.id, api_id)
            continue

        output_id = f"{template.id}__{detected_filter_key}"
        faqs.append(
            {
                "id": output_id,
                "template_id": template.id,
                "group": template.group,
                "question": question_text,
                "answer": answer.strip(),
                "mode": template.mode,
                "tags": list(template.tags),
                "filter_key": detected_filter_key,
                "filter_label": filter_label,
            }
        )
    return faqs


def _generate_for_single_page(
    api_id: str,
    page: Mapping[str, object],
    *,
    templates: Sequence[FAQTemplate],
    client: Optional[OpenAIClient],
    model: Optional[str],
    max_faqs: Optional[int],
    filter_key: Optional[str],
) -> tuple[str, List[Dict[str, object]]]:
    if not isinstance(page, Mapping):
        logger.warning("Skipping %s because page entry is not a mapping", api_id)
        return api_id, []
    faqs = generate_certificate_faqs_for_page(
        api_id,
        page,
        templates=templates,
        client=client,
        model=model,
        max_faqs=max_faqs,
        filter_key=filter_key,
    )
    return api_id, faqs


def generate_certificate_faqs(
    pages: Mapping[str, object],
    *,
    templates: Sequence[FAQTemplate] = CERT_FAQ_TEMPLATES,
    client: Optional[OpenAIClient] = None,
    model: Optional[str] = None,
    max_faqs: Optional[int] = None,
    max_workers: int = 8,
    filter_key: Optional[str] = None,
) -> Dict[str, List[Dict[str, object]]]:
    faq_output: Dict[str, List[Dict[str, object]]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_api_id = {
            executor.submit(
                _generate_for_single_page,
                api_id,
                page,
                templates=templates,
                client=client,
                model=model,
                max_faqs=max_faqs,
                filter_key=filter_key,
            ): api_id
            for api_id, page in pages.items()
        }

        for future in concurrent.futures.as_completed(future_to_api_id):
            api_id = future_to_api_id[future]
            try:
                result_api_id, faqs = future.result()
            except Exception:
                logger.exception("Failed to generate certificate FAQs for %s", api_id)
                continue

            if faqs:
                faq_output[result_api_id] = faqs
    return faq_output


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate certificate-focused FAQs from filtered API page models"
    )
    parser.add_argument(
        "--input",
        default="outputs/filtered_api_pages.json",
        help="Path to filtered API pages JSON",
    )
    parser.add_argument(
        "--output",
        default="outputs/cert_filter_faqs.json",
        help="Output path for generated certificate FAQs",
    )
    parser.add_argument("--max-faqs", type=int, help="Maximum FAQs per API")
    parser.add_argument("--model", help="Override model for LLM FAQs (defaults to summary model)")
    parser.add_argument(
        "--filter-key",
        choices=sorted(CERT_FILTER_KEYS),
        help="Optional certificate filter key override",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    pages = _load_json(args.input)

    client: Optional[OpenAIClient] = None
    try:
        client = OpenAIClient(OpenAIConfig())
    except EnvironmentError as exc:  # pragma: no cover - env dependent
        logger.warning("OpenAI credentials missing; certificate FAQs will be skipped: %s", exc)
        client = None

    faqs = generate_certificate_faqs(
        pages,
        client=client,
        model=args.model,
        max_faqs=args.max_faqs,
        filter_key=args.filter_key,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(faqs, handle, ensure_ascii=False, indent=2)
    logger.info("Wrote certificate FAQs for %d APIs to %s", len(faqs), output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

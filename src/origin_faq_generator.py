"""Origin-focused FAQ generator for filtered API pages.

To add a new origin filter, update FILTER_LABELS/FILTER_EXPLAINERS and the
ORIGIN_* label/background maps in src/filtered_intent_postprocessor.py.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import logging
import os
import random
import re
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, TYPE_CHECKING

from src.config import OpenAIConfig
from src.faq_generator import FAQTemplate, _extract_context, _has_required_fields
if TYPE_CHECKING:
    from src.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

FILTER_LABELS = {
    "gmp": "GMP-certified",
    "cep": "with CEP available",
    "wc": "with Written Confirmation (WC)",
    "fda": "with US FDA-facing documentation",
    "coa": "with CoA provided for each batch",
    "iso9001": "with ISO 9001-certified quality systems",
    "usdmf": "with US DMF filed",
    "origin_country:IN": "Verified API manufacturers in India",
    "origin_country:CN": "Verified API manufacturers in China",
    "origin_country:US": "Verified American API manufacturers (United States)",
    "origin_country:JP": "Verified API manufacturers in Japan",
    "origin_country:KR": "Verified API manufacturers in South Korea",
    "origin_region:ASIA": "Produced in Asia",
    "origin_region:EUROPE": "Produced in Europe (EU)",
    "origin_region:NORTH_AMERICA": "Produced in North America",
    "origin_region:SOUTH_AMERICA": "Produced in South America",
}

FILTER_EXPLAINERS = {
    "gmp": "Suppliers that report manufacturing under Good Manufacturing Practice (GMP) and can provide GMP certificates or audit documentation.",
    "cep": "APIs for which a Certificate of Suitability (CEP) is reported, indicating compliance with the relevant Ph. Eur. monograph.",
    "wc": "Suppliers that can provide Written Confirmation (WC) for export to the EU, according to applicable guidelines.",
    "fda": "Suppliers linked to US FDA-regulated markets, typically through US DMF filings or FDA-registered facilities. Do not state that the finished product is FDA-approved.",
    "coa": "Suppliers that provide a Certificate of Analysis (CoA) for each batch of the API, detailing assay, impurities and key quality parameters.",
    "iso9001": "Suppliers whose quality management systems are certified according to ISO 9001.",
    "usdmf": "APIs for which a US Drug Master File (US DMF) has been filed by at least one supplier.",
    "origin_country:IN": "APIs manufactured by suppliers from India; buyers typically focus on EU/US GMP history, DMF availability, audit readiness, and predictable export logistics when sourcing from Indian production sites.",
    "origin_country:CN": "APIs manufactured by suppliers from China; procurement teams pay close attention to regulatory transparency, DMF status, inspection history, and international shipping reliability when evaluating Chinese manufacturers.",
    "origin_country:US": "APIs manufactured by suppliers from United States; buyers prioritize strong FDA compliance records, domestic supply security, and simplified logistics for US-origin material.",
    "origin_country:JP": "APIs manufactured by suppliers from Japan; sourcing teams evaluate strict quality standards, regulatory rigor, long-term supply reliability, and typically higher cost structures associated with Japanese production.",
    "origin_country:KR": "APIs manufactured by suppliers from South Korea; buyers assess regulatory compliance, technological capabilities, export readiness, and consistency of supply from Korean manufacturing sites.",
    "origin_region:ASIA": "APIs manufactured across Asia; procurement teams compare regulatory maturity, audit history, cost structures, and international logistics across multiple Asian production hubs.",
    "origin_region:EUROPE": "APIs manufactured in Europe; buyers align sourcing decisions around EMA compliance, high quality expectations, shorter lead times within the EU, and stable regulatory environments.",
    "origin_region:NORTH_AMERICA": "APIs manufactured in North America; sourcing teams emphasize regulatory trust, supply chain resilience, and streamlined logistics for regional production.",
    "origin_region:SOUTH_AMERICA": "APIs manufactured in South America; procurement teams assess regulatory alignment, export experience, lead times, and freight complexity when sourcing from regional manufacturers.",
}

ORIGIN_COUNTRY_LABELS: dict[str, str] = {
    "IN": "India",
    "CN": "China",
    "US": "United States",
    "JP": "Japan",
    "KR": "South Korea",
}

ORIGIN_REGION_LABELS: dict[str, str] = {
    "ASIA": "Asia",
    "EUROPE": "Europe",
    "NORTH_AMERICA": "North America",
    "SOUTH_AMERICA": "South America",
}

ORIGIN_COUNTRY_BACKGROUND: dict[str, str] = {
    "IN": (
        "India is a primary global source for API raw materials and finished APIs, offering scale, cost efficiency, and broad regulatory coverage.\n"
        "Buyers typically evaluate documentation depth (CoA, GMP, DMF) alongside raw material traceability.\n"
        "Logistics planning - especially port selection and incoterms - is often addressed upfront to manage lead-time variability."
    ),
    "CN": (
        "China combines scale and chemical depth in API and intermediate production, making it a key sourcing region globally..\n"
        "Buyers assess regulatory transparency, documentation depth, and material traceability as part of qualification.\n"
        "Logistics and customs planning are typically coordinated early to ensure predictable lead times."
    ),
    "US": (
        "US-based API production offers regulatory confidence and high supply chain transparency.\n"
        "Buyers focus on GMP evidence, FDA inspection outcomes, and documentation readiness.\n"
        "Shorter logistics cycles are common, though quality release and compliance reviews still govern delivery timelines."
    ),
    "JP": (
        "Japanese API production is valued for consistency, documentation discipline, and process reliability.\n"
        "Buyers assess certification completeness and data transparency early in qualification.\n"
        "Audit coordination and assessment planning are commonly built into sourcing timelines."
    ),
    "KR": (
        "Korean API production combines regulatory alignment with modern manufacturing capabilities.\n"
        "Buyers focus on GMP adherence, batch traceability, and documentation completeness.\n"
        "Logistics planning may factor in route reliability and cold-chain handling depending on the product."
    ),
}

ORIGIN_REGION_BACKGROUND: dict[str, str] = {
    "ASIA": (
        "Asian API sourcing offers scale and cost advantages alongside varied regulatory environments.\n"
        "Buyers assess qualification rigor, documentation depth, and logistics reliability on a country-by-country basis.\n"
        "GMP compliance, CoA validation, and supply chain traceability remain baseline requirements across the region."
    ),
    "EUROPE": (
        "European API production generally operates within EU GMP frameworks, supported by mature quality systems and regulatory oversight.\n"
        "Procurement teams review site credentials, CoA consistency, and applicable certificates such as CEPs where relevant to the product.\n"
        "Regional logistics often enable shorter and more predictable lead times into European markets."
    ),
    "NORTH_AMERICA": (
        "North American API manufacturing serves regulated markets with well-documented quality and compliance controls.\n"
        "Buyers typically assess GMP status, inspection histories, and DMF or CEP availability where applicable.\n"
        "Lead times and shipping routes may differ between the US and Canada but are generally characterized by stable and predictable transit."
    ),
    "SOUTH_AMERICA": (
        "South America hosts a mix of domestic-focused and export-oriented API manufacturing sites across several countries.\n"
        "Procurement workflows emphasize verification of documentation readiness, regulatory alignment, and supply continuity.\n"
        "Freight planning and customs coordination are usually addressed early to align delivery schedules with local production cycles."
    ),
}

ORIGIN_COUNTRY_ADJECTIVES = {
    "IN": "Indian",
    "CN": "Chinese",
    "US": "US-based",
    "JP": "Japanese",
    "KR": "South Korean",
}

ORIGIN_REGION_ADJECTIVES = {
    "ASIA": "Asian",
    "EUROPE": "European",
    "NORTH_AMERICA": "North American",
    "SOUTH_AMERICA": "South American",
}

ORIGIN_FILTER_KEYS = tuple(key for key in FILTER_LABELS if key.startswith("origin_"))

ORIGIN_FAQ_TEMPLATES: List[FAQTemplate] = [
    FAQTemplate(
        id="origin_meaning",
        mode="llm",
        question="What does it mean to source {api_name} from {origin_phrase_mfg}?",
        group="origin",
        context_keys=["supply", "regulatory"],
        tags=["meaning", "sourcing"],
    ),
    FAQTemplate(
        id="origin_scope",
        mode="llm",
        question="What does \"{origin_phrase_short}\" imply about the supply chain for {api_name}?",
        group="origin",
        context_keys=["supply"],
        tags=["scope", "supply_chain"],
    ),
    FAQTemplate(
        id="origin_not_guarantee",
        mode="llm",
        question="What should buyers not assume when choosing {api_name} suppliers with manufacturing in {origin_geo}?",
        group="origin",
        context_keys=["regulatory"],
        tags=["limitations", "qualification"],
    ),
    FAQTemplate(
        id="origin_qualification",
        mode="llm",
        question="When sourcing {api_name} from {origin_geo}, what changes in supplier qualification compared with other regions?",
        group="origin",
        context_keys=["regulatory", "supply"],
        tags=["qualification", "comparison"],
    ),
    FAQTemplate(
        id="origin_documents",
        mode="llm",
        question="Which documents are most important to request from {origin_phrase_mfg} when qualifying {api_name}?",
        group="origin",
        context_keys=["regulatory"],
        tags=["documentation", "buyer_actions"],
    ),
    FAQTemplate(
        id="origin_documentation_check",
        mode="llm",
        question=(
            "What should buyers verify about regulatory documentation and inspection history when sourcing {api_name} "
            "from {origin_geo} manufacturers?"
        ),
        group="origin",
        context_keys=["regulatory"],
        tags=["documentation", "inspection"],
    ),
    FAQTemplate(
        id="origin_logistics",
        mode="llm",
        question="What logistics factors commonly affect lead times when sourcing {api_name} from {origin_geo} manufacturers?",
        group="origin",
        context_keys=["supply"],
        tags=["logistics", "lead_time"],
    ),
    FAQTemplate(
        id="origin_risks",
        mode="llm",
        question="What are common risks buyers plan for when sourcing {api_name} from manufacturers in {origin_geo}?",
        group="origin",
        context_keys=["supply", "regulatory"],
        tags=["risks", "planning"],
    ),
    FAQTemplate(
        id="origin_tradeoffs",
        mode="llm",
        question=(
            "What trade-offs do buyers typically evaluate when comparing {api_name} suppliers in {origin_geo} "
            "versus other origins?"
        ),
        group="origin",
        context_keys=["supply"],
        tags=["tradeoffs", "comparison"],
    ),
    FAQTemplate(
        id="origin_rfq",
        mode="llm",
        question=(
            "What should an RFQ include to compare {api_name} manufacturers in {origin_geo} on quality, documentation, "
            "and lead time?"
        ),
        group="origin",
        context_keys=["supply", "regulatory"],
        tags=["rfq", "procurement"],
    ),
]

_FAQ_DEVELOPER_MESSAGE = (
    "You are an expert pharmaceutical procurement writer creating origin-focused FAQs. "
    "Be factual, concise, and avoid marketing language."
)

_REPAIR_DEVELOPER_MESSAGE = (
    "You repair invalid JSON into valid JSON without changing meaning."
)

_JSON_ONLY_SUFFIX = "Return ONLY JSON. No markdown. No code fences. No commentary."


class RequestLimiter:
    def __init__(self, max_concurrent: int) -> None:
        self._semaphore = threading.BoundedSemaphore(max(1, max_concurrent))

    def __enter__(self) -> "RequestLimiter":
        self._semaphore.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._semaphore.release()


class CacheStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, object]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        if self.path.suffix == ".jsonl":
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = entry.get("key")
                if isinstance(key, str):
                    self._data[key] = entry
        else:
            try:
                content = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return
            if isinstance(content, dict):
                for key, entry in content.items():
                    if isinstance(key, str) and isinstance(entry, dict):
                        self._data[key] = entry

    def get(self, key: str) -> Optional[List[Dict[str, object]]]:
        entry = self._data.get(key)
        if not entry:
            return None
        faqs = entry.get("faqs")
        if isinstance(faqs, list):
            return faqs
        return None

    def set(self, key: str, entry: Dict[str, object]) -> None:
        with self._lock:
            self._data[key] = entry
            if self.path.suffix == ".jsonl":
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            else:
                self._write_atomic_json(self.path, self._data)

    @staticmethod
    def _write_atomic_json(path: Path, data: Mapping[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)


class DeadLetterWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        *,
        api_id: str,
        api_name: str,
        origin_key: str,
        exception_name: str,
        reason: str,
        raw_output: str,
    ) -> None:
        entry = {
            "api_id": api_id,
            "api_name": api_name,
            "origin_key": origin_key,
            "exception": exception_name,
            "reason": reason,
            "raw_output_excerpt": _truncate_text(raw_output, 500),
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


@dataclass
class ValidationStats:
    missing_keys: int = 0
    empty_answers: int = 0
    question_mismatches: int = 0
    unanswered_questions: int = 0

    @property
    def total_failures(self) -> int:
        return (
            self.missing_keys
            + self.empty_answers
            + self.question_mismatches
            + self.unanswered_questions
        )


@dataclass
class ParseDiagnostics:
    raw_length: int
    json_extracted: bool
    parsed_items: int
    repair_used: bool
    validation_failures: int


@dataclass
class GenerationOutcome:
    api_id: str
    api_name: str
    origin_key: str
    faqs: List[Dict[str, object]]
    diagnostics: Optional[ParseDiagnostics]
    error_type: Optional[str] = None
    error_reason: Optional[str] = None


@dataclass
class GenerationStats:
    total_candidates: int = 0
    skipped_missing_origin: int = 0
    failed_timeout: int = 0
    failed_parse_validation: int = 0
    succeeded: int = 0


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


def _page_variants(page: Mapping[str, object]) -> Tuple[Mapping[str, object], ...]:
    normalized = _normalize_page(page)
    if normalized is page:
        return (page,)
    return (page, normalized)


def _detect_origin_key(page: Mapping[str, object], override: Optional[str] = None) -> Optional[str]:
    if override:
        return override

    origin_keys = set(ORIGIN_FILTER_KEYS)
    for candidate in _page_variants(page):
        filter_section = candidate.get("filter_section")
        if isinstance(filter_section, Mapping):
            for key in filter_section:
                if key in origin_keys:
                    return str(key)

        hero = candidate.get("hero")
        if isinstance(hero, Mapping):
            filter_intent = hero.get("filter_intent")
            if isinstance(filter_intent, Mapping):
                for nested_key in filter_intent:
                    if nested_key in origin_keys:
                        return str(nested_key)
                title = filter_intent.get("title")
                if isinstance(title, str):
                    normalized_title = title.lower()
                    for key, label in FILTER_LABELS.items():
                        if key in origin_keys and label.lower() in normalized_title:
                            return key

        filter_key = candidate.get("filter_key")
        if isinstance(filter_key, str) and filter_key in origin_keys:
            return filter_key

    return None


def _format_context(context_slices: Mapping[str, str], context_keys: Sequence[str]) -> str:
    ordered_keys = list(context_keys) if context_keys else ["regulatory", "supply"]
    lines = []
    for key in ordered_keys:
        value = context_slices.get(key, "")
        if value:
            lines.append(f"- {key.title()}: {value}")
    return "\n".join(lines)


def _guardrails_for_origin() -> List[str]:
    return [
        "Avoid clinical indications, side effects, or dosing guidance.",
        "Focus on sourcing, qualification, documentation, and compliance scope.",
        "Do not use the word 'filter'.",
    ]


def _normalize_text(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.strip().splitlines()).strip()


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "…"


def _log_diagnostics(
    *,
    api_id: str,
    api_name: str,
    questions_count: int,
    diagnostics: ParseDiagnostics,
) -> None:
    logger.info(
        "FAQ diagnostics api_id=%s api_name=%s questions=%d raw_len=%d json_extracted=%s parsed_items=%d validation_failures=%d",
        api_id,
        api_name,
        questions_count,
        diagnostics.raw_length,
        diagnostics.json_extracted,
        diagnostics.parsed_items,
        diagnostics.validation_failures,
    )


def _origin_adjective(origin_type: str, code: str, origin_geo: str) -> str:
    if origin_type == "country":
        return ORIGIN_COUNTRY_ADJECTIVES.get(code, origin_geo)
    return ORIGIN_REGION_ADJECTIVES.get(code, origin_geo)


def _origin_meta_from_key(origin_key: str) -> Optional[Dict[str, str]]:
    if origin_key.startswith("origin_country:"):
        _, _, code = origin_key.partition(":")
        origin_geo = ORIGIN_COUNTRY_LABELS.get(code)
        origin_type = "country"
        origin_background = ORIGIN_COUNTRY_BACKGROUND.get(code, "")
    elif origin_key.startswith("origin_region:"):
        _, _, code = origin_key.partition(":")
        origin_geo = ORIGIN_REGION_LABELS.get(code)
        origin_type = "region"
        origin_background = ORIGIN_REGION_BACKGROUND.get(code, "")
    else:
        return None

    if not origin_geo:
        return None

    adjective = _origin_adjective(origin_type, code, origin_geo)
    origin_phrase_short = f"manufactured in {origin_geo}"
    origin_phrase_mfg = f"{adjective} API manufacturers"
    origin_phrase_suppliers = f"suppliers with manufacturing in {origin_geo}"
    origin_phrase_page = f"API manufacturers in {origin_geo}"

    return {
        "origin_key": origin_key,
        "origin_type": origin_type,
        "origin_code": code,
        "origin_geo": origin_geo,
        "origin_phrase_short": origin_phrase_short,
        "origin_phrase_mfg": origin_phrase_mfg,
        "origin_phrase_suppliers": origin_phrase_suppliers,
        "origin_phrase_page": origin_phrase_page,
        "origin_label": FILTER_LABELS.get(origin_key, ""),
        "origin_explainer": FILTER_EXPLAINERS.get(origin_key, ""),
        "origin_background": origin_background,
    }


def _build_bulk_prompt(
    *,
    context: Mapping[str, str],
    context_slices: Mapping[str, str],
    origin_meta: Mapping[str, str],
    questions: Sequence[str],
    max_faqs: int,
    context_keys: Sequence[str],
) -> str:
    context_block = _format_context(context_slices, context_keys)
    guardrails = "\n".join(f"- {item}" for item in _guardrails_for_origin())
    questions_block = "\n".join(f"{idx + 1}. {question}" for idx, question in enumerate(questions))
    prompt = (
        "Generate origin-focused FAQ answers as strict JSON.\n\n"
        "Return a JSON array of objects. Each object must have:\n"
        '- "question": the exact question text provided below\n'
        '- "answer": a 2-4 sentence answer\n\n'
        f"Return at most {max_faqs} FAQ items. Do not add extra keys or commentary.\n\n"
        f"{_JSON_ONLY_SUFFIX}\n\n"
        "If a top-level object is required, wrap the array in {\"faqs\": [...]}.\n\n"
        "Origin context:\n"
        f"- API name: {context.get('drug_name')}\n"
        f"- CAS: {context.get('cas')}\n"
        f"- Origin key: {origin_meta.get('origin_key')}\n"
        f"- Origin label: {origin_meta.get('origin_label')}\n"
        f"- Origin explainer: {origin_meta.get('origin_explainer')}\n"
        f"- Origin background: {origin_meta.get('origin_background')}\n"
        f"Additional context:\n{context_block or '- (none)'}\n\n"
        "Constraints:\n"
        "- Avoid marketing language, speculation, or promises.\n"
        "- Do not restate long intro copy.\n"
        f"{guardrails}\n"
        "- If context is insufficient, stay high-level and factual without inventing details.\n\n"
        "Questions:\n"
        f"{questions_block}"
    )
    return _normalize_text(prompt)


def _is_transient_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    if status_code in {429, 500, 502, 503, 504}:
        return True
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    message = str(exc).lower()
    transient_markers = [
        "timed out",
        "timeout",
        "connection reset",
        "connection aborted",
        "temporarily unavailable",
        "rate limit",
        "too many requests",
        "service unavailable",
        "bad gateway",
    ]
    return any(marker in message for marker in transient_markers)


def _call_with_retries(
    func,
    *,
    max_retries: int,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
) -> str:
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - network errors
            if attempt >= max_retries or not _is_transient_error(exc):
                raise
            delay = min(max_delay, base_delay * (2**attempt)) + random.random()
            logger.warning("Retrying OpenAI call after error: %s", exc)
            time.sleep(delay)
    raise RuntimeError("Failed to complete OpenAI request")


def _build_repair_prompt(
    *,
    raw_response: str,
    questions: Sequence[str],
    max_faqs: int,
) -> str:
    questions_block = "\n".join(f"{idx + 1}. {question}" for idx, question in enumerate(questions))
    prompt = (
        "Repair the following text into valid JSON.\n\n"
        "Return a JSON array of objects with exactly two keys: question and answer.\n"
        "Use the exact question text provided; keep answers 2-4 sentences.\n"
        f"Return at most {max_faqs} items.\n\n"
        f"{_JSON_ONLY_SUFFIX}\n\n"
        "If a top-level object is required, wrap the array in {\"faqs\": [...]}.\n\n"
        "Questions:\n"
        f"{questions_block}\n\n"
        "Invalid response:\n"
        f"{raw_response}"
    )
    return _normalize_text(prompt)


def _clean_response_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.replace("```", "").strip()
    return cleaned


def _extract_json_payload(text: str) -> tuple[Optional[object], Optional[str]]:
    cleaned = _clean_response_text(text)
    decoder = json.JSONDecoder()
    last_error: Optional[str] = None
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            payload, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            last_error = "JSON decode failed"
            continue
        return payload, None
    if cleaned:
        try:
            return json.loads(cleaned), None
        except json.JSONDecodeError as exc:
            last_error = f"{exc.__class__.__name__}: {exc.msg}"
    return None, last_error


def _parse_faq_payload(payload: object, max_faqs: int) -> Optional[List[Dict[str, str]]]:
    if isinstance(payload, dict):
        if "faqs" in payload:
            payload = payload["faqs"]
        elif "items" in payload:
            payload = payload["items"]
    if not isinstance(payload, list):
        return None
    parsed: List[Dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        answer = item.get("answer")
        if isinstance(question, str) and isinstance(answer, str):
            parsed.append({"question": question.strip(), "answer": answer.strip()})
        if len(parsed) >= max_faqs:
            break
    return parsed or None


def _parse_faqs_with_repair(
    raw_response: str,
    *,
    max_faqs: int,
    repair_func: Optional[Callable[[], Optional[str]]] = None,
) -> tuple[Optional[List[Dict[str, str]]], bool, Optional[str]]:
    payload, error_reason = _extract_json_payload(raw_response)
    parsed = _parse_faq_payload(payload, max_faqs) if payload else None
    if parsed is not None or not repair_func:
        return parsed, False, error_reason
    repaired = repair_func()
    payload, error_reason = _extract_json_payload(repaired or "")
    parsed = _parse_faq_payload(payload, max_faqs) if payload else None
    return parsed, True, error_reason


def _sanitize_origin_key(origin_key: str) -> str:
    return origin_key.replace(":", "_")


def _validate_faq_items(
    question_items: Sequence[Tuple[FAQTemplate, str]],
    parsed: Sequence[Dict[str, str]],
    *,
    origin_meta: Mapping[str, str],
) -> tuple[List[Dict[str, object]], ValidationStats]:
    stats = ValidationStats()
    normalized_expected = [question.strip().lower() for _, question in question_items]
    expected_lookup = {question: idx for idx, question in enumerate(normalized_expected)}
    answers_by_question: Dict[str, str] = {}
    for item in parsed:
        question = item.get("question")
        answer = item.get("answer")
        if not isinstance(question, str) or not isinstance(answer, str):
            stats.missing_keys += 1
            continue
        question = question.strip()
        answer = answer.strip()
        if not answer:
            stats.empty_answers += 1
            continue
        normalized_question = question.lower()
        if normalized_question not in expected_lookup:
            stats.question_mismatches += 1
        answers_by_question[normalized_question] = answer

    faqs: List[Dict[str, object]] = []
    for index, (template, question_text) in enumerate(question_items):
        normalized_question = normalized_expected[index]
        answer = answers_by_question.get(normalized_question)
        if not answer and index < len(parsed):
            fallback_answer = parsed[index].get("answer")
            if isinstance(fallback_answer, str) and fallback_answer.strip():
                answer = fallback_answer.strip()
        if not answer:
            stats.unanswered_questions += 1
            continue
        origin_key = origin_meta.get("origin_key", "unknown")
        output_id = f"{template.id}__{_sanitize_origin_key(origin_key)}"
        tags = list(template.tags)
        origin_label = origin_meta.get("origin_label")
        if origin_label:
            tags.append(origin_label)
        faqs.append(
            {
                "id": output_id,
                "template_id": template.id,
                "group": template.group,
                "question": question_text,
                "answer": answer.strip(),
                "mode": template.mode,
                "tags": tags,
                "origin_key": origin_key,
                "origin_label": origin_label,
                "origin_type": origin_meta.get("origin_type"),
                "origin_code": origin_meta.get("origin_code"),
            }
        )
    return faqs, stats


def _is_response_format_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "response_format" in message or ("json" in message and "schema" in message)


def _generate_llm_bulk(
    *,
    client: Optional[OpenAIClient],
    model: Optional[str],
    prompt: str,
    max_tokens: Optional[int] = None,
    max_retries: int = 5,
    limiter: Optional[RequestLimiter] = None,
    developer_message: str = _FAQ_DEVELOPER_MESSAGE,
    response_format: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Optional[str]:
    if client is None:
        logger.warning("No OpenAI client available; skipping origin FAQ generation")
        return None

    def _call(request_response_format: Optional[Dict[str, Any]]) -> str:
        if limiter:
            with limiter:
                return client._chat_completion(
                    model=model or client.config.summary_model,
                    max_tokens=max_tokens or client.config.max_completion_tokens,
                    developer_message=developer_message,
                    user_message=prompt,
                    response_format=request_response_format,
                    idempotency_key=idempotency_key,
                )
        return client._chat_completion(
            model=model or client.config.summary_model,
            max_tokens=max_tokens or client.config.max_completion_tokens,
            developer_message=developer_message,
            user_message=prompt,
            response_format=request_response_format,
            idempotency_key=idempotency_key,
        )

    try:
        return _call_with_retries(lambda: _call(response_format), max_retries=max_retries)
    except Exception as exc:
        if response_format and _is_response_format_error(exc):
            logger.warning("JSON response_format unsupported; retrying without JSON mode")
            return _call_with_retries(lambda: _call(None), max_retries=max_retries)
        raise


def generate_origin_faqs_for_page(
    api_id: str,
    page: Mapping[str, object],
    *,
    templates: Sequence[FAQTemplate],
    client: Optional[OpenAIClient],
    model: Optional[str],
    max_faqs: Optional[int],
    origin_key: Optional[str],
    repair_model: Optional[str],
    max_retries: int,
    limiter: Optional[RequestLimiter],
    cache: Optional[CacheStore],
    failed_writer: Optional[DeadLetterWriter],
    detected_origin_key: Optional[str] = None,
) -> GenerationOutcome:
    context, context_slices = _extract_context(api_id, page)
    detected_origin_key = detected_origin_key or _detect_origin_key(page, override=origin_key)
    api_name = context.get("drug_name") or api_id
    if not detected_origin_key or detected_origin_key not in ORIGIN_FILTER_KEYS:
        logger.info("Skipping %s due to missing origin key", api_id)
        return GenerationOutcome(
            api_id=api_id,
            api_name=api_name,
            origin_key=detected_origin_key or "unknown",
            faqs=[],
            diagnostics=None,
            error_type="missing_origin",
            error_reason="Missing origin key",
        )

    origin_meta = _origin_meta_from_key(detected_origin_key)
    if not origin_meta or not origin_meta.get("origin_label") or not origin_meta.get(
        "origin_explainer"
    ):
        logger.warning("Missing origin metadata for %s", detected_origin_key)
        return GenerationOutcome(
            api_id=api_id,
            api_name=api_name,
            origin_key=detected_origin_key,
            faqs=[],
            diagnostics=None,
            error_type="missing_origin_metadata",
            error_reason="Missing origin metadata",
        )

    context = {
        **context,
        "api_name": context.get("drug_name") or api_id,
        **origin_meta,
    }

    question_items: List[Tuple[FAQTemplate, str]] = []
    for template in templates:
        if max_faqs is not None and len(question_items) >= max_faqs:
            break
        if not _has_required_fields(template, context):
            continue
        try:
            question_text = template.question.format(**context)
        except KeyError as exc:
            logger.debug("Missing placeholder %s for question %s", exc, template.id)
            continue
        question_items.append((template, question_text))

    if not question_items:
        return GenerationOutcome(
            api_id=api_id,
            api_name=api_name,
            origin_key=detected_origin_key,
            faqs=[],
            diagnostics=None,
            error_type="missing_questions",
            error_reason="No FAQ templates available for context",
        )

    context_keys: List[str] = []
    for template, _ in question_items:
        for key in template.context_keys:
            if key not in context_keys:
                context_keys.append(key)
    if not context_keys:
        context_keys = ["regulatory", "supply"]

    questions = [question for _, question in question_items]
    prompt = _build_bulk_prompt(
        context=context,
        context_slices=context_slices,
        origin_meta=origin_meta,
        questions=questions,
        max_faqs=max_faqs or len(questions),
        context_keys=context_keys,
    )

    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    cache_key = "|".join(
        [
            model or (client.config.summary_model if client else ""),
            detected_origin_key,
            api_id,
            str(max_faqs or len(questions)),
            prompt_hash,
        ]
    )

    if cache:
        cached = cache.get(cache_key)
        if cached is not None:
            diagnostics = ParseDiagnostics(
                raw_length=0,
                json_extracted=True,
                parsed_items=len(cached),
                repair_used=False,
                validation_failures=0,
            )
            return GenerationOutcome(
                api_id=api_id,
                api_name=api_name,
                origin_key=detected_origin_key,
                faqs=cached,
                diagnostics=diagnostics,
            )

    idempotency_key = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    raw_response = _generate_llm_bulk(
        client=client,
        model=model,
        prompt=prompt,
        max_tokens=client.config.max_completion_tokens if client else None,
        max_retries=max_retries,
        limiter=limiter,
        response_format={"type": "json_object"},
        idempotency_key=idempotency_key,
    )
    if not raw_response:
        diagnostics = ParseDiagnostics(
            raw_length=0,
            json_extracted=False,
            parsed_items=0,
            repair_used=False,
            validation_failures=0,
        )
        _log_diagnostics(
            api_id=api_id,
            api_name=api_name,
            questions_count=len(questions),
            diagnostics=diagnostics,
        )
        return GenerationOutcome(
            api_id=api_id,
            api_name=api_name,
            origin_key=detected_origin_key,
            faqs=[],
            diagnostics=diagnostics,
            error_type="empty_response",
            error_reason="Empty response from model",
        )

    repair_prompt = _build_repair_prompt(
        raw_response=raw_response,
        questions=questions,
        max_faqs=max_faqs or len(questions),
    )
    try:
        parsed, repair_used, parse_error = _parse_faqs_with_repair(
            raw_response,
            max_faqs=max_faqs or len(questions),
            repair_func=lambda: _generate_llm_bulk(
                client=client,
                model=repair_model or model,
                prompt=repair_prompt,
                max_tokens=client.config.max_completion_tokens if client else None,
                max_retries=max_retries,
                limiter=limiter,
                developer_message=_REPAIR_DEVELOPER_MESSAGE,
                response_format={"type": "json_object"},
                idempotency_key=f"{idempotency_key}-repair",
            ),
        )
    except Exception as exc:
        error_message = f"Repair call failed: {exc}"
        logger.warning("Repair call failed for %s: %s", api_id, exc)
        if failed_writer:
            failed_writer.write(
                api_id=api_id,
                api_name=api_name,
                origin_key=detected_origin_key,
                exception_name=exc.__class__.__name__,
                reason=error_message,
                raw_output=raw_response,
            )
        diagnostics = ParseDiagnostics(
            raw_length=len(raw_response),
            json_extracted=False,
            parsed_items=0,
            repair_used=True,
            validation_failures=0,
        )
        _log_diagnostics(
            api_id=api_id,
            api_name=api_name,
            questions_count=len(questions),
            diagnostics=diagnostics,
        )
        return GenerationOutcome(
            api_id=api_id,
            api_name=api_name,
            origin_key=detected_origin_key,
            faqs=[],
            diagnostics=diagnostics,
            error_type="parse_validation",
            error_reason=error_message,
        )

    json_extracted = parsed is not None
    parsed_count = len(parsed) if parsed else 0
    if parsed is None:
        error_message = parse_error or "Invalid JSON after repair"
        logger.warning("Invalid JSON for %s after repair", api_id)
        if failed_writer:
            failed_writer.write(
                api_id=api_id,
                api_name=api_name,
                origin_key=detected_origin_key,
                exception_name="JSONDecodeError",
                reason=error_message,
                raw_output=raw_response,
            )
        diagnostics = ParseDiagnostics(
            raw_length=len(raw_response),
            json_extracted=False,
            parsed_items=0,
            repair_used=repair_used,
            validation_failures=0,
        )
        _log_diagnostics(
            api_id=api_id,
            api_name=api_name,
            questions_count=len(questions),
            diagnostics=diagnostics,
        )
        return GenerationOutcome(
            api_id=api_id,
            api_name=api_name,
            origin_key=detected_origin_key,
            faqs=[],
            diagnostics=diagnostics,
            error_type="parse_validation",
            error_reason=error_message,
        )

    faqs, validation_stats = _validate_faq_items(
        question_items,
        parsed,
        origin_meta=origin_meta,
    )

    diagnostics = ParseDiagnostics(
        raw_length=len(raw_response),
        json_extracted=json_extracted,
        parsed_items=parsed_count,
        repair_used=repair_used,
        validation_failures=validation_stats.total_failures,
    )

    _log_diagnostics(
        api_id=api_id,
        api_name=api_name,
        questions_count=len(questions),
        diagnostics=diagnostics,
    )

    if not faqs:
        logger.warning("No valid FAQs parsed for %s after JSON validation", api_id)
        if failed_writer:
            failed_writer.write(
                api_id=api_id,
                api_name=api_name,
                origin_key=detected_origin_key,
                exception_name="ValidationError",
                reason="No valid FAQs after parsing",
                raw_output=raw_response,
            )
        return GenerationOutcome(
            api_id=api_id,
            api_name=api_name,
            origin_key=detected_origin_key,
            faqs=[],
            diagnostics=diagnostics,
            error_type="parse_validation",
            error_reason="No valid FAQs after parsing",
        )

    if cache:
        cache_entry = {
            "key": cache_key,
            "api_id": api_id,
            "origin_key": detected_origin_key,
            "model": model or (client.config.summary_model if client else ""),
            "max_faqs": max_faqs or len(questions),
            "prompt_hash": prompt_hash,
            "faqs": faqs,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        cache.set(cache_key, cache_entry)

    return GenerationOutcome(
        api_id=api_id,
        api_name=api_name,
        origin_key=detected_origin_key,
        faqs=faqs,
        diagnostics=diagnostics,
    )


def _generate_for_single_page(
    api_id: str,
    page: Mapping[str, object],
    *,
    templates: Sequence[FAQTemplate],
    client: Optional[OpenAIClient],
    model: Optional[str],
    max_faqs: Optional[int],
    origin_key: Optional[str],
    repair_model: Optional[str],
    max_retries: int,
    limiter: Optional[RequestLimiter],
    cache: Optional[CacheStore],
    failed_writer: Optional[DeadLetterWriter],
    detected_origin_key: Optional[str],
) -> GenerationOutcome:
    if not isinstance(page, Mapping):
        logger.warning("Skipping %s because page entry is not a mapping", api_id)
        return GenerationOutcome(
            api_id=api_id,
            api_name=api_id,
            origin_key=detected_origin_key or "unknown",
            faqs=[],
            diagnostics=None,
            error_type="invalid_page",
            error_reason="Page entry is not a mapping",
        )
    try:
        return generate_origin_faqs_for_page(
            api_id,
            page,
            templates=templates,
            client=client,
            model=model,
            max_faqs=max_faqs,
            origin_key=origin_key,
            repair_model=repair_model,
            max_retries=max_retries,
            limiter=limiter,
            cache=cache,
            failed_writer=failed_writer,
            detected_origin_key=detected_origin_key,
        )
    except Exception as exc:  # pragma: no cover - network errors
        context, _ = _extract_context(api_id, page)
        api_name = context.get("drug_name") or api_id
        error_type = "timeout" if _is_transient_error(exc) else "exception"
        if failed_writer:
            failed_writer.write(
                api_id=api_id,
                api_name=api_name,
                origin_key=detected_origin_key or "unknown",
                exception_name=exc.__class__.__name__,
                reason=str(exc),
                raw_output="",
            )
        logger.exception("Failed to generate origin FAQs for %s", api_id)
        return GenerationOutcome(
            api_id=api_id,
            api_name=api_name,
            origin_key=detected_origin_key or "unknown",
            faqs=[],
            diagnostics=None,
            error_type=error_type,
            error_reason=str(exc),
        )


def generate_origin_faqs(
    pages: Mapping[str, object],
    *,
    templates: Sequence[FAQTemplate] = ORIGIN_FAQ_TEMPLATES,
    client: Optional[OpenAIClient] = None,
    model: Optional[str] = None,
    max_faqs: Optional[int] = None,
    max_workers: int = 8,
    max_concurrent_requests: int = 8,
    max_in_flight: int = 300,
    origin_key: Optional[str] = None,
    repair_model: Optional[str] = None,
    max_retries: int = 5,
    cache: Optional[CacheStore] = None,
    failed_writer: Optional[DeadLetterWriter] = None,
) -> tuple[Dict[str, List[Dict[str, object]]], GenerationStats]:
    faq_output: Dict[str, List[Dict[str, object]]] = {}
    stats = GenerationStats(total_candidates=len(pages))
    limiter = RequestLimiter(max_concurrent_requests)
    eligible: List[Tuple[str, Mapping[str, object], str]] = []
    for api_id, page in pages.items():
        if not isinstance(page, Mapping):
            logger.warning("Skipping %s because page entry is not a mapping", api_id)
            continue
        detected = _detect_origin_key(page, override=origin_key)
        if not detected or detected not in ORIGIN_FILTER_KEYS:
            logger.info("Skipping %s due to missing origin key", api_id)
            stats.skipped_missing_origin += 1
            continue
        eligible.append((api_id, page, detected))

    work_queue: deque[Tuple[str, Mapping[str, object], str]] = deque(eligible)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        in_flight: Dict[concurrent.futures.Future, str] = {}
        while work_queue or in_flight:
            while work_queue and len(in_flight) < max_in_flight:
                api_id, page, detected_origin_key = work_queue.popleft()
                future = executor.submit(
                    _generate_for_single_page,
                    api_id,
                    page,
                    templates=templates,
                    client=client,
                    model=model,
                    max_faqs=max_faqs,
                    origin_key=origin_key,
                    repair_model=repair_model,
                    max_retries=max_retries,
                    limiter=limiter,
                    cache=cache,
                    failed_writer=failed_writer,
                    detected_origin_key=detected_origin_key,
                )
                in_flight[future] = api_id

            if not in_flight:
                continue
            done, _ = concurrent.futures.wait(
                in_flight.keys(),
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                api_id = in_flight.pop(future)
                outcome = future.result()
                if outcome.faqs:
                    faq_output[outcome.api_id] = outcome.faqs
                    stats.succeeded += 1
                elif outcome.error_type == "timeout":
                    stats.failed_timeout += 1
                elif outcome.error_type and outcome.error_type not in {
                    "missing_origin",
                    "missing_origin_metadata",
                    "missing_questions",
                }:
                    stats.failed_parse_validation += 1
    return faq_output, stats


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate origin-focused FAQs from filtered API page models"
    )
    parser.add_argument(
        "--input",
        default="outputs/filtered_api_pages.json",
        help="Path to filtered API pages JSON",
    )
    parser.add_argument(
        "--output",
        default="outputs/origin_faqs.json",
        help="Output path for generated origin FAQs",
    )
    parser.add_argument("--max-faqs", type=int, help="Maximum FAQs per API")
    parser.add_argument("--model", help="Override model for LLM FAQs (defaults to summary model)")
    parser.add_argument(
        "--repair-model",
        help="Model to use for one-time JSON repair (defaults to --model)",
    )
    parser.add_argument(
        "--cache-path",
        default="outputs/origin_faq_cache.jsonl",
        help="Path to JSONL/JSON cache for generated FAQs",
    )
    parser.add_argument(
        "--max-concurrent-requests",
        type=int,
        default=8,
        help="Maximum concurrent OpenAI requests across threads",
    )
    parser.add_argument(
        "--max-in-flight",
        type=int,
        default=300,
        help="Maximum in-flight futures to avoid memory spikes",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Maximum retries for transient OpenAI errors",
    )
    parser.add_argument(
        "--failed-path",
        default="outputs/origin_faq_failed.jsonl",
        help="Path to write failed API generations as JSONL",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=None,
        help="OpenAI client timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--connect-timeout-seconds",
        type=int,
        default=None,
        help="OpenAI client connect timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Thread pool size (defaults to OPENAI_MAX_WORKERS or 8)",
    )
    parser.add_argument(
        "--origin-key",
        choices=sorted(ORIGIN_FILTER_KEYS),
        help="Optional origin key override",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    pages = _load_json(args.input)

    from src.openai_client import OpenAIClient

    client: Optional[OpenAIClient]
    try:
        config = OpenAIConfig()
        if args.timeout_seconds is not None:
            config.timeout_seconds = args.timeout_seconds
            config.read_timeout_seconds = args.timeout_seconds
        if args.connect_timeout_seconds is not None:
            config.connect_timeout_seconds = args.connect_timeout_seconds
        if args.max_concurrent_requests:
            config.max_concurrent_requests = args.max_concurrent_requests
        client = OpenAIClient(config)
    except EnvironmentError as exc:  # pragma: no cover - env dependent
        logger.warning("OpenAI credentials missing; origin FAQs will be skipped: %s", exc)
        client = None

    cache = CacheStore(Path(args.cache_path)) if args.cache_path else None
    failed_writer = DeadLetterWriter(Path(args.failed_path)) if args.failed_path else None

    max_workers = args.max_workers or int(os.getenv("OPENAI_MAX_WORKERS", "8"))
    faqs, stats = generate_origin_faqs(
        pages,
        client=client,
        model=args.model,
        max_faqs=args.max_faqs,
        max_workers=max_workers,
        max_concurrent_requests=args.max_concurrent_requests,
        max_in_flight=args.max_in_flight,
        origin_key=args.origin_key,
        repair_model=args.repair_model or args.model,
        max_retries=args.max_retries,
        cache=cache,
        failed_writer=failed_writer,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(faqs, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(output_path)
    logger.info("Wrote origin FAQs for %d APIs to %s", len(faqs), output_path)
    if stats.total_candidates and len(faqs) == 0:
        summary = (
            "No origin FAQs generated.\n"
            f"total_candidates={stats.total_candidates} "
            f"skipped_missing_origin={stats.skipped_missing_origin} "
            f"failed_timeout={stats.failed_timeout} "
            f"failed_parse_validation={stats.failed_parse_validation} "
            f"succeeded={stats.succeeded}"
        )
        logger.error(summary)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

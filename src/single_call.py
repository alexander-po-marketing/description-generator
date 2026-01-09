"""Helpers for single-call generation JSON parsing and repair."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9]*", "", cleaned).strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[: -3].strip()
    return cleaned


def _extract_json(text: str) -> str:
    cleaned = _strip_code_fences(text)
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return cleaned
    return cleaned[start : end + 1]


def _fix_trailing_commas(text: str) -> str:
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    return cleaned


def parse_single_call_payload(text: str, include_faqs: bool) -> Dict[str, Any]:
    cleaned = _extract_json(text)
    cleaned = _fix_trailing_commas(cleaned)
    payload = json.loads(cleaned)
    return validate_single_call_payload(payload, include_faqs)


def validate_single_call_payload(payload: Any, include_faqs: bool) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Single-call payload must be a JSON object")

    def _get_str(key: str) -> str:
        value = payload.get(key)
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError(f"Field '{key}' must be a string")
        return value.strip()

    description = _get_str("description")
    summary = _get_str("summary")
    summary_sentence = _get_str("summary_sentence")

    result: Dict[str, Any] = {
        "description": description,
        "summary": summary,
        "summary_sentence": summary_sentence,
    }

    if include_faqs:
        faqs_value = payload.get("faqs")
        if faqs_value is None:
            faqs: List[Dict[str, str]] = []
        elif not isinstance(faqs_value, list):
            raise ValueError("Field 'faqs' must be a list when provided")
        else:
            faqs = []
            for item in faqs_value:
                if not isinstance(item, dict):
                    raise ValueError("FAQ entries must be objects")
                question = item.get("question", "")
                answer = item.get("answer", "")
                if not isinstance(question, str) or not isinstance(answer, str):
                    raise ValueError("FAQ question/answer must be strings")
                if question.strip() or answer.strip():
                    faqs.append({"question": question.strip(), "answer": answer.strip()})
        result["faqs"] = faqs

    return result


def build_repair_prompt(raw_text: str, error_message: Optional[str] = None) -> str:
    problem = error_message or "Invalid JSON"
    return (
        "You are a JSON validator. Fix the JSON so it is valid and follows the schema. "
        "Return only JSON, no markdown or explanations.\n\n"
        f"Issue: {problem}\n"
        "Schema: {\"description\": string, \"summary\": string, \"summary_sentence\": string, "
        "\"faqs\": [{\"question\": string, \"answer\": string}] }\n\n"
        "JSON to fix:\n"
        f"{raw_text}\n"
    )

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.cert_faq_generator import (  # noqa: E402
    _extract_json_payload,
    _parse_faq_payload,
    _parse_faqs_with_repair,
    _validate_faq_items,
)
from src.faq_generator import FAQTemplate  # noqa: E402


def _faq_template(question: str) -> FAQTemplate:
    return FAQTemplate(
        id="template",
        mode="llm",
        question=question,
        group="certification",
        context_keys=[],
        tags=[],
    )


def test_extract_json_payload_plain_array() -> None:
    raw = '[{"question": "Q1", "answer": "A1"}]'
    payload, error = _extract_json_payload(raw)
    assert error is None
    parsed = _parse_faq_payload(payload, 5)
    assert parsed == [{"question": "Q1", "answer": "A1"}]


def test_extract_json_payload_fenced_json() -> None:
    raw = "```json\n[{\"question\": \"Q1\", \"answer\": \"A1\"}]\n```"
    payload, error = _extract_json_payload(raw)
    assert error is None
    parsed = _parse_faq_payload(payload, 5)
    assert parsed == [{"question": "Q1", "answer": "A1"}]


def test_extract_json_payload_leading_prose() -> None:
    raw = "Here are the FAQs:\n[{\"question\": \"Q1\", \"answer\": \"A1\"}]\nThanks."
    payload, error = _extract_json_payload(raw)
    assert error is None
    parsed = _parse_faq_payload(payload, 5)
    assert parsed == [{"question": "Q1", "answer": "A1"}]


def test_extract_json_payload_wrapper_object() -> None:
    raw = json.dumps({"faqs": [{"question": "Q1", "answer": "A1"}]})
    payload, error = _extract_json_payload(raw)
    assert error is None
    parsed = _parse_faq_payload(payload, 5)
    assert parsed == [{"question": "Q1", "answer": "A1"}]


def test_parse_with_repair_stub() -> None:
    raw = "not valid json"

    def repair() -> str:
        return '[{"question": "Q1", "answer": "A1"}]'

    parsed, repair_used, _ = _parse_faqs_with_repair(raw, max_faqs=5, repair_func=repair)
    assert repair_used is True
    assert parsed == [{"question": "Q1", "answer": "A1"}]


def test_validate_faq_items_question_mismatch() -> None:
    template = _faq_template("What is GMP?")
    question_items = [(template, "What is GMP?")]
    parsed = [{"question": "What is GDP?", "answer": "Answer."}]
    faqs, stats = _validate_faq_items(
        question_items,
        parsed,
        filter_key="gmp",
        filter_label="GMP",
    )
    assert stats.question_mismatches == 1
    assert faqs[0]["question"] == "What is GMP?"


def test_validate_faq_items_missing_keys() -> None:
    template = _faq_template("What is GMP?")
    question_items = [(template, "What is GMP?")]
    parsed = [{"question": "What is GMP?"}]
    faqs, stats = _validate_faq_items(
        question_items,
        parsed,
        filter_key="gmp",
        filter_label="GMP",
    )
    assert stats.missing_keys == 1
    assert stats.unanswered_questions == 1
    assert faqs == []

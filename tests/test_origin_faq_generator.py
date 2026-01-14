import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.origin_faq_generator import (  # noqa: E402
    _detect_origin_key,
    _extract_json_payload,
    _parse_faq_payload,
)


def test_extract_json_payload_plain_array() -> None:
    raw = '[{"question": "Q1", "answer": "A1"}]'
    payload, error = _extract_json_payload(raw)
    assert error is None
    parsed = _parse_faq_payload(payload, 5)
    assert parsed == [{"question": "Q1", "answer": "A1"}]


def test_detect_origin_key_from_filter_section() -> None:
    page = {"filter_section": {"origin_country:IN": {"value": True}}}
    assert _detect_origin_key(page) == "origin_country:IN"


def test_detect_origin_key_from_hero_title() -> None:
    page = {"hero": {"filter_intent": {"title": "Verified API manufacturers in China"}}}
    assert _detect_origin_key(page) == "origin_country:CN"


def test_detect_origin_key_from_filter_key() -> None:
    page = {"filter_key": "origin_region:EUROPE"}
    assert _detect_origin_key(page) == "origin_region:EUROPE"

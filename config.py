"""Application configuration and constants."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set


def _parse_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_set(value: Optional[str]) -> Set[str]:
    return set(_parse_list(value))


@dataclass
class OpenAIConfig:
    model: str = os.getenv("OPENAI_MODEL", "gpt-5.1")
    summary_model: str = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")
    temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0.4"))
    max_tokens: int = int(os.getenv("OPENAI_MAX_TOKENS", "700"))
    summary_max_tokens: int = int(os.getenv("OPENAI_SUMMARY_MAX_TOKENS", "200"))
    max_retries: int = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
    timeout_seconds: int = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))


@dataclass
class PipelineConfig:
    xml_path: str
    database_json: str
    descriptions_json: str
    descriptions_xml: str
    description_prompts_log: str = "description_prompts.log"
    summary_prompts_log: str = "summary_prompts.log"
    valid_drug_ids: Set[str] = field(default_factory=set)
    max_drugs: Optional[int] = None
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    desired_fields: Set[str] = field(
        default_factory=lambda: {
            "name",
            "description",
            "cas-number",
            "unii",
            "average-mass",
            "monoisotopic-mass",
            "state",
            "indication",
            "pharmacodynamics",
            "mechanism-of-action",
            "toxicity",
            "metabolism",
            "absorption",
            "half-life",
            "protein-binding",
            "route-of-elimination",
            "volume-of-distribution",
            "clearance",
            "Molecular Formula",
            "SMILES",
            "logP",
            "Water Solubility",
            "Melting Point",
            "Molecular Weight",
            "classification",
            "categories",
            "groups",
            "packagers",
            "manufacturers",
            "external-identifiers",
            "external-links",
            "general-references",
            "international-brands",
            "products",
        }
    )

    @classmethod
    def from_args(
        cls,
        xml_path: str,
        database_json: str,
        descriptions_json: str,
        descriptions_xml: str,
        *,
        valid_drug_ids: Optional[Iterable[str]] = None,
        max_drugs: Optional[int] = None,
        log_level: Optional[str] = None,
    ) -> "PipelineConfig":
        return cls(
            xml_path=xml_path,
            database_json=database_json,
            descriptions_json=descriptions_json,
            descriptions_xml=descriptions_xml,
            valid_drug_ids=set(valid_drug_ids or []),
            max_drugs=max_drugs,
            log_level=log_level or os.getenv("LOG_LEVEL", "INFO"),
        )


def load_valid_ids_from_file(path: str) -> Set[str]:
    with open(path, "r", encoding="utf-8") as handle:
        return {line.strip() for line in handle if line.strip()}


def parse_valid_ids(value: Optional[str]) -> Set[str]:
    if not value:
        return set()
    if os.path.isfile(value):
        return load_valid_ids_from_file(value)
    return _parse_set(value)

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
    model: str = os.getenv("OPENAI_MODEL", "gpt-5.1-chat-latest")
    summary_model: str = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-5.1-chat-latest")
    single_call_model: str = os.getenv("OPENAI_SINGLE_CALL_MODEL", "") or model
    repair_model: str = os.getenv("OPENAI_REPAIR_MODEL", "gpt-5.1-mini")
    max_completion_tokens: int = int(os.getenv("OPENAI_MAX_COMPLETION_TOKENS", "1000"))
    summary_max_completion_tokens: int = int(
        os.getenv("OPENAI_SUMMARY_MAX_COMPLETION_TOKENS", "400")
    )
    max_retries: int = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
    timeout_seconds: int = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "120"))
    connect_timeout_seconds: int = int(os.getenv("OPENAI_CONNECT_TIMEOUT_SECONDS", "30"))
    read_timeout_seconds: int = int(os.getenv("OPENAI_READ_TIMEOUT_SECONDS", "120"))
    max_concurrent_requests: int = int(os.getenv("OPENAI_MAX_CONCURRENT_REQUESTS", "10"))
    max_requests_per_minute: Optional[int] = (
        int(os.getenv("OPENAI_MAX_REQUESTS_PER_MINUTE", ""))
        if os.getenv("OPENAI_MAX_REQUESTS_PER_MINUTE")
        else None
    )
    max_tokens_per_minute: Optional[int] = (
        int(os.getenv("OPENAI_MAX_TOKENS_PER_MINUTE", ""))
        if os.getenv("OPENAI_MAX_TOKENS_PER_MINUTE")
        else None
    )


@dataclass
class PipelineConfig:
    xml_path: str
    database_json: str
    preview_html: str = "outputs/api_pages_preview.html"
    page_models_json: str = "outputs/api_pages.json"
    import_json: str = "outputs/api_pages_import.json"
    progress_json: str = "outputs/progress.json"
    failed_drugs_jsonl: str = "outputs/failed_drugs.jsonl"
    template_definition: Optional[str] = None
    prompt_log: str = "logs/prompts.log"
    generation_cache_json: str = "outputs/generation_cache.json"
    valid_drug_ids: Set[str] = field(default_factory=set)
    max_drugs: Optional[int] = None
    max_workers: int = int(os.getenv("OPENAI_MAX_WORKERS", "8"))
    submit_chunk_size: int = int(os.getenv("OPENAI_SUBMIT_CHUNK_SIZE", "200"))
    checkpoint_every: int = int(os.getenv("OPENAI_CHECKPOINT_EVERY", "25"))
    single_call_generation: bool = False
    include_faqs: bool = False
    use_existing_database: bool = True
    resume_from: Optional[str] = None
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
            "food-interactions",
            "atc-codes",
            "dosages",
            "patents",
            "targets",
            "drug-interactions",
            "synthesis-reference",
            "products",
            "packagers",
            "manufacturers",
            "external-identifiers",
            "external-links",
            "general-references",
            "international-brands",
        }
    )

    @classmethod
    def from_args(
        cls,
        xml_path: str,
        database_json: str,
        page_models_json: Optional[str] = None,
        import_json: Optional[str] = None,
        preview_html: Optional[str] = None,
        progress_json: Optional[str] = None,
        failed_drugs_jsonl: Optional[str] = None,
        prompt_log: Optional[str] = None,
        generation_cache_json: Optional[str] = None,
        template_definition: Optional[str] = None,
        *,
        valid_drug_ids: Optional[Iterable[str]] = None,
        max_drugs: Optional[int] = None,
        max_workers: Optional[int] = None,
        submit_chunk_size: Optional[int] = None,
        checkpoint_every: Optional[int] = None,
        single_call_generation: bool = False,
        include_faqs: bool = False,
        use_existing_database: bool = True,
        resume_from: Optional[str] = None,
        log_level: Optional[str] = None,
    ) -> "PipelineConfig":
        return cls(
            xml_path=xml_path,
            database_json=database_json,
            page_models_json=page_models_json or "outputs/api_pages.json",
            import_json=import_json or "outputs/api_pages_import.json",
            preview_html=preview_html or "outputs/api_pages_preview.html",
            progress_json=progress_json or "outputs/progress.json",
            failed_drugs_jsonl=failed_drugs_jsonl or "outputs/failed_drugs.jsonl",
            prompt_log=prompt_log or "logs/prompts.log",
            generation_cache_json=generation_cache_json or "outputs/generation_cache.json",
            template_definition=template_definition,
            valid_drug_ids=set(valid_drug_ids or []),
            max_drugs=max_drugs,
            max_workers=max_workers or int(os.getenv("OPENAI_MAX_WORKERS", "8")),
            submit_chunk_size=submit_chunk_size or int(os.getenv("OPENAI_SUBMIT_CHUNK_SIZE", "200")),
            checkpoint_every=checkpoint_every or int(os.getenv("OPENAI_CHECKPOINT_EVERY", "25")),
            single_call_generation=single_call_generation,
            include_faqs=include_faqs,
            use_existing_database=use_existing_database,
            resume_from=resume_from,
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

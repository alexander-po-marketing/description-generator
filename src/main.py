"""DrugBank -> AI -> HTML pipeline with CLI."""

from __future__ import annotations

import argparse
import inspect
import json
import logging
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, Optional

from src.config import OpenAIConfig, PipelineConfig, parse_valid_ids
from src.drugbank_parser import parse_drugbank_xml
from src.exporters import export_clean_import, export_database, export_page_models, load_database
from src.generation_cache import (
    load_generation_cache,
    prompt_hash,
    read_cached_text,
    save_generation_cache,
    write_cached_text,
)
from src.generators import (
    build_description_prompt,
    build_single_call_prompt,
    build_summary_prompt,
    build_summary_sentence_prompt,
)
from src.job_store import ProgressState, append_jsonl, load_progress, save_progress
from src.models import DrugData, GeneratedContent
from src.openai_client import OpenAIClient
from src.path_utils import ensure_parent_dir, normalize_repo_path
from src.page_builder import build_page_model
from src.preview_renderer import save_html_preview
from src.single_call import build_repair_prompt, parse_single_call_payload, validate_single_call_payload
from src.template_engine import load_template_definition


logger = logging.getLogger(__name__)


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def sanitize_text(text: str) -> str:
    """Normalize model output to plain text without HTML or citation artifacts."""
    cleaned = text or ""
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\[.*?\]", "", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _self_check_summary_prompt_signature() -> None:
    signature = inspect.signature(build_summary_sentence_prompt)
    if len(signature.parameters) != 2 or "description" not in signature.parameters:
        raise RuntimeError("build_summary_sentence_prompt must accept (drug, description)")


def validate_drug(drug: DrugData) -> Iterable[str]:
    missing = []
    if not drug.name:
        missing.append("name")
    return missing


def generate_for_drug(
    drug: DrugData,
    client: OpenAIClient,
    ai_config: OpenAIConfig,
    *,
    single_call: bool,
    include_faqs: bool,
    cache: Dict[str, object],
    cache_lock: threading.Lock,
) -> GeneratedContent:
    if single_call:
        prompt = build_single_call_prompt(drug, include_faqs=include_faqs)
        prompt_hash_value = prompt_hash(ai_config.single_call_model, prompt)
        with cache_lock:
            cached_description = read_cached_text(cache, drug.drugbank_id, "description", prompt_hash_value)
            cached_summary = read_cached_text(cache, drug.drugbank_id, "summary", prompt_hash_value)
            cached_summary_sentence = read_cached_text(
                cache,
                drug.drugbank_id,
                "summary_sentence",
                prompt_hash_value,
            )
            cached_faqs = None
            if include_faqs:
                cached_faqs = read_cached_text(cache, drug.drugbank_id, "faqs", prompt_hash_value)
        if cached_description and cached_summary and cached_summary_sentence:
            faqs_payload = None
            if include_faqs and cached_faqs:
                try:
                    faqs_payload = validate_single_call_payload(
                        {"description": cached_description, "summary": cached_summary, "summary_sentence": cached_summary_sentence, "faqs": json.loads(cached_faqs)},
                        include_faqs,
                    ).get("faqs")
                except Exception:
                    faqs_payload = None
            return GeneratedContent(
                description=sanitize_text(cached_description),
                summary=sanitize_text(cached_summary),
                summary_sentence=sanitize_text(cached_summary_sentence),
                faqs=faqs_payload,
            )

        raw_response = client.generate_text(
            prompt,
            model=ai_config.single_call_model,
            max_tokens=ai_config.max_completion_tokens,
            developer_message=(
                "You produce strict JSON output for pharma content generation. "
                "Return only JSON, no markdown or commentary."
            ),
        )
        try:
            payload = parse_single_call_payload(raw_response, include_faqs)
        except Exception as exc:
            repair_prompt = build_repair_prompt(raw_response, str(exc))
            repaired = client.generate_text(
                repair_prompt,
                model=ai_config.repair_model,
                max_tokens=ai_config.summary_max_completion_tokens,
                developer_message="You fix JSON to be valid and schema-compliant.",
            )
            payload = parse_single_call_payload(repaired, include_faqs)

        description = sanitize_text(payload.get("description") or "")
        summary = sanitize_text(payload.get("summary") or "")
        summary_sentence = sanitize_text(payload.get("summary_sentence") or "")
        faqs = payload.get("faqs") if include_faqs else None
        with cache_lock:
            write_cached_text(cache, drug.drugbank_id, "description", prompt_hash_value, description, ai_config.single_call_model)
            write_cached_text(cache, drug.drugbank_id, "summary", prompt_hash_value, summary, ai_config.single_call_model)
            write_cached_text(
                cache,
                drug.drugbank_id,
                "summary_sentence",
                prompt_hash_value,
                summary_sentence,
                ai_config.single_call_model,
            )
            if include_faqs:
                write_cached_text(
                    cache,
                    drug.drugbank_id,
                    "faqs",
                    prompt_hash_value,
                    json.dumps(faqs or [], ensure_ascii=False),
                    ai_config.single_call_model,
                )
        return GeneratedContent(
            description=description,
            summary=summary,
            summary_sentence=summary_sentence,
            faqs=faqs,
        )

    desc_prompt = build_description_prompt(drug)
    desc_hash = prompt_hash(ai_config.model, desc_prompt)
    with cache_lock:
        description = read_cached_text(cache, drug.drugbank_id, "description", desc_hash)
    if not description:
        description = client.generate_description(desc_prompt)
        with cache_lock:
            write_cached_text(cache, drug.drugbank_id, "description", desc_hash, description, ai_config.model)

    summary = ""
    summary_sentence = ""
    if description:
        summary_prompt = build_summary_prompt(drug, description)
        summary_hash = prompt_hash(ai_config.summary_model, summary_prompt)
        with cache_lock:
            summary = read_cached_text(cache, drug.drugbank_id, "summary", summary_hash) or ""
        if not summary:
            summary = client.generate_summary(summary_prompt)
            with cache_lock:
                write_cached_text(cache, drug.drugbank_id, "summary", summary_hash, summary, ai_config.summary_model)

        summary_sentence_prompt = build_summary_sentence_prompt(drug, description or "")
        summary_sentence_hash = prompt_hash(ai_config.summary_model, summary_sentence_prompt)
        with cache_lock:
            summary_sentence = (
                read_cached_text(cache, drug.drugbank_id, "summary_sentence", summary_sentence_hash) or ""
            )
        if not summary_sentence:
            summary_sentence = client.generate_text(summary_sentence_prompt)
            with cache_lock:
                write_cached_text(
                    cache,
                    drug.drugbank_id,
                    "summary_sentence",
                    summary_sentence_hash,
                    summary_sentence,
                    ai_config.summary_model,
                )

    description = sanitize_text(description)
    summary = sanitize_text(summary)
    summary_sentence = sanitize_text(summary_sentence)
    return GeneratedContent(description=description, summary=summary, summary_sentence=summary_sentence)


def _load_existing_page_models(path: str) -> Dict[str, object]:
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _filter_parsed_drugs(config: PipelineConfig, parsed: Dict[str, DrugData]) -> Dict[str, DrugData]:
    if config.valid_drug_ids:
        parsed = {drug_id: drug for drug_id, drug in parsed.items() if drug_id in config.valid_drug_ids}
    if config.max_drugs:
        limited: Dict[str, DrugData] = {}
        for drug_id in parsed:
            limited[drug_id] = parsed[drug_id]
            if len(limited) >= config.max_drugs:
                break
        parsed = limited
    return parsed


def process_drugs(config: PipelineConfig, ai_config: OpenAIConfig) -> Dict[str, object]:
    ensure_parent_dir(Path(config.database_json))
    ensure_parent_dir(Path(config.page_models_json))
    ensure_parent_dir(Path(config.import_json))
    ensure_parent_dir(Path(config.preview_html))
    ensure_parent_dir(Path(config.generation_cache_json))
    ensure_parent_dir(Path(config.progress_json))
    ensure_parent_dir(Path(config.failed_drugs_jsonl))
    if config.use_existing_database and os.path.isfile(config.database_json):
        logger.info("Using cached database JSON at %s", config.database_json)
        parsed = load_database(config.database_json)
        parsed = _filter_parsed_drugs(config, parsed)
    else:
        parsed = parse_drugbank_xml(config)
        export_database(config.database_json, parsed)

    resume_path = config.resume_from or config.page_models_json
    page_models: Dict[str, object] = {}
    if config.resume_from:
        page_models = _load_existing_page_models(resume_path)
        if page_models:
            logger.info("Resuming from %s with %s existing page models", resume_path, len(page_models))

    cache = load_generation_cache(config.generation_cache_json)
    cache_lock = threading.Lock()
    failure_lock = threading.Lock()
    progress_lock = threading.Lock()

    progress = load_progress(config.progress_json)
    completed_ids = set(progress.completed_at.keys())

    template_definition = load_template_definition(config.template_definition)
    thread_local = threading.local()

    def get_client() -> OpenAIClient:
        client = getattr(thread_local, "client", None)
        if client is None:
            client = OpenAIClient(ai_config, prompt_log_path=config.prompt_log)
            thread_local.client = client
        return client

    def worker(drug_id: str, drug: DrugData) -> Optional[tuple[str, object]]:
        missing = list(validate_drug(drug))
        if missing:
            logger.warning("Skipping %s due to missing fields: %s", drug_id, ", ".join(missing))
            return None
        try:
            client = get_client()
            client.set_context(drug_id)
            generated = generate_for_drug(
                drug,
                client,
                ai_config,
                single_call=config.single_call_generation,
                include_faqs=config.include_faqs,
                cache=cache,
                cache_lock=cache_lock,
            )
            page_model = build_page_model(
                drug,
                client,
                summary=generated.summary,
                description=generated.description,
                summary_sentence=generated.summary_sentence,
                template=template_definition,
            )
            if config.include_faqs and generated.faqs is not None:
                page_model["faqs"] = generated.faqs
            logger.info("Generated content for %s", drug.name)
            retries = client.consume_retry_total(drug_id)
            if retries:
                with failure_lock:
                    append_jsonl(
                        config.failed_drugs_jsonl,
                        {"drug_id": drug_id, "status": "retried", "retries": retries},
                    )
            return drug_id, page_model
        except Exception as exc:  # pragma: no cover - integration layer
            logger.exception("Failed to generate content for %s: %s", drug_id, exc)
            with failure_lock:
                append_jsonl(
                    config.failed_drugs_jsonl,
                    {"drug_id": drug_id, "error": str(exc)},
                )
            with progress_lock:
                progress.mark_failed(drug_id)
            return None
        finally:
            client = getattr(thread_local, "client", None)
            if client is not None:
                client.set_context(None)

    remaining = {
        drug_id: drug
        for drug_id, drug in parsed.items()
        if drug_id not in page_models and drug_id not in completed_ids
    }
    if remaining:
        logger.info("Generating content for %s drugs with up to %s workers", len(remaining), config.max_workers)
    with ThreadPoolExecutor(max_workers=max(config.max_workers, 1)) as executor:
        items = list(remaining.items())
        processed_since_checkpoint = 0
        for start in range(0, len(items), max(config.submit_chunk_size, 1)):
            chunk = items[start : start + max(config.submit_chunk_size, 1)]
            futures = [executor.submit(worker, drug_id, drug) for drug_id, drug in chunk]
            for future in as_completed(futures):
                result = future.result()
                if not result:
                    continue
                drug_id, page_model = result
                page_models[drug_id] = page_model
                with progress_lock:
                    progress.mark_completed(drug_id)
                processed_since_checkpoint += 1
                if processed_since_checkpoint >= max(config.checkpoint_every, 1):
                    export_page_models(config.page_models_json, page_models)
                    export_clean_import(config.import_json, page_models)
                    save_generation_cache(config.generation_cache_json, cache)
                    save_progress(config.progress_json, progress)
                    processed_since_checkpoint = 0

    save_progress(config.progress_json, progress)
    export_page_models(config.page_models_json, page_models)
    export_clean_import(config.import_json, page_models)
    save_html_preview(page_models, config.preview_html)
    save_generation_cache(config.generation_cache_json, cache)
    return page_models


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DrugBank to Pharmaoffer description generator (run with `python src/main.py`)",
    )
    parser.add_argument("--xml-path", required=True, help="Path to DrugBank XML input")
    parser.add_argument("--output-database-json", default="outputs/database.json", help="Parsed database JSON output path")
    parser.add_argument(
        "--output-page-models-json",
        default="outputs/api_pages.json",
        help="Structured API page models JSON output path (primary output)",
    )
    parser.add_argument(
        "--output-import-json",
        default="outputs/api_pages_import.json",
        help="Clean import JSON without template metadata",
    )
    parser.add_argument(
        "--template-definition",
        help="Path to a JSON template definition emitted by the visual builder",
    )
    parser.add_argument("--valid-drugs", help="Comma-separated list of DrugBank IDs or path to file with one ID per line")
    parser.add_argument("--max-drugs", type=int, help="Limit number of drugs processed")
    parser.add_argument("--max-workers", type=int, help="Maximum concurrent OpenAI workers")
    parser.add_argument(
        "--generation-cache-json",
        default="outputs/generation_cache.json",
        help="Path to generation cache JSON for prompt hashing reuse",
    )
    parser.add_argument(
        "--progress-json",
        default="outputs/progress.json",
        help="Path to progress JSON for resumable runs",
    )
    parser.add_argument(
        "--failed-drugs-jsonl",
        default="outputs/failed_drugs.jsonl",
        help="Path to JSONL log of failed drugs",
    )
    parser.add_argument(
        "--resume-from",
        help="Path to an existing page model JSON to resume from (skip already generated IDs)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the default output JSON if it exists",
    )
    parser.add_argument(
        "--force-parse-xml",
        action="store_true",
        help="Always parse the XML even if a cached database.json exists",
    )
    parser.add_argument(
        "--use-existing-database",
        action="store_true",
        default=None,
        help="Reuse outputs/database.json if present (default)",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=25,
        help="Persist checkpoints every N processed drugs (default: 25)",
    )
    parser.add_argument(
        "--submit-chunk-size",
        type=int,
        default=200,
        help="Submit ThreadPoolExecutor jobs in chunks to limit memory (default: 200)",
    )
    parser.add_argument(
        "--single-call-generation",
        action="store_true",
        help="Generate description/summary/summary_sentence (and optional FAQs) in one OpenAI call",
    )
    parser.add_argument(
        "--include-faqs",
        action="store_true",
        help="Include FAQs in single-call generation outputs",
    )
    parser.add_argument(
        "--max-concurrent-requests",
        type=int,
        help="Cap in-flight OpenAI requests (default: 10)",
    )
    parser.add_argument(
        "--max-requests-per-minute",
        type=int,
        help="Optional RPM rate limit (leave unset to disable)",
    )
    parser.add_argument(
        "--max-tokens-per-minute",
        type=int,
        help="Optional TPM rate limit (leave unset to disable)",
    )
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"), help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    setup_logging(args.log_level)
    _self_check_summary_prompt_signature()

    valid_ids = parse_valid_ids(args.valid_drugs)
    output_database_json = str(normalize_repo_path(args.output_database_json, "outputs"))
    output_page_models_json = str(normalize_repo_path(args.output_page_models_json, "outputs"))
    output_import_json = str(normalize_repo_path(args.output_import_json, "outputs"))
    generation_cache_json = str(normalize_repo_path(args.generation_cache_json, "outputs"))
    progress_json = str(normalize_repo_path(args.progress_json, "outputs"))
    failed_drugs_jsonl = str(normalize_repo_path(args.failed_drugs_jsonl, "outputs"))
    preview_html = str(normalize_repo_path("outputs/api_pages_preview.html", "outputs"))
    prompt_log = str(normalize_repo_path("logs/prompts.log", "logs"))

    use_existing_database = True if args.use_existing_database is None else args.use_existing_database
    if args.force_parse_xml:
        use_existing_database = False

    resume_from = None
    if args.resume_from:
        resume_from = str(normalize_repo_path(args.resume_from, "outputs"))
    elif args.resume:
        resume_from = output_page_models_json

    pipeline_config = PipelineConfig.from_args(
        xml_path=args.xml_path,
        database_json=output_database_json,
        page_models_json=output_page_models_json,
        import_json=output_import_json,
        preview_html=preview_html,
        prompt_log=prompt_log,
        template_definition=args.template_definition,
        valid_drug_ids=valid_ids,
        max_drugs=args.max_drugs,
        max_workers=args.max_workers,
        generation_cache_json=generation_cache_json,
        progress_json=progress_json,
        failed_drugs_jsonl=failed_drugs_jsonl,
        use_existing_database=use_existing_database,
        resume_from=resume_from,
        log_level=args.log_level,
        submit_chunk_size=args.submit_chunk_size,
        checkpoint_every=args.checkpoint_every,
        single_call_generation=args.single_call_generation,
        include_faqs=args.include_faqs,
    )
    ai_config = OpenAIConfig()
    if args.max_concurrent_requests:
        ai_config.max_concurrent_requests = args.max_concurrent_requests
    if args.max_requests_per_minute:
        ai_config.max_requests_per_minute = args.max_requests_per_minute
    if args.max_tokens_per_minute:
        ai_config.max_tokens_per_minute = args.max_tokens_per_minute

    logger.info("Starting generation pipeline")
    process_drugs(pipeline_config, ai_config)
    logger.info("Finished generation pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

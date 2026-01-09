"""DrugBank -> AI -> HTML pipeline with CLI."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, Optional

from src.config import OpenAIConfig, PipelineConfig, parse_valid_ids
from src.drugbank_parser import load_database_json, parse_drugbank_xml
from src.exporters import export_clean_import, export_database, export_page_models
from src.generation_cache import (
    load_generation_cache,
    prompt_hash,
    read_cached_text,
    save_generation_cache,
    write_cached_text,
)
from src.generators import build_description_prompt, build_summary_prompt, build_summary_sentence_prompt
from src.models import DrugData, GeneratedContent
from src.openai_client import OpenAIClient
from src.page_builder import build_page_model
from src.preview_renderer import save_html_preview
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


def validate_drug(drug: DrugData) -> Iterable[str]:
    missing = []
    if not drug.name:
        missing.append("name")
    return missing


def generate_for_drug(
    drug: DrugData,
    client: OpenAIClient,
    ai_config: OpenAIConfig,
    cache: Dict[str, object],
    cache_lock: threading.Lock,
) -> GeneratedContent:
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

        summary_sentence_prompt = build_summary_sentence_prompt(drug, description)
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
    if config.use_existing_database and os.path.isfile(config.database_json):
        logger.info("Using cached database JSON at %s", config.database_json)
        parsed = load_database_json(config.database_json)
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
            generated = generate_for_drug(drug, client, ai_config, cache, cache_lock)
            page_model = build_page_model(
                drug,
                client,
                summary=generated.summary,
                description=generated.description,
                summary_sentence=generated.summary_sentence,
                template=template_definition,
            )
            logger.info("Generated content for %s", drug.name)
            return drug_id, page_model
        except Exception as exc:  # pragma: no cover - integration layer
            logger.exception("Failed to generate content for %s: %s", drug_id, exc)
            return None

    remaining = {drug_id: drug for drug_id, drug in parsed.items() if drug_id not in page_models}
    if remaining:
        logger.info("Generating content for %s drugs with up to %s workers", len(remaining), config.max_workers)
    with ThreadPoolExecutor(max_workers=max(config.max_workers, 1)) as executor:
        futures = [executor.submit(worker, drug_id, drug) for drug_id, drug in remaining.items()]
        for future in as_completed(futures):
            result = future.result()
            if not result:
                continue
            drug_id, page_model = result
            page_models[drug_id] = page_model

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
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"), help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    setup_logging(args.log_level)

    valid_ids = parse_valid_ids(args.valid_drugs)
    pipeline_config = PipelineConfig.from_args(
        xml_path=args.xml_path,
        database_json=args.output_database_json,
        page_models_json=args.output_page_models_json,
        import_json=args.output_import_json,
        template_definition=args.template_definition,
        valid_drug_ids=valid_ids,
        max_drugs=args.max_drugs,
        max_workers=args.max_workers,
        generation_cache_json=args.generation_cache_json,
        use_existing_database=not args.force_parse_xml,
        resume_from=args.resume_from or (args.output_page_models_json if args.resume else None),
        log_level=args.log_level,
    )
    ai_config = OpenAIConfig()

    logger.info("Starting generation pipeline")
    process_drugs(pipeline_config, ai_config)
    logger.info("Finished generation pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""DrugBank -> AI -> HTML pipeline with CLI."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable

from src.config import OpenAIConfig, PipelineConfig, parse_valid_ids
from src.drugbank_parser import parse_drugbank_xml
from src.exporters import export_database, export_descriptions_json, export_descriptions_xml, export_page_models
from src.generators import build_description_prompt, build_summary_prompt, build_summary_sentence_prompt
from src.html_renderer import render_html
from src.models import DrugData, GeneratedContent
from src.page_builder import build_page_model
from src.preview_renderer import save_html_preview
from src.openai_client import OpenAIClient


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


def write_prompt_log(path: str, prompt: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(prompt + "\n\n")


def generate_for_drug(drug: DrugData, client: OpenAIClient, config: PipelineConfig) -> GeneratedContent:
    desc_prompt = build_description_prompt(drug)
    write_prompt_log(config.description_prompts_log, desc_prompt)
    description = client.generate_description(desc_prompt)

    summary_prompt = build_summary_prompt(drug, description)
    write_prompt_log(config.summary_prompts_log, summary_prompt)
    summary = client.generate_summary(summary_prompt)

    summary_sentence_prompt = build_summary_sentence_prompt(drug)
    write_prompt_log(config.summary_prompts_log, summary_sentence_prompt)
    summary_sentence = client.generate_text(summary_sentence_prompt)

    description = sanitize_text(description)
    summary = sanitize_text(summary)
    summary_sentence = sanitize_text(summary_sentence)
    return GeneratedContent(description=description, summary=summary, summary_sentence=summary_sentence)


def process_drugs(config: PipelineConfig, ai_config: OpenAIConfig) -> Dict[str, object]:
    client = OpenAIClient(ai_config)
    parsed = parse_drugbank_xml(config)
    export_database(config.database_json, parsed)

    page_models: Dict[str, object] = {}
    legacy_descriptions: Dict[str, str] | None = (
        {} if config.descriptions_json or config.descriptions_xml else None
    )
    for drug_id, drug in parsed.items():
        missing = list(validate_drug(drug))
        if missing:
            logger.warning("Skipping %s due to missing fields: %s", drug_id, ", ".join(missing))
            continue
        try:
            generated = generate_for_drug(drug, client, config)
            page_models[drug_id] = build_page_model(
                drug,
                client,
                summary=generated.summary,
                description=generated.description,
                summary_sentence=generated.summary_sentence,
            )
            if legacy_descriptions is not None:
                html = render_html(drug, generated)
                legacy_descriptions[drug_id] = html
            logger.info("Generated content for %s", drug.name)
        except Exception as exc:  # pragma: no cover - integration layer
            logger.exception("Failed to generate content for %s: %s", drug_id, exc)

    export_page_models(config.page_models_json, page_models)
    save_html_preview(page_models, config.preview_html)
    if legacy_descriptions is not None:
        if config.descriptions_json:
            export_descriptions_json(config.descriptions_json, legacy_descriptions)
        if config.descriptions_xml:
            export_descriptions_xml(config.descriptions_xml, parsed, legacy_descriptions)
    return page_models


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DrugBank to Pharmaoffer description generator (run with `python src/main.py`)",
    )
    parser.add_argument("--xml-path", required=True, help="Path to DrugBank XML input")
    parser.add_argument("--output-database-json", default="outputs/database.json", help="Parsed database JSON output path")
    parser.add_argument(
        "--output-descriptions-json",
        default=None,
        help="Optional legacy HTML description JSON output path (omit to skip)",
    )
    parser.add_argument(
        "--output-descriptions-xml",
        default=None,
        help="Optional legacy HTML description XML output path (omit to skip)",
    )
    parser.add_argument(
        "--output-page-models-json",
        default="outputs/api_pages.json",
        help="Structured API page models JSON output path (primary output)",
    )
    parser.add_argument(
        "--output-preview-html",
        default="outputs/api_pages_preview.html",
        help="HTML preview file rendered from structured page models",
    )
    parser.add_argument("--description-log", default="logs/description_prompts.log", help="Where to write description prompts used during generation")
    parser.add_argument("--summary-log", default="logs/summary_prompts.log", help="Where to write summary prompts used during generation")
    parser.add_argument("--valid-drugs", help="Comma-separated list of DrugBank IDs or path to file with one ID per line")
    parser.add_argument("--max-drugs", type=int, help="Limit number of drugs processed")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"), help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    setup_logging(args.log_level)

    valid_ids = parse_valid_ids(args.valid_drugs)
    pipeline_config = PipelineConfig.from_args(
        xml_path=args.xml_path,
        database_json=args.output_database_json,
        descriptions_json=args.output_descriptions_json,
        descriptions_xml=args.output_descriptions_xml,
        page_models_json=args.output_page_models_json,
        preview_html=args.output_preview_html,
        valid_drug_ids=valid_ids,
        max_drugs=args.max_drugs,
        log_level=args.log_level,
        description_prompts_log=args.description_log,
        summary_prompts_log=args.summary_log,
    )
    ai_config = OpenAIConfig()

    logger.info("Starting generation pipeline")
    process_drugs(pipeline_config, ai_config)
    logger.info("Finished generation pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


"""DrugBank -> AI -> HTML pipeline with CLI."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from typing import Dict, Iterable

from src.config import OpenAIConfig, PipelineConfig, parse_valid_ids
from src.drugbank_parser import parse_drugbank_xml
from src.exporters import export_clean_import, export_database, export_page_models
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


def generate_for_drug(drug: DrugData, client: OpenAIClient, config: PipelineConfig) -> GeneratedContent:
    desc_prompt = build_description_prompt(drug)
    description = client.generate_description(desc_prompt)

    summary_prompt = build_summary_prompt(drug, description)
    summary = client.generate_summary(summary_prompt)

    summary_sentence_prompt = build_summary_sentence_prompt(drug, description_text)
    summary_sentence = client.generate_text(summary_sentence_prompt)

    description = sanitize_text(description)
    summary = sanitize_text(summary)
    summary_sentence = sanitize_text(summary_sentence)
    return GeneratedContent(description=description, summary=summary, summary_sentence=summary_sentence)


def process_drugs(config: PipelineConfig, ai_config: OpenAIConfig) -> Dict[str, object]:
    client = OpenAIClient(ai_config, prompt_log_path=config.prompt_log)
    parsed = parse_drugbank_xml(config)
    export_database(config.database_json, parsed)

    template_definition = load_template_definition(config.template_definition)
    page_models: Dict[str, object] = {}
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
                template=template_definition,
            )
            logger.info("Generated content for %s", drug.name)
        except Exception as exc:  # pragma: no cover - integration layer
            logger.exception("Failed to generate content for %s: %s", drug_id, exc)

    export_page_models(config.page_models_json, page_models)
    export_clean_import(config.import_json, page_models)
    save_html_preview(page_models, config.preview_html)
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
        log_level=args.log_level,
    )
    ai_config = OpenAIConfig()

    logger.info("Starting generation pipeline")
    process_drugs(pipeline_config, ai_config)
    logger.info("Finished generation pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


"""DrugBank -> AI -> HTML pipeline with CLI."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable

from config import OpenAIConfig, PipelineConfig, parse_valid_ids
from drugbank_parser import parse_drugbank_xml
from exporters import export_database, export_descriptions_json, export_descriptions_xml
from generators import build_description_prompt, build_summary_prompt
from html_renderer import render_html
from models import DrugData, GeneratedContent
from openai_client import OpenAIClient


logger = logging.getLogger(__name__)


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def sanitize_text(text: str) -> str:
    """Remove square-bracketed citations that sometimes appear in DrugBank content."""
    return re.sub(r"\[.*?\]", "", text or "")


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

    description = sanitize_text(description)
    summary = sanitize_text(summary)
    return GeneratedContent(description_html=description, summary=summary)


def process_drugs(config: PipelineConfig, ai_config: OpenAIConfig) -> Dict[str, str]:
    client = OpenAIClient(ai_config)
    parsed = parse_drugbank_xml(config)
    export_database(config.database_json, parsed)

    descriptions: Dict[str, str] = {}
    for drug_id, drug in parsed.items():
        missing = list(validate_drug(drug))
        if missing:
            logger.warning("Skipping %s due to missing fields: %s", drug_id, ", ".join(missing))
            continue
        try:
            generated = generate_for_drug(drug, client, config)
            html = render_html(drug, generated)
            descriptions[drug_id] = html
            logger.info("Generated content for %s", drug.name)
        except Exception as exc:  # pragma: no cover - integration layer
            logger.exception("Failed to generate content for %s: %s", drug_id, exc)

    export_descriptions_json(config.descriptions_json, descriptions)
    export_descriptions_xml(config.descriptions_xml, parsed, descriptions)
    return descriptions


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DrugBank to Pharmaoffer description generator")
    parser.add_argument("--xml-path", required=True, help="Path to DrugBank XML input")
    parser.add_argument("--output-database-json", default="outputs/database.json", help="Parsed database JSON output path")
    parser.add_argument("--output-descriptions-json", default="outputs/api_descriptions.json", help="Generated descriptions JSON output path")
    parser.add_argument("--output-descriptions-xml", default="outputs/api_descriptions.xml", help="Generated descriptions XML output path")
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


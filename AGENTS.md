This repository implements a modular DrugBank → API page model generator.

## What this repo does
- Parses DrugBank XML into structured `DrugData`.
- Uses OpenAI to generate pharma-grade narrative text (plain text, no HTML).
- Builds structured API page models (`api_pages.json`) plus a clean import payload.
- Optionally renders HTML previews and per-section HTML fragments.
- Provides FAQ generators for API pages and certificate-filter pages.
- Exposes both CLI entrypoints and a lightweight browser UI.

## Key entrypoints
- `python src/main.py` — end-to-end pipeline (parse → generate → page models).
- `python -m src.section_renderer` — convert `api_pages.json` into section HTML blocks.
- `python -m src.faq_generator` — build API FAQs from page models.
- `python -m src.cert_faq_generator` — build certificate-filter FAQs from filtered pages.
- `python launch_interface.py` — run the UI wrapper for the CLI.

## Core modules
- `src/config.py` — env-driven configuration.
- `src/drugbank_parser.py` — XML parsing into `DrugData`.
- `src/generators.py` — prompt builders for descriptions and summaries.
- `src/openai_client.py` — OpenAI wrapper with retries and prompt logging.
- `src/page_builder.py` — assembles structured page models.
- `src/exporters.py` — JSON export helpers.
- `src/preview_renderer.py` / `src/section_renderer.py` — HTML previews + section blocks.

## Outputs
- `outputs/database.json` — parsed DrugBank data.
- `outputs/api_pages.json` — structured page models (primary output).
- `outputs/api_pages_import.json` — clean import payload (template metadata removed).
- `outputs/api_pages_preview.html` — HTML preview of page models.
- `outputs/generation_cache.json` — prompt hash cache for reuse.
- `logs/prompts.log` — captured prompts (when enabled).

## Environment variables
- `OPENAI_API_KEY` (required)
- `OPENAI_ORG`, `OPENAI_PROJECT` (optional)
- `OPENAI_MODEL`, `OPENAI_SUMMARY_MODEL`
- `OPENAI_MAX_COMPLETION_TOKENS`, `OPENAI_SUMMARY_MAX_COMPLETION_TOKENS`
- `OPENAI_MAX_RETRIES`, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_WORKERS`
- `LOG_LEVEL`

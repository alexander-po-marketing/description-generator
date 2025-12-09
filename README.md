# DrugBank to Pharmaoffer Content Pipeline

This project transforms DrugBank XML exports into structured JSON ready for Pharmaoffer API product pages. The pipeline parses DrugBank data, generates expert pharmaceutical descriptions with OpenAI, builds UI-agnostic page models, and can optionally emit HTML previews as well as per-section HTML blocks for database ingestion.

## Features

- **Modular architecture:** dedicated modules for configuration, parsing, generation, rendering, exporting, and the CLI entrypoint.
- **Configurable OpenAI usage:** models, completion token limits, retries, and credentials are driven by environment variables.
- **Robust parsing:** pulls core DrugBank attributes, classifications, products, categories, and references with graceful handling of missing data.
- **Enhanced prompting:** pharma-grade description and summary prompts with logged inputs for traceability.
- **Structured page models:** JSON designed for flexible React/Vue rendering (no embedded HTML tags).
- **Optional HTML previews:** renderable snippets remain available for debugging.
- **Section HTML export:** reuse the preview renderer to build clean, per-section HTML fragments suitable for storing directly in the database.
- **CLI and UI control:** run the pipeline via command line or through the browser-based controller.
- **Logging and retries:** visibility into each pipeline stage and resilient OpenAI calls.

## Repository layout

```
inputs/     # DrugBank XML and optional valid-ID files
outputs/    # database.json, api_pages.json, optional legacy preview files, section_html/
logs/       # prompt logs and pipeline logs
cache/      # scratch directory for experiments
scripts/    # helpers including the interface HTTP server
interface/  # index.html + UI assets served by the interface HTTP server
src/        # core pipeline modules and CLI entrypoint
```

## Quickstart (CLI)

1. **Set credentials**

   ```bash
   export OPENAI_API_KEY=your_key
   # optional
   export OPENAI_ORG=your_org
   export OPENAI_PROJECT=your_project
   ```

2. **Run the generator**

   ```bash
    python src/main.py \
      --xml-path inputs/drugbank.xml \
      --output-database-json outputs/database.json \
      --output-page-models-json outputs/api_pages.json \
     --valid-drugs inputs/valid_ids.txt \
    --max-drugs 50 \
    --log-level INFO
  ```

 Supply `--valid-drugs` as a comma-separated list or a path to a text file (one DrugBank ID per line). Omit it to process all entries. Use `--max-drugs` to cap processing during tests.

3. **Export section-level HTML (optional)**

   Convert existing `api_pages.json` output into database-ready section HTML fragments:

   ```bash
   python -m src.section_renderer \
     --input outputs/api_pages.json \
     --output outputs/section_html/section_blocks.json
   ```

   The exporter reads the generated page models, reuses the preview rendering blocks, and writes a dictionary keyed by API ID where each value contains section HTML (e.g., `hero`, `overview`, `pharmacology`, `adme_pk`, `formulation`, `regulatory`, `safety`).

4. **Generate FAQs from existing pages**

   Convert structured API page models into templated FAQs (mixing direct substitutions and LLM-backed answers):

   ```bash
   python -m src.faq_generator \
     --input outputs/api_pages.json \
     --output outputs/api_faqs.json \
     --max-faqs 20 \
     --model gpt-4o-mini
   ```

   Direct FAQs use placeholder substitution; LLM FAQs reuse the existing OpenAI configuration and pull context from hero, overview, pharmacology, ADME, and regulatory slices. Missing placeholders are logged and skipped to keep outputs clean.

### Running the FAQ generator manually

The FAQ generator only needs the structured page models produced by the main pipeline:

- **Required input:** `outputs/api_pages.json` (created by `python src/main.py ...`).
- **Output produced:** `outputs/api_faqs.json`.

Launch it directly from the repository root:

```bash
python -m src.faq_generator \
  --input outputs/api_pages.json \
  --output outputs/api_faqs.json \
  --max-faqs 20 \
  --model gpt-4o-mini
```

The script skips any FAQ template that lacks the required context (including fallback fields) and writes the resulting per-drug FAQ list to the specified output path.

## Interactive web interface

The `/interface/index.html` UI wraps the CLI with a simple control panel to set credentials, browse repository files, pick output targets, and launch runs from the browser. It also exposes a one-click action to run the section HTML exporter against an existing `outputs/api_pages.json`, saving results under `outputs/section_html/`.

1. Start the local server and open the UI automatically with Chrome/Chromium:

   ```bash
   python launch_interface.py
   ```

   The launcher waits for the server to respond, then opens the interface with `--app=http://localhost:8000/`. If Chrome/Chromium is not installed, the script prints the URL so you can open it manually.

2. To run the server without the launcher, use:

   ```bash
   python scripts/interface_server.py --host 0.0.0.0 --port 8000
   ```

   Then open http://localhost:8000/ in your browser. (The server serves the `interface/` directory as its static root.)

The UI suggests paths from `inputs/`, `outputs/`, and `logs/`, exposes overwrite/continue safeguards, and displays stdout/stderr from the underlying CLI run.

## Configuration

Environment variables control OpenAI behavior and defaults:

- `OPENAI_MODEL` (default `gpt-5.1-chat-latest`)
- `OPENAI_SUMMARY_MODEL` (default `gpt-4o-mini`)
- `OPENAI_MAX_COMPLETION_TOKENS` (default `700`)
- `OPENAI_SUMMARY_MAX_COMPLETION_TOKENS` (default `200`)
- `OPENAI_MAX_RETRIES` (default `3`)
- `OPENAI_TIMEOUT_SECONDS` (default `30`)
- `LOG_LEVEL` (default `INFO`)

## Outputs

- `outputs/database.json` — structured parsed DrugBank data per DrugBank ID (debug/secondary source).
- `outputs/api_pages.json` — structured, HTML-free page models ready for UI rendering (primary output).
- `outputs/api_pages_preview.html` — quick HTML preview of the structured models using the bundled template.
- `outputs/section_html/section_blocks.json` — dictionary mapping API IDs to per-section HTML fragments ready for database storage.
- `outputs/api_faqs.json` — templated FAQ entries (direct and LLM-backed) for each API, sourced from the structured page models.
- `logs/prompts.log` — captured prompts for auditing and debugging.

## Testing and extension

The modular design isolates parsing, prompt generation, rendering, and exporting, making it straightforward to unit test each component. Swap models, tweak prompts, or adjust HTML layout by editing the dedicated modules without touching the CLI.

## HTML classes used in generated blocks

The section renderer intentionally emits minimal HTML wrappers so styling can be applied later. Blocks may include these classes:

- `api-page-preview` — wrapper for a single API preview section.
- `hero-block` — container for the hero/header content.
- `lead` — summary paragraph in the hero.
- `subblock`, `subblock-header`, `subblock-body` — titled sub-sections used across identification, pharmacology, ADME, formulation, regulatory, and safety blocks.
- `chip-list`, `chip` — inline lists for categories, markets, manufacturers, and keywords.
- `block` — collapsible panels for in-depth sections.
- `summary-title`, `summary-text` — header text inside collapsible panels.
- `facts-grid`, `fact-card`, `fact-label`, `fact-value` — structured facts in the hero block.
- `long-description` — wrapper for narrative description paragraphs.

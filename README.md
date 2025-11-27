# DrugBank to Pharmaoffer Content Pipeline

This project transforms DrugBank XML exports into structured JSON ready for Pharmaoffer API product pages. The pipeline parses DrugBank data, generates expert pharmaceutical descriptions with OpenAI, builds UI-agnostic page models, and can optionally emit legacy HTML previews.

## Features

- **Modular architecture:** dedicated modules for configuration, parsing, generation, rendering, exporting, and the CLI entrypoint.
- **Configurable OpenAI usage:** models, completion token limits, retries, and credentials are driven by environment variables.
- **Robust parsing:** pulls core DrugBank attributes, classifications, products, categories, and references with graceful handling of missing data.
- **Enhanced prompting:** pharma-grade description and summary prompts with logged inputs for traceability.
- **Structured page models:** JSON designed for flexible React/Vue rendering (no embedded HTML tags).
- **Optional HTML previews:** renderable snippets remain available for debugging.
- **CLI and UI control:** run the pipeline via command line or through the browser-based controller.
- **Logging and retries:** visibility into each pipeline stage and resilient OpenAI calls.

## Repository layout

```
inputs/     # DrugBank XML and optional valid-ID files
outputs/    # database.json, api_pages.json, optional legacy preview files
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

## Interactive web interface

The `/interface/index.html` UI wraps the CLI with a simple control panel to set credentials, browse repository files, pick output targets, and launch runs from the browser.

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
- `logs/prompts.log` — captured prompts for auditing and debugging.

## Testing and extension

The modular design isolates parsing, prompt generation, rendering, and exporting, making it straightforward to unit test each component. Swap models, tweak prompts, or adjust HTML layout by editing the dedicated modules without touching the CLI.

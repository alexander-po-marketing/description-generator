# DrugBank Description Generator

This repository contains an experimental pipeline that converts a DrugBank XML export into structured drug data and AI-generated HTML descriptions for Pharmaoffer product pages. The original prototype lives in `scripts/drugbank_to_html_2.py`; new scaffolding adds a clearer repository layout plus a static interface to configure runs.

## Repository layout

- `interface/` – Static HTML/JS/CSS for configuring credentials, file paths, and pipeline options.
- `inputs/` – Source files such as DrugBank XML drops and optional valid-drug ID lists.
  - `inputs/drugbank/database_part_1.xml` – Sample XML fragment from the legacy repository.
- `outputs/` – Targets for generated `database.json`, `api_descriptions.json`, and `api_descriptions.xml`.
- `logs/` – Text logs from CLI runs and the helper server.
- `cache/` – Temporary artifacts (model caches, parsed chunks, etc.).
- `scripts/` – Python entry points and helpers, including the legacy generator and a lightweight interface server.

This layout keeps inputs, outputs, transient cache data, logs, and browser assets clearly separated while preserving the legacy script.

## Interface

1. Start the helper API in a terminal:
   ```bash
   python scripts/interface_server.py --port 8000
   ```
2. Serve the interface (any static server works) or open it directly via file://:
   ```bash
   cd interface && python -m http.server 4173
   ```
3. In your browser, open `http://localhost:4173` (or open `interface/index.html` directly) and configure:
   - OpenAI API key, org, and project.
   - Model settings (model name, temperature, max tokens).
   - Paths for the DrugBank XML, existing database JSON, and description outputs.
   - Pipeline options such as valid drug IDs (list or file), max drug count, cache path, and log level.
   - Whether to overwrite or continue when outputs already exist.
4. Click **Run Generator** to POST your configuration to the helper API. The panel returns the CLI stdout/stderr so you can monitor status and logs.

## CLI wrapper

`scripts/run_pipeline.py` is a placeholder CLI that mirrors the options exposed by the interface and writes configuration/log messages to `logs/pipeline_run.log`. Replace the stubbed `execute_pipeline` function with the real parsing and OpenAI generation logic when the refactor is ready.

Example dry-run invocation:
```bash
python scripts/run_pipeline.py \
  --xml-path inputs/drugbank/database_part_1.xml \
  --database-json outputs/database.json \
  --descriptions-json outputs/api_descriptions.json \
  --descriptions-xml outputs/api_descriptions.xml \
  --valid-drug-ids DB13928 \
  --max-drugs 5 \
  --log-level DEBUG \
  --dry-run
```

## Notes

- Secrets are never stored; supply OpenAI credentials at runtime via the interface or CLI arguments.
- The helper server uses permissive CORS headers so the static interface can run from `file://` or any localhost port.
- Existing log and cache folders are created automatically by the CLI wrapper.

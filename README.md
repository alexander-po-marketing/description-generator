# DrugBank to Pharmaoffer Content Pipeline

This project transforms DrugBank XML exports into structured JSON, XML, and HTML suitable for Pharmaoffer API product pages. The pipeline parses DrugBank data, generates expert pharmaceutical descriptions with OpenAI, renders clean HTML sections, and exports multiple machine-readable formats.

## Features

- **Modular architecture:** dedicated modules for configuration, parsing, generation, rendering, exporting, and the CLI entrypoint.
- **Configurable OpenAI usage:** models, temperature, max tokens, retries, and credentials are driven by environment variables.
- **Robust parsing:** pulls core DrugBank attributes, classifications, products, categories, and references with graceful handling of missing data.
- **Enhanced prompting:** pharma-grade description and summary prompts with logged inputs for traceability.
- **Clean HTML:** semantic sections for identification, pharmacology, taxonomy, and references.
- **CLI-driven:** process entire dumps or subsets with filtering, max-count limits, and explicit output paths.
- **Logging and retries:** visibility into each pipeline stage and resilient OpenAI calls.

## Quickstart

1. **Set credentials**

   ```bash
   export OPENAI_API_KEY=your_key
   # optional
   export OPENAI_ORG=your_org
   export OPENAI_PROJECT=your_project
   ```

2. **Run the generator**

   ```bash
   python drugbank_to_html_2.py \
     --xml-path /path/to/drugbank.xml \
     --output-database-json database.json \
     --output-descriptions-json api_descriptions.json \
     --output-descriptions-xml api_descriptions.xml \
     --valid-drugs DB13928,DB14596 \
     --max-drugs 50 \
     --log-level INFO
   ```

   Supply `--valid-drugs` as a comma-separated list or a path to a text file (one DrugBank ID per line). Omit it to process all entries. Use `--max-drugs` to cap processing during tests.

## Configuration

Environment variables control OpenAI behavior and defaults:

- `OPENAI_MODEL` (default `gpt-5.1`)
- `OPENAI_SUMMARY_MODEL` (default `gpt-4o-mini`)
- `OPENAI_TEMPERATURE` (default `0.4`)
- `OPENAI_MAX_TOKENS` (default `700`)
- `OPENAI_SUMMARY_MAX_TOKENS` (default `200`)
- `OPENAI_MAX_RETRIES` (default `3`)
- `OPENAI_TIMEOUT_SECONDS` (default `30`)
- `LOG_LEVEL` (default `INFO`)

## Outputs

- `database.json` — structured parsed DrugBank data per DrugBank ID.
- `api_descriptions.json` — generated HTML descriptions keyed by DrugBank ID.
- `api_descriptions.xml` — XML wrapper containing `<drug><name/><cas-number/><description/></drug>` entries.
- `description_prompts.log` and `summary_prompts.log` — captured prompts for auditing and debugging.

## Testing and extension

The modular design isolates parsing, prompt generation, rendering, and exporting, making it straightforward to unit test each component. Swap models, tweak prompts, or adjust HTML layout by editing the dedicated modules without touching the CLI.

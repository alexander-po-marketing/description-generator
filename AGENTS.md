You are an advanced AI code assistant with full read–write access to this file:

/mnt/data/drugbank_to_html_2_beta.py

This script was originally written by a junior developer and needs a serious upgrade.

1. Context & Current Script

The current script does the following:

Parses a DrugBank XML file.

Extracts selected fields for each drug (name, CAS, indication, pharmacodynamics, mechanism of action, groups, categories, brands, products, classification, references, etc.).

Uses OpenAI chat completions to:

Generate a 250–300 word SEO-optimized API description in HTML (<p>).

Generate a 1–2 sentence summary.

Builds HTML sections:

“General Description”

“Identification”

“Pharmacology”

“Chemical Taxonomy”

“References” / external links

Writes multiple outputs:

database.json – raw parsed drug data

api_descriptions.json – final HTML description per DrugBank ID

api_descriptions.xml – XML with <drug><name/><cas-number/><description/></drug>

The problem:
The script is monolithic, not very robust, not configurable, and the prompting & HTML structure are basic. It works, but it’s “junior code”.

2. High-Level Goals

Your job is to rewrite and significantly improve this script into a production-grade pipeline, and also improve the quality and structure of the generated descriptions themselves.

You are allowed to:

Refactor the architecture (multiple modules, cleaner abstractions).

Improve the OpenAI prompting to get better, more structured, more useful descriptions and summaries.

Improve the HTML structure for SEO, UX, and maintainability.

Add scalability & robustness (multiple drugs, retries, batching, logging).

Add strong configurability (models, fields, limits).

Make the entire system easier to test, extend, and operate.

Do not turn this into a completely different project; keep the core idea:
DrugBank XML → structured drug data → AI-generated description + summary → HTML/JSON/XML outputs for Pharmaoffer API product pages.

3. New Architecture & Modules

Refactor into a clean, modular structure. Suggested modules (you can adapt):

config.py

Constants and settings: model names, default paths, limits, desired fields, etc.

Read environment vars for OpenAI credentials.

drugbank_parser.py

All logic to parse DrugBank XML into structured objects.

models.py

Typed dataclasses / Pydantic models for:

DrugData (parsed fields)

GeneratedContent (description + summary + any structured sub-blocks)

openai_client.py

OpenAI client initialization (no hard-coded secrets).

Functions to:

Generate full descriptions.

Generate short summaries.

Optionally generate structured sections.

html_renderer.py

Logic for turning DrugData + GeneratedContent into clean, valid HTML.

Reusable helpers to build <section>, <dl>, tables, etc.

exporters.py

Functions to write:

database.json

api_descriptions.json

api_descriptions.xml

cli.py or main.py

CLI entry point using argparse.

You can keep drugbank_to_html_2_beta.py as a thin wrapper that calls into the new modules, or replace it with main.py.

4. Improve the AI Prompts & Description Structure

The current prompts are simple and only require “one big <p> tag”. Improve this by:

Upgrading the main description prompt so that:

It explicitly structures the content for pharma use:

2–3 short paragraphs, inside one wrapper container (e.g. one <div> with multiple <p>s, or a single <p> with <br> breaks — pick a consistent, SEO-friendly pattern).

Clear emphasis on:

Mechanism of action & pharmacology

Key clinical uses / indications

Formulation / route of administration

Benefits (e.g. patient adherence, PK profile)

Safety/high-level risk notes (without giving medical advice)

It is SEO-optimized:

Include the API name, synonyms or brand names when relevant.

Use relevant technical keywords naturally (GLP-1 receptor agonist, peptide API, etc., when present in source).

It targets the audience explicitly:

Formulation scientists

Sourcing managers

Regulatory / QA

CDMOs/CROs

Allow structured description outputs
Modify the prompt so the model returns a simple, machine-parseable structure, e.g.:

Either a single HTML block with clear internal structure

Or a lightweight pseudo-JSON / markdown structure that your code then converts to HTML sections, e.g.:

Overview

Mechanism & Pharmacology

Formulation & Manufacturing

Clinical & Regulatory notes (high-level)

Sourcing/Quality considerations

Pick a structure that is:

Stable

Easy to parse

Useful for CMS and UX

Improve the summary prompt:

1–2 sentences, explicitly for:

Search snippets

Card/preview UI

Emphasize:

What the API does

Why it’s notable (e.g. once-weekly GLP-1 agonist, strong efficacy in T2DM/obesity).

Keep the core idea (description + summary), but upgrade the output quality.

5. Type Hints, Dataclasses & Validation

Add full type hints everywhere.

Introduce dataclasses (or Pydantic models) for:

DrugData — parsed from XML (name, CAS, groups, pharmacology fields, etc.)

GeneratedContent — holds the description HTML, summary, and optionally structured sections.

Validate critical fields:

Ensure name and description are present before exporting.

Log and skip drugs that don’t have enough data to generate meaningful content.

6. Parsing & Field Handling

Clean up parse_drugbank_xml:

Move tag-specific logic (groups, classification, categories, international-brands, products, general-references, external-links) into separate helper functions.

Make desired_fields and valid_drugs configurable via config.py and CLI flags.

Ensure the parser:

Handles namespaces safely.

Gracefully skips malformed entries.

Can optionally restrict to a subset of drug IDs for testing (--valid-drugs).

7. HTML Rendering Improvements

Keep roughly the same high-level sections:

General Description

Identification

Pharmacology

Chemical Taxonomy

References / External Links

But:

Clean up the HTML structure:

Valid tags

No stray <td>/</tr> inside <dl>

No missing closing tags

Make section generation declarative, e.g.:

A mapping from logical fields → <dt>/<dd> pairs.

Allow easy changes to layout later (e.g. switching from <dl> to <table>).

Ensure the final HTML:

Is well-formed.

Is reasonably readable if viewed raw.

Is safe from trivial injection (strip weird brackets, etc.).

8. Scalability, Performance & Robustness

Add a simple control over how many drugs to process (--max-drugs) so we can test on subsets.

Add retries with backoff on OpenAI calls (you can abstract retries into a helper).

Optionally:

Add batching or basic concurrency (e.g. asyncio or concurrent.futures) for generating descriptions for multiple drugs, while respecting rate limits.

Ensure that:

A failure for one drug does not crash the whole run.

All failures are logged with reasons.

9. Config & Secrets

Remove hard-coded OpenAI credentials.

Read from environment variables (OPENAI_API_KEY, OPENAI_ORG, OPENAI_PROJECT) in openai_client.py.

Make model names, temp, max tokens, and number of retries configurable.

10. CLI & UX

Replace input() with argparse-based CLI:

--xml-path

--output-database-json

--output-descriptions-json

--output-descriptions-xml

--valid-drugs (comma-separated or path to a txt file)

--max-drugs

--log-level

Provide a clear --help.

11. Logging & Monitoring

Use the logging module.

Log:

Start/end of major phases (parsing, generation, export).

Per-drug status (success, skipped, error).

OpenAI errors and retries.

12. Backwards Compatibility

Try to keep outputs structurally compatible:

Still produce database.json, api_descriptions.json, api_descriptions.xml.

Still ensure each <drug> in XML contains <name>, <cas-number>, <description>.

It’s acceptable if:

The generated HTML becomes richer and more structured (e.g. multiple paragraphs instead of one long <p>), as long as it still works as the “description” for the product page.

13. Deliverables

Rewrite and improve the code so that:

The monolithic junior script becomes a clean, modular, production-ready pipeline.

The prompting and description logic are upgraded, yielding:

Higher-quality, more structured, more useful descriptions.

Better summaries for previews/search.

The whole thing is:

Configurable

Robust

Test-friendly

Maintainable by a senior developer.

Apply all changes directly to the repository containing /mnt/data/drugbank_to_html_2_beta.py, creating new modules/files as needed and updating imports accordingly.

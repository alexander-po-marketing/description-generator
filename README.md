Purpose of the Script

drugbank_to_html_2_beta


The script is an automated DrugBank → Pharmaoffer HTML generator.

It takes a DrugBank XML dump, extracts selected fields (name, CAS, pharmacodynamics, MOA, categories, products, etc.), then uses OpenAI models to:

Generate a 250–300-word SEO-optimized API description (HTML <p> block).

Generate a 1–2 sentence pharmaceutical summary.

Build structured HTML blocks (Identification, Pharmacology, Taxonomy, References).

Export everything into:

database.json — raw parsed drug data.

api_descriptions.json — final HTML output.

api_descriptions.xml — XML version.

Separate text logs of prompts for debugging.

This script is meant for automatically generating full API product-page content for Pharmaoffer.

High-Level Flow (Simple Version)

Load DrugBank XML
Parse using lxml.etree.

Extract only the needed drugs
Controlled by valid_drugs = {"DB13928"}.
You can expand this to process hundreds of APIs.

Extract specific fields
Using desired_fields. The parser also includes custom logic for:

groups

classification

products (first 5)

international brands

categories

general references

external links

Save raw extracted data → database.json

For each drug:

Build a structured prompt

Call OpenAI GPT-5.1 → generate description

Call GPT-5-mini → generate summary

Build the final HTML with multiple sections

Clean it up (remove bracketed refs)

Save final output
→ JSON & XML.

Detailed “What Each Part Does” (Codex-Friendly)
1. Config + OpenAI Client Setup

Holds API keys, org, project.
Codex could abstract this into env vars.

2. Field Definitions

valid_drugs → restrict which DrugBank IDs to process.
desired_fields → whitelist of XML fields to extract.

Codex could convert this into config files.

3. parse_drugbank_xml() — Extracts clean drug data

Reads the XML, isolates <drug> nodes, and builds a Python dict.

Special logic for nested structures:

<groups><group>…

<classification><class-level>

<international-brands>

<categories>

<products> (takes only up to 5 names)

<general-references> → cleans citations

<external-links> → maps titles + URLs

Output:
{ "DB13928": { "name": "...", "indication": "...", ... } }

4. Prompt Builders

generate_prompt(drug_info)
Creates a structured OpenAI prompt using extracted fields.

save_prompt_to_file()
Logs prompts for debugging.

5. OpenAI Description Generation

generate_description()
Calls gpt-5.1 with:

Developer message: persona (PhD pharma scientist)

User message: structured field list

Generates:

250–300 word <p> description

Retries up to 3 times.

6. Summary Generation

generate_summary()
Calls gpt-5-mini to create a punchy 1–2 sentence summary.

7. HTML Block Builders

Identification

Pharmacology

Chemical taxonomy

General references table

External links table

These convert the structured drug data into proper HTML <section> blocks.

Codex could rewrite this into components or templates.

8. Final HTML Assembly

generate_final_html() merges:

Main description

Summary

Identification, Taxonomy, Pharmacology

References

External links

Then strips bracket annotations (DrugBank references).
Returns full HTML ready for publishing.

9. Exporters

generate_xml_output()
Creates <drugs><drug><name>…</name><description>…</description></drug></drugs>.

The script also writes:

database.json

api_descriptions.json

10. CLI Entry Point: main()

Asks user for XML file path

Parses XML

Generates JSON, HTML, XML

Prints progress through tqdm

Codex could remove CLI input and replace with function arguments.

Why This Script Exists

It solves the full pipeline of turning raw DrugBank XML into ready-to-publish Pharmaoffer API pages automatically.

Instead of manually writing 300-word scientific descriptions for hundreds of APIs, this system:

auto-extracts data

auto-generates expert descriptions

auto-generates summaries

auto-generates structured HTML

auto-saves everything to JSON/XML for CMS ingestion

Basically: DrugBank → AI → final product page content.

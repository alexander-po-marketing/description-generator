"""Generate filter-intent overlays for API descriptions using OpenAI."""

from __future__ import annotations

import html
import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)

FILTER_LABELS = {
    "gmp": "GMP-certified",
    "cep": "with CEP available",
    "wc": "with Written Confirmation (WC)",
    "fda": "with US FDA-facing documentation",
    "coa": "with CoA provided for each batch",
    "iso9001": "with ISO 9001-certified quality systems",
    "usdmf": "with US DMF filed",
    "origin_country:IN": "Verified API manufacturers in India",
    "origin_country:CN": "Verified API manufacturers in China",
    "origin_country:US": "Verified American API manufacturers (United States)",
    "origin_country:JP": "Verified API manufacturers in Japan",
    "origin_country:KR": "Verified API manufacturers in South Korea",
    "origin_region:ASIA": "Produced in Asia",
    "origin_region:EUROPE": "Produced in Europe (EU)",
    "origin_region:NORTH_AMERICA": "Produced in North America",
    "origin_region:SOUTH_AMERICA": "Produced in South America",
}

FILTER_EXPLAINERS = {
    "gmp": "Suppliers that report manufacturing under Good Manufacturing Practice (GMP) and can provide GMP certificates or audit documentation.",
    "cep": "APIs for which a Certificate of Suitability (CEP) is reported, indicating compliance with the relevant Ph. Eur. monograph.",
    "wc": "Suppliers that can provide Written Confirmation (WC) for export to the EU, according to applicable guidelines.",
    "fda": "Suppliers linked to US FDA-regulated markets, typically through US DMF filings or FDA-registered facilities. Do not state that the finished product is FDA-approved.",
    "coa": "Suppliers that provide a Certificate of Analysis (CoA) for each batch of the API, detailing assay, impurities and key quality parameters.",
    "iso9001": "Suppliers whose quality management systems are certified according to ISO 9001.",
    "usdmf": "APIs for which a US Drug Master File (US DMF) has been filed by at least one supplier.",
    "origin_country:IN": "APIs manufactured by suppliers from India; buyers typically focus on EU/US GMP history, DMF availability, audit readiness, and predictable export logistics when sourcing from Indian production sites.",
    "origin_country:CN": "APIs manufactured by suppliers from China; procurement teams pay close attention to regulatory transparency, DMF status, inspection history, and international shipping reliability when evaluating Chinese manufacturers.",
    "origin_country:US": "APIs manufactured by suppliers from United States; buyers prioritize strong FDA compliance records, domestic supply security, and simplified logistics for US-origin material.",
    "origin_country:JP": "APIs manufactured by suppliers from Japan; sourcing teams evaluate strict quality standards, regulatory rigor, long-term supply reliability, and typically higher cost structures associated with Japanese production.",
    "origin_country:KR": "APIs manufactured by suppliers from South Korea; buyers assess regulatory compliance, technological capabilities, export readiness, and consistency of supply from Korean manufacturing sites.",
    "origin_region:ASIA": "APIs manufactured across Asia; procurement teams compare regulatory maturity, audit history, cost structures, and international logistics across multiple Asian production hubs.",
    "origin_region:EUROPE": "APIs manufactured in Europe; buyers align sourcing decisions around EMA compliance, high quality expectations, shorter lead times within the EU, and stable regulatory environments.",
    "origin_region:NORTH_AMERICA": "APIs manufactured in North America; sourcing teams emphasize regulatory trust, supply chain resilience, and streamlined logistics for regional production.",
    "origin_region:SOUTH_AMERICA": "APIs manufactured in South America; procurement teams assess regulatory alignment, export experience, lead times, and freight complexity when sourcing from regional manufacturers."
}

ORIGIN_COUNTRY_LABELS: dict[str, str] = {
    "IN": "India",
    "CN": "China",
    "US": "United States",
    "JP": "Japan",
    "KR": "South Korea",
}

ORIGIN_REGION_LABELS: dict[str, str] = {
    "ASIA": "Asia",
    "EUROPE": "Europe",
    "NORTH_AMERICA": "North America",
    "SOUTH_AMERICA": "South America",
}

ORIGIN_COUNTRY_BACKGROUND: dict[str, str] = {
    "IN": (
        "India is a primary global source for API raw materials and finished APIs, offering scale, cost efficiency, and broad regulatory coverage.\n"
        "Buyers typically evaluate documentation depth (CoA, GMP, DMF) alongside raw material traceability.\n"
        "Logistics planning—especially port selection and incoterms—is often addressed upfront to manage lead-time variability."
    ),
    "CN": (
        "China combines scale and chemical depth in API and intermediate production, making it a key sourcing region globally..\n"
        "Buyers assess regulatory transparency, documentation depth, and material traceability as part of qualification.\n"
        "Logistics and customs planning are typically coordinated early to ensure predictable lead times."
    ),
    "US": (
        "US-based API production offers regulatory confidence and high supply chain transparency.\n"
        "Buyers focus on GMP evidence, FDA inspection outcomes, and documentation readiness.\n"
        "Shorter logistics cycles are common, though quality release and compliance reviews still govern delivery timelines."
    ),
    "JP": (
        "Japanese API production is valued for consistency, documentation discipline, and process reliability.\n"
        "Buyers assess certification completeness and data transparency early in qualification.\n"
        "Audit coordination and assessment planning are commonly built into sourcing timelines."
    ),
    "KR": (
        "Korean API production combines regulatory alignment with modern manufacturing capabilities.\n"
        "Buyers focus on GMP adherence, batch traceability, and documentation completeness.\n"
        "Logistics planning may factor in route reliability and cold-chain handling depending on the product."
    ),
}

ORIGIN_REGION_BACKGROUND: dict[str, str] = {
    "ASIA": (
        "Asian API sourcing offers scale and cost advantages alongside varied regulatory environments.\n"
        "Buyers assess qualification rigor, documentation depth, and logistics reliability on a country-by-country basis.\n"
        "GMP compliance, CoA validation, and supply chain traceability remain baseline requirements across the region."
    ),
    "EUROPE": (
        "European API production generally operates within EU GMP frameworks, supported by mature quality systems and regulatory oversight.\n"
        "Procurement teams review site credentials, CoA consistency, and applicable certificates such as CEPs where relevant to the product.\n"
        "Regional logistics often enable shorter and more predictable lead times into European markets."
    ),
    "NORTH_AMERICA": (
        "North American API manufacturing serves regulated markets with well-documented quality and compliance controls.\n"
        "Buyers typically assess GMP status, inspection histories, and DMF or CEP availability where applicable.\n"
        "Lead times and shipping routes may differ between the US and Canada but are generally characterized by stable and predictable transit."
    ),
    "SOUTH_AMERICA": (
        "South America hosts a mix of domestic-focused and export-oriented API manufacturing sites across several countries.\n"
        "Procurement workflows emphasize verification of documentation readiness, regulatory alignment, and supply continuity.\n"
        "Freight planning and customs coordination are usually addressed early to align delivery schedules with local production cycles."
    ),
}

FILTER_BLOCK_TEXT = {
    "gmp": """<h3>API_NAME GMP</h3><p>GMP (Good Manufacturing Practice) for a API_NAME API manufacturer refers to the set of regulatory standards that ensure the API is produced consistently, safely, and with controlled quality. GMP requirements cover the entire manufacturing lifecycle, from raw materials to final release, and are mandatory for producing APIs that will be used in regulated pharmaceutical markets.</p><p>In the sourcing process, GMP compliance is one of the first qualifications buyers look for, because it directly reflects the quality and reliability of the manufacturing site.</p><p>GMP expectations for a API_NAME API facility include:</p><ul><li><p>Documented and validated manufacturing processes</p></li><li><p>Controlled environments, equipment calibration, and preventive maintenance</p></li><li><p>Well-defined procedures for testing, sampling, and batch release</p></li><li><p>Trained personnel and clear quality responsibilities</p></li><li><p>Proper handling, storage, and traceability of materials</p></li><li><p>Robust deviation, change control, and CAPA systems</p></li><li><p>Regular internal and external audits</p></li></ul><p>GMP can be demonstrated through:</p><ul><li><p>EU GMP certificates</p></li><li><p>US FDA inspection history</p></li><li><p>National regulatory authority GMP certificates (e.g., NMPA, CDSCO, PMDA)</p></li><li><p>Written Confirmation (for EU imports)</p></li></ul><p>From a sourcing perspective, GMP compliance:</p><ul><li><p>Shows that the API is produced under globally recognized quality standards</p></li><li><p>Reduces regulatory risk and audit findings</p></li><li><p>Increases confidence when comparing API_NAME suppliers for qualification or long-term supply</p></li></ul><p>GMP is one of the core foundations of API quality and is usually a mandatory requirement when selecting a API_NAME manufacturer.</p>""",
    "cep": """<h3>API_NAME CEP available</h3><p>A Certificate of Suitability (CEP) for API_NAME is an official document issued by the EDQM (European Directorate for the Quality of Medicines &amp; HealthCare) confirming that the API_NAME API complies with the relevant monograph in the European Pharmacopoeia (Ph. Eur.). In the sourcing process, a CEP is a strong indicator that the API manufacturer&rsquo;s quality, purity, and impurity profile have been independently reviewed and accepted by a European authority.</p><p>For API_NAME and other APIs, a CEP typically covers:</p><ul><li><p>Confirmation that the API quality is in line with the Ph. Eur. monograph</p></li><li><p>Details on impurities and residual solvents, including how they are controlled</p></li><li><p>Information on the manufacturing process and controls (to the extent needed to assess compliance)</p></li><li><p>References to the approved specifications, analytical methods, and quality standards</p></li></ul><p>A CEP is not a marketing authorization, but it simplifies regulatory submissions in Europe (and many other markets that recognize CEPs). Finished dosage form manufacturers can reference the CEP in their dossiers instead of submitting full API data themselves, which speeds up registration and reduces duplication of technical work.</p><p>From a sourcing perspective, a API_NAME CEP:</p><ul><li><p>Demonstrates that the API and its control strategy have passed a central, independent assessment</p></li><li><p>Reduces the regulatory burden for buyers registering products in CEP-recognizing markets</p></li><li><p>Serves as a strong credential when comparing multiple API_NAME suppliers</p></li></ul><p>The underlying technical dossier submitted to EDQM remains confidential, protecting the manufacturer&rsquo;s process know-how while providing regulators and buyers with confidence in the consistency and quality of the API_NAME API.</p>""",
    "wc": """<h3>API_NAME WC (Written&nbsp;confirmation)</h3><p>A Written Confirmation (WC) for API_NAME is an official document issued by the regulatory authority of the manufacturing country to confirm that the API is produced in compliance with EU Good Manufacturing Practice (GMP) standards. It is required for APIs manufactured outside the European Union that are intended for import into the EU.</p><p>In the sourcing process, a Written Confirmation is often requested by buyers to ensure that the API_NAME API comes from a GMP-compliant facility and can be legally imported into the EU.</p><p>A Written Confirmation typically includes:</p><ul><li><p>Confirmation that the manufacturing site operates according to standards equivalent to EU GMP</p></li><li><p>Details of the manufacturing site, including address and inspection history</p></li><li><p>The specific API covered by the document (e.g., API_NAME)</p></li><li><p>The validity period and issuing authority</p></li></ul><p>A WC is not a full regulatory dossier. Instead, it is an assurance from the manufacturer&rsquo;s national authority that the facility meets the GMP level required for EU import. Without a valid Written Confirmation or an EU GMP certificate, EU importers cannot legally bring the API into the European market.</p><p>From a sourcing standpoint, a API_NAME Written Confirmation:</p><ul><li><p>Helps buyers verify that the manufacturing site is GMP-aligned</p></li><li><p>Simplifies importation into EU markets</p></li><li><p>Provides added regulatory confidence when comparing suppliers</p></li></ul><p>It complements other regulatory documents such as DMFs and CEPs by focusing specifically on GMP compliance for export to the European Union.</p>""",
    "fda": """<h3>API_NAME US FDA</h3><p>US FDA-facing documentation for API_NAME refers to the set of regulatory and quality documents that demonstrate an API manufacturer&rsquo;s compliance with US Food and Drug Administration requirements. When sourcing API_NAME for products intended for the US market, buyers often evaluate these documents to ensure the API can be used in FDA-regulated applications.</p><p>The most common FDA-facing documents include:</p><ul><li><p><strong>USDMF (Drug Master File)</strong><br /> A confidential dossier describing the API_NAME manufacturing process, controls, specifications, and stability data. It allows finished dosage form manufacturers to reference the API information in their own FDA submissions.</p></li><li><p><strong>GMP inspection history or Establishment Inspection Reports (if available to the manufacturer)</strong><br /> Evidence that the facility has been inspected by the FDA and operates in compliance with US GMP requirements. Some manufacturers hold FDA registration and have undergone successful inspections.</p></li><li><p><strong>Facility FEI and DUNS numbers</strong><br /> Identifiers used by the FDA to track establishments involved in drug manufacturing.</p></li><li><p><strong>Letter of Authorization (LOA)</strong><br /> Issued by the API manufacturer, allowing a specific customer to reference their USDMF in an FDA application.</p></li></ul><p>US FDA-facing documentation is not a single certificate but rather a combination of regulatory credentials and compliance evidence. For buyers, these documents:</p><ul><li><p>Confirm that the API is produced under conditions acceptable to the FDA</p></li><li><p>Enable smooth regulatory submissions for finished dosage forms</p></li><li><p>Provide confidence when selecting a supplier for US-bound products</p></li></ul><p>In the sourcing workflow, these credentials help differentiate suppliers that meet US regulatory expectations from those focused on non-US markets.</p>""",
    "coa": """<p><h3>API_NAME CoA</h3>A Certificate of Analysis (CoA) for API_NAME is a quality document issued for a specific production batch of the API. It lists the results of all tests performed on that batch and confirms that the material meets the agreed specifications, often aligned with major pharmacopeias such as USP, BP, or Ph. Eur.</p><p>During the sourcing process, the CoA is one of the most important documents buyers review, because it provides real, batch-specific evidence of product quality.</p><p>A API_NAME CoA typically includes:</p><ul><li><p>Batch number and manufacturing date</p></li><li><p>Specifications and test results (assay, impurities, physical characteristics, etc.)</p></li><li><p>Reference standards used (USP, BP, Ph. Eur., in-house)</p></li><li><p>Analytical methods or method references</p></li><li><p>Storage conditions and retest or expiry date</p></li><li><p>Name and address of the manufacturing site</p></li><li><p>Quality unit signatures and approval date</p></li></ul><p>Unlike regulatory dossiers (such as DMFs or CEPs), a CoA is not a long-term qualification document. It is tied to each individual batch and verifies that the delivered material conforms to quality requirements.</p><p>From a sourcing perspective, a API_NAME CoA:</p><ul><li><p>Confirms that the batch being supplied meets specifications</p></li><li><p>Allows buyers to compare quality parameters across different suppliers</p></li><li><p>Helps ensure consistency and compliance in downstream formulation and registration work</p></li></ul><p>A valid, properly issued CoA is essential for QA review, release, and audit readiness when purchasing API_NAME API.</p>""",
    "iso9001": """<h3>API_NAME ISO 9001-certified</h3><p>ISO 9001 for a API_NAME API manufacturer is a certification that confirms the company has a well-structured quality management system (QMS) in place. It is not specific to pharmaceuticals, but it demonstrates that the organization follows internationally recognized quality management principles, including documentation control, continuous improvement, and customer focus.</p><p>In the sourcing process, ISO 9001 is often viewed as a supporting credential that shows a supplier has mature internal processes, even though it does not replace GMP or other pharma-specific regulatory requirements.</p><p>An ISO 9001 certification typically covers:</p><ul><li><p>How the company manages quality procedures and documentation</p></li><li><p>Roles and responsibilities within the quality system</p></li><li><p>Corrective and preventive action processes</p></li><li><p>Risk management and continuous improvement programs</p></li><li><p>Internal audits and management review practices</p></li></ul><p>For buyers evaluating API_NAME suppliers, ISO 9001 provides:</p><ul><li><p>Assurance that the manufacturer has standardized, repeatable processes</p></li><li><p>Evidence of organizational quality culture beyond basic compliance</p></li><li><p>Additional confidence when onboarding or prequalifying new suppliers</p></li></ul><p>While ISO 9001 is not a regulatory requirement for API production, it complements pharma-specific documentation (DMF, CEP, GMP certificates, CoA) by demonstrating broader quality management capability within the organization.</p>""",
    "usdmf": """<h3>API_NAME USDMF</h3><p>A Drug Master File (DMF) for API_NAME is a confidential technical dossier that describes in detail how the API_NAME active pharmaceutical ingredient (API) is manufactured, controlled, packaged, and stored. In the sourcing process, a DMF is one of the key documents buyers look at to assess whether an API manufacturer has robust quality and regulatory documentation in place.</p><p>Because regulations differ between regions, API_NAME DMFs can be registered in several formats, for example:</p><ul><li><p>USDMF for submissions to the US FDA</p></li><li><p>ASMF (formerly EDMF) for Europe</p></li><li><p>JDMF for Japan</p></li><li><p>CDMF for China</p></li></ul><p>A API_NAME USDMF submitted to the US FDA typically includes:</p><ul><li><p>Detailed information on API_NAME's chemical characteristics and specifications</p></li><li><p>A description of the manufacturing process and in-process controls</p></li><li><p>Information on the production facilities and quality systems</p></li><li><p>Data on packaging, stability, and storage conditions</p></li></ul><p>The DMF itself is not a marketing authorization, but it allows a finished dosage form manufacturer to reference the file in their own regulatory submission without accessing the supplier's proprietary know-how. The content of the DMF is kept confidential by the health authority, which protects the API manufacturer's intellectual property while still giving regulators full insight into the quality and consistency of the API_NAME API.</p>""",
}


class FilteredIntentError(RuntimeError):
    """Raised when filter intent generation fails."""


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"Environment variable {key} is required for OpenAI access.")
    return value


def _is_origin_country(filter_key: str) -> bool:
    return filter_key.startswith("origin_country:")


def _is_origin_region(filter_key: str) -> bool:
    return filter_key.startswith("origin_region:")


def _is_origin_filter(filter_key: str) -> bool:
    return _is_origin_country(filter_key) or _is_origin_region(filter_key)


def _origin_label_from_key(filter_key: str) -> tuple[str | None, str | None]:
    if _is_origin_country(filter_key):
        _, _, code = filter_key.partition(":")
        return ORIGIN_COUNTRY_LABELS.get(code), code
    if _is_origin_region(filter_key):
        _, _, region = filter_key.partition(":")
        return ORIGIN_REGION_LABELS.get(region), region
    return None, None


def _build_origin_filter_prompt(
    api_name: str, origin_label: str, origin_type: str, origin_background_text: str
) -> str:
    return f"""
Write a sourcing note for procurement teams evaluating suppliers of {api_name} API.

Produce ONE plain-text paragraph of 3–5 sentences.
Explain why buyers filter suppliers by production {origin_type} ({origin_label}) and how this origin choice influences sourcing and procurement workflows.

Guidelines:
- Explain the practical reasons buyers look for {api_name} API from this {origin_type}, and when possible, include API-specific sourcing or supply-chain considerations that are characteristic for this country or region (only if commonly known or logically implied; do not invent facts).
- Describe how origin affects supplier qualification and due-diligence steps, including documentation review (such as CoA, GMP evidence, DMF or CEP where relevant), without assuming availability unless explicitly stated by the filter.
- Mention typical considerations for material traceability, audits or remote assessments, and lead-time or freight planning, adapted to this origin.
- Note that filtering by origin may narrow the available supplier set compared to global sourcing, without using numbers or unverifiable claims.
- Keep the tone factual, neutral, and procurement-oriented; avoid stereotypes, politics, marketing language, or medical guidance.
- Do not modify, repeat, or reinterpret the base API description.

Context for reference only (do not quote or closely paraphrase):
{origin_background_text}

Return only the paragraph in plain text. No formatting, headings, or lists.
""".strip()


def generate_filter_intent_text(api_name: str, filter_key: str, client: OpenAI) -> str:
    """Generate a short, qualification-focused sourcing paragraph for the hero block."""

    if filter_key not in FILTER_LABELS:
        raise ValueError(f"Unknown filter key '{filter_key}'. Expected one of: {', '.join(FILTER_LABELS)}")

    if _is_origin_filter(filter_key):
        origin_label, origin_token = _origin_label_from_key(filter_key)
        if not origin_label or not origin_token:
            raise ValueError(f"Unknown origin filter key '{filter_key}'")

        origin_type = "country" if _is_origin_country(filter_key) else "region"
        background_lookup = (
            ORIGIN_COUNTRY_BACKGROUND if _is_origin_country(filter_key) else ORIGIN_REGION_BACKGROUND
        )
        origin_background_text = background_lookup.get(origin_token, "")
        prompt = _build_origin_filter_prompt(
            api_name=api_name,
            origin_label=origin_label,
            origin_type=origin_type,
            origin_background_text=origin_background_text,
        )

        completion = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.1-chat-latest"),
            messages=[
                {
                    "role": "developer",
                    "content": (
                        "Write a concise sourcing overview for the specified origin."
                        " Keep it procurement-focused and avoid clinical claims."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=220,
        )
        content = (completion.choices[0].message.content or "").strip()
        if not content:
            return (
                "This view highlights {api_name} API suppliers with production origin in {origin_label}. "
                "Buyers use origin filters to align sourcing with qualification and logistics constraints. "
                "Confirm documentation such as CoA and relevant quality/regulatory files early in the process, as availability can differ by origin."
            ).format(api_name=api_name, origin_label=origin_label)
        return content

    filter_label = FILTER_LABELS[filter_key]
    template = FILTER_BLOCK_TEXT.get(filter_key)
    if not template:
        raise ValueError(f"Unknown filter key '{filter_key}'. Expected one of: {', '.join(FILTER_BLOCK_TEXT)}")
    filter_background = template.replace("API_NAME", api_name)

    prompt = f"""
You are a senior pharmaceutical API B2B content writer.

Task:
You will receive:

An API name,

A sourcing qualification used by the buyer,

A background text describing what this qualification means.

Write ONE short paragraph (3–5 sentences) that explains, for {api_name} API:

how the "{filter_label}" qualification changes the sourcing context,

what documentation and quality signals buyers typically expect under this qualification,

how this filter affects supplier selection, documentation review, or market availability.

Focus only on sourcing, regulatory and quality aspects.
Do NOT provide medical advice or treatment recommendations.
Do NOT claim that finished products are approved by any authority; stay at the API/supplier level.
Return ONLY the paragraph as plain text (no JSON, no bullet points).

API name: {api_name}
Qualification label: {filter_label}

Qualification background:
{filter_background}
""".strip()

    completion = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.1-chat-latest"),
        messages=[
            {
                "role": "developer",
                "content": (
                    "Provide a single sourcing-focused paragraph for the specified qualification. Keep it concise and avoid clinical advice."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    content = (completion.choices[0].message.content or "").strip()
    if not content:
        raise FilteredIntentError("Model returned empty content for filter intent text.")

    return content


def _normalize_page(page: Mapping[str, Any]) -> Mapping[str, Any]:
    if "raw" in page and isinstance(page.get("raw"), Mapping):
        return page["raw"]  # type: ignore[return-value]
    return page


def _stringify(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        flattened: List[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            flattened.append(text)
        return ", ".join(flattened) if flattened else None
    if isinstance(value, Mapping):
        return "; ".join(f"{k}: {v}" for k, v in value.items() if v)
    text = str(value).strip()
    return text or None


def _clean_title(value: object) -> Optional[str]:
    text = _stringify(value)
    if not text:
        return None
    return text.split("|")[0].strip()


def _format_paragraph_html(text: str) -> str:
    escaped = html.escape(text.strip())
    return f"<p>{escaped}</p>" if escaped else ""


def _extract_api_fields(page: Mapping[str, Any]) -> Tuple[str | None, str | None]:
    normalized = _normalize_page(page)
    api_name: str | None = None
    if isinstance(normalized, Mapping):
        hero = normalized.get("hero")
        if isinstance(hero, Mapping):
            api_name = _clean_title(hero.get("title")) or _stringify(hero.get("genericName"))
        if not api_name:
            api_name = _clean_title(normalized.get("name")) or _stringify(normalized.get("api_name"))

    original_description: str | None = None
    clinical_overview = normalized.get("clinicalOverview") if isinstance(normalized, Mapping) else None
    if isinstance(clinical_overview, Mapping):
        long_desc = clinical_overview.get("longDescription")
        if isinstance(long_desc, str):
            original_description = long_desc
    if not original_description and isinstance(normalized, Mapping):
        overview = normalized.get("overview")
        if isinstance(overview, Mapping):
            desc = overview.get("description")
            if isinstance(desc, str):
                original_description = desc

    return api_name, original_description


def _update_seo_metadata(
    page: MutableMapping[str, Any], api_name: Optional[str], filter_key: str
) -> None:
    if not api_name:
        return

    label = FILTER_LABELS.get(filter_key)
    explainer = FILTER_EXPLAINERS.get(filter_key)
    if not label or not explainer:
        return

    seo_title = f"{api_name} API suppliers - {label}"
    meta_description = f"Find {api_name} API manufacturers. {explainer}"

    seo = page.get("seo")
    if not isinstance(seo, MutableMapping):
        seo = {}
        page["seo"] = seo
    seo["title"] = seo_title
    seo["metaDescription"] = meta_description

    blocks = page.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, MutableMapping) or block.get("id") != "seo":
                continue
            value = block.get("value")
            if not isinstance(value, MutableMapping):
                value = {}
                block["value"] = value
            value["Title"] = seo_title
            value["Meta description"] = meta_description


def _iter_pages(data: Any) -> Iterable[tuple[Any, MutableMapping[str, Any]]]:
    if isinstance(data, list):
        for index, item in enumerate(data):
            if isinstance(item, MutableMapping):
                yield index, item
    elif isinstance(data, MutableMapping):
        for key, value in data.items():
            if isinstance(value, MutableMapping):
                yield key, value


def generate_filter_text(api_name: str, filter_key: str) -> str:
    template = FILTER_BLOCK_TEXT.get(filter_key)
    if not template:
        raise ValueError(f"Unknown filter key '{filter_key}'. Expected one of: {', '.join(FILTER_BLOCK_TEXT)}")
    html_block = template.replace("API_NAME", api_name)
    return html_block


def apply_filtered_intent_to_file(
    input_path: str,
    output_path: str,
    filter_key: str,
) -> None:
    """Apply filter-intent hero content to every entry in a JSON file."""

    if filter_key not in FILTER_LABELS:
        raise ValueError(f"Unknown filter key '{filter_key}'. Expected one of: {', '.join(FILTER_LABELS)}")

    input_file = Path(input_path)
    output_file = Path(output_path)
    with input_file.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    client = OpenAI(api_key=_require_env("OPENAI_API_KEY"))

    mutated = False
    for key, page in _iter_pages(data):
        normalized_page = _normalize_page(page)
        if not isinstance(normalized_page, MutableMapping):
            logger.warning("Skipping item %s because page structure is not a mapping.", key)
            continue

        api_name, _ = _extract_api_fields(page)
        if not api_name:
            logger.warning("Skipping item %s because API name is missing.", key)
            continue

        logger.info("Applying filter '%s' to %s", filter_key, api_name)
        filter_intent_text = generate_filter_intent_text(api_name=api_name, filter_key=filter_key, client=client)

        if _is_origin_filter(filter_key):
            filter_block_text = _format_paragraph_html(filter_intent_text)
            origin_label, _ = _origin_label_from_key(filter_key)
            origin_label = origin_label or FILTER_LABELS[filter_key]
            if _is_origin_country(filter_key):
                filter_intent_title = f"{api_name} API suppliers from {origin_label}"
            else:
                filter_intent_title = f"{api_name} API suppliers - produced in {origin_label}"
        else:
            filter_block_text = generate_filter_text(api_name, filter_key)
            filter_intent_title = f"{api_name} API manufacturers: {FILTER_LABELS[filter_key]}"

        hero = normalized_page.get("hero")
        if not isinstance(hero, MutableMapping):
            logger.warning("Skipping item %s because hero block is missing.", key)
            continue

        filter_intent = hero.get("filter_intent")
        if not isinstance(filter_intent, dict):
            filter_intent = {}
            hero["filter_intent"] = filter_intent

        filter_intent_entry: MutableMapping[str, Any]
        if _is_origin_filter(filter_key):
            nested = filter_intent.get(filter_key)
            if not isinstance(nested, MutableMapping):
                nested = {}
                filter_intent[filter_key] = nested
            filter_intent_entry = nested
        else:
            filter_intent_entry = filter_intent

        filter_intent_entry["title"] = filter_intent_title
        filter_intent_entry["filter_summary"] = filter_intent_text
        filter_intent_entry["filter_block_text"] = filter_block_text

        if _is_origin_filter(filter_key) and filter_intent_entry is not filter_intent:
            filter_intent.setdefault("title", filter_intent_title)
            filter_intent.setdefault("filter_summary", filter_intent_text)
            filter_intent.setdefault("filter_block_text", filter_block_text)

        if isinstance(page, MutableMapping):
            template = page.get("template")
            if isinstance(template, MutableMapping):
                blocks = template.get("blocks")
                if isinstance(blocks, list):
                    hero_block = next(
                        (block for block in blocks if isinstance(block, MutableMapping) and block.get("id") == "hero"),
                        None,
                    )
                    if hero_block is not None:
                        children = hero_block.get("children")
                        if not isinstance(children, list):
                            children = []
                            hero_block["children"] = children

                        existing_group = next(
                            (
                                child
                                for child in children
                                if isinstance(child, MutableMapping) and child.get("id") == "hero-filter-intent"
                            ),
                            None,
                        )

                        if existing_group is None:
                            children.append(
                                {
                                    "id": "hero-filter-intent",
                                    "label": "Filter intent",
                                    "path": ["filter_intent"],
                                    "type": "group",
                                    "visible": True,
                                    "children": [
                                        {
                                            "id": "hero-filter-intent-title",
                                            "label": "Title",
                                            "path": ["title"],
                                            "type": "field",
                                        },
                                        {
                                            "id": "hero-filter-intent-filter-summary",
                                            "label": "FilterSummary",
                                            "path": ["filter_summary"],
                                            "type": "field",
                                        },
                                        {
                                            "id": "hero-filter-intent-filter-block-text",
                                            "label": "FilterBlockText",
                                            "path": ["filter_block_text"],
                                            "type": "field",
                                        },
                                    ],
                                }
                            )

        if isinstance(page, MutableMapping):
            blocks_list = page.get("blocks")
            if isinstance(blocks_list, list):
                for block in blocks_list:
                    if isinstance(block, MutableMapping) and block.get("id") == "hero":
                        hero_value = block.get("value")
                        if not isinstance(hero_value, MutableMapping):
                            hero_value = {}
                        hero_value["Filter intent"] = {
                            "Title": filter_intent_title,
                            "FilterSummary": filter_intent_text,
                            "FilterBlockText": filter_block_text,
                        }
                        block["value"] = hero_value
                        break

        filter_section = normalized_page.get("filter_section")
        if not isinstance(filter_section, dict):
            filter_section = {}
            normalized_page["filter_section"] = filter_section
        filter_section[filter_key] = filter_block_text

        _update_seo_metadata(normalized_page, api_name, filter_key)
        mutated = True

    if not mutated:
        logger.warning("No items were updated. Check input structure and required fields.")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    import argparse

    parser = argparse.ArgumentParser(description="Post-process API descriptions with filter-specific overlays.")
    parser.add_argument("input", help="Path to input JSON file containing API descriptions")
    parser.add_argument("output", help="Path to write JSON with filtered descriptions")
    parser.add_argument(
        "filter_key",
        choices=sorted(FILTER_LABELS.keys()),
        help="Filter key to apply",
    )
    args = parser.parse_args()

    apply_filtered_intent_to_file(args.input, args.output, args.filter_key)

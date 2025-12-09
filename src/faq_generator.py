"""FAQ generator for existing API page data."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from src.config import OpenAIConfig
from src.openai_client import OpenAIClient

logger = logging.getLogger(__name__)


@dataclass
class FAQTemplate:
    id: str
    question: str
    group: str
    mode: str = "direct"
    answer_template: Optional[str] = None
    context_keys: Sequence[str] = field(default_factory=list)
    tags: Sequence[str] = field(default_factory=list)

    def required_fields(self) -> List[str]:
        fields: List[str] = []
        for text in [self.question, self.answer_template]:
            if not text:
                continue
            for _, field_name, _, _ in Formatter().parse(text):
                if field_name and field_name not in fields:
                    fields.append(field_name)
        return fields


FAQ_TEMPLATES: List[FAQTemplate] = [
    FAQTemplate(
        id="basic_use",
        mode="llm",
        question="What is {drug_name} (CAS {cas}) used for?",
        group="technical",
        context_keys=["hero", "overview", "pharmacology"],
        tags=["indications", "clinical", "high-intent"],
    ),
    
    FAQTemplate(
        id="therapeutic_class",
        mode="direct",
        question="Which therapeutic class does {drug_name} fall into?",
        group="technical",
        answer_template=(
            "{drug_name} belongs to the following therapeutic categories: {therapeutic_categories}. "
            "This positioning helps teams compare alternative APIs, anticipate pharmacology expectations, and align early rese"
            "arch priorities."
        ),
        context_keys=["overview", "pharmacology"],
        tags=["classification", "clinical"],
    ),
    FAQTemplate(
        id="primary_indications",
        mode="direct",
        question="What conditions is {drug_name} mainly prescribed for?",
        group="technical",
        answer_template=(
            "The primary indications for {drug_name}: {primary_indications}. "
            "These use cases frame the target patient populations and help prioritize formulation and safety evaluations."
        ),
        context_keys=["overview"],
        tags=["indications", "clinical"],
    ),
    FAQTemplate(
        id="regions_approved",
        mode="direct",
        question="Where is {drug_name} approved or in use globally?",
        group="regulatory",
        answer_template=(
            "{drug_name} is reported as approved in the following major regions: {regions_approved}. "
            "Understanding geographic coverage informs regulatory filings, supply planning, and risk assessments before escala"
            "ting procurement."
        ),
        context_keys=["regulatory"],
        tags=["regulatory", "markets"],
    ),
    FAQTemplate(
        id="mechanism_of_action",
        mode="direct",
        question="How does {drug_name} work?",
        group="technical",
        context_keys=["pharmacology"],
        tags=["mechanism", "pharmacology"],
    ),
    FAQTemplate(
        id="safety_toxicity",
        mode="llm",
        question="What should someone know about the safety or toxicity profile of {drug_name}?",
        group="technical",
        context_keys=["safety", "overview", "pharmacology"],
        tags=["safety", "toxicity"],
    ),
    FAQTemplate(
        id="formulation_handling",
        mode="llm",
        question="What are important formulation and handling considerations for {drug_name} as an API?",
        group="technical",
        context_keys=["adme", "formulation"],
        tags=["formulation", "handling"],
    ),
    FAQTemplate(
        id="regulatory_patent",
        mode="llm",
        question="What’s the regulatory and patent landscape for {drug_name} right now?",
        group="regulatory",
        context_keys=["regulatory"],
        tags=["regulatory", "patents"],
    ),
    FAQTemplate(
        id="sourcing",
        mode="llm",
        question="What matters most when sourcing GMP-grade {drug_name}?",
        group="sourcing",
        context_keys=["regulatory", "supply"],
        tags=["sourcing", "buyers"],
    ),
    FAQTemplate(
        id="sourcing_documents",
        mode="direct",
        question="Which documents are typically required when sourcing {drug_name} API?",
        group="sourcing",
        answer_template=(
            "Request the core API documentation set: [[sourcing_documents]]. "
            "Confirm versions and validity dates match the destination market to avoid delays in qualification."
        ),
        context_keys=["regulatory", "supply"],
        tags=["sourcing", "documentation"],
    ),
    FAQTemplate(
        id="small_molecule",
        mode="direct",
        question="Is {drug_name} a {drug_type}?",
        group="technical",
        answer_template=(
            "{drug_name} is classified as a {drug_type}. "
            "That classification shapes process design, impurity profiling, and analytical control strategies."
        ),
        context_keys=["identification", "overview"],
        tags=["classification", "chemistry"],
    ),
    FAQTemplate(
        id="stability_concerns",
        mode="llm",
        question="Are there special stability concerns for oral {drug_name}?",
        group="technical",
        context_keys=["formulation", "adme"],
        tags=["formulation", "stability"],
    ),
    FAQTemplate(
        id="patent_expiry",
        mode="direct",
        question="When are the key patents for {drug_name} expected to expire?",
        group="regulatory",
        answer_template=(
            "Patent timelines reported for {drug_name}: {patent_status}. "
            "Use these milestones to inform market entry planning, dossier preparation, and exclusivity risk assessments."
        ),
        context_keys=["regulatory"],
        tags=["regulatory", "patents"],
    ),
    FAQTemplate(
        id="manufacturers",
        mode="direct",
        question="Which manufacturers are known to produce {drug_name} API?",
        group="sourcing",
        answer_template=(
            "Known or reported manufacturers for {drug_name}: [[manufacturers]]. "
            "Evaluate their GMP history, scale, and regional coverage before requesting dossiers or allocating demand."
        ),
        context_keys=["supply"],
        tags=["suppliers", "manufacturing"],
    ),
    FAQTemplate(
        id="quote_requests",
        mode="direct",
        question="How can I request quotes for {drug_name} API from GMP suppliers?",
        group="sourcing",
        answer_template=(
            "Submit quote requests through the supplier listings with your specs and required documents ({quote_guidance}). "
            "Providing consistent details upfront speeds comparable offers and clarifies technical feasibility."
        ),
        context_keys=["supply"],
        tags=["sourcing", "quotes"],
    ),
    FAQTemplate(
        id="smart_sourcing",
        mode="direct",
        question="How does Pharmaoffer’s Smart Sourcing Service help with {drug_name} procurement?",
        group="pharmaoffer",
        answer_template=(
            "Pharmaoffer's Smart Sourcing Service coordinates compliant suppliers, documentation, and competitive quotes for {drug_name}. "
            "It centralizes outreach, follow-ups, and document validation to shorten procurement timelines."
        ),
        context_keys=["supply"],
        tags=["pharmaoffer", "services"],
    ),
    FAQTemplate(
        id="gmp_audit",
        mode="direct",
        question="Is a GMP audit report available for {drug_name} manufacturers?",
        group="sourcing",
        answer_template=(
            "Audit reports may be requested for {drug_name}: [[gmp_audit_reports]]. "
            "Confirm the scope and recency of any audit before relying on it for qualification decisions."
        ),
        context_keys=["supply", "regulatory"],
        tags=["gmp", "audit"],
    ),
    FAQTemplate(
        id="pro_data",
        mode="direct",
        question="Is {drug_name} included in the PRO Data Insights coverage?",
        group="pharmaoffer",
        answer_template=(
            "PRO Data Insights coverage for {drug_name}: [[pro_data_available]]. "
            "Use the dataset to benchmark suppliers and monitor regulatory activity where available."
        ),
        context_keys=["regulatory"],
        tags=["analytics", "pro-data"],
    ),
    FAQTemplate(
        id="market_report",
        mode="direct",
        question="Where can I access the API market report for {drug_name}?",
        group="pharmaoffer",
        answer_template=(
            "Market report availability for {drug_name}: [[market_report_link]]. "
            "The report highlights demand trends, pricing drivers, and supplier landscape insights for procurement planning."
        ),
        context_keys=["regulatory", "supply"],
        tags=["market", "report"],
    ),
    FAQTemplate(
        id="supplier_count",
        mode="direct",
        question="How many suppliers offer {drug_name} API on Pharmaoffer?",
        group="sourcing",
        answer_template=(
            "Reported supplier count for {drug_name}: [[supplier_count]] verified suppliers. "
            "Filter listings by certifications, regions, and delivery options to match your qualification plan."
        ),
        context_keys=["supply"],
        tags=["suppliers", "counts"],
    ),
    FAQTemplate(
        id="producing_countries",
        mode="direct",
        question="Which countries are known to manufacture {drug_name} API?",
        group="sourcing",
        answer_template=(
            "Production countries reported for {drug_name}: [[manufacturer_countries]]. "
            "Knowing the manufacturing geography helps anticipate logistics lead times and import compliance needs."
        ),
        context_keys=["supply"],
        tags=["suppliers", "countries"],
    ),
    FAQTemplate(
        id="gmp_certifications",
        mode="direct",
        question="Which certifications do suppliers of {drug_name} usually hold?",
        group="sourcing",
        answer_template=(
            "Common certifications for {drug_name} suppliers: [[gmp_certifications]]. "
            "Always verify issuing authorities and expiry dates when reviewing audit packages."
        ),
        context_keys=["supply"],
        tags=["gmp", "certifications"],
    ),
    FAQTemplate(
        id="typical_moq",
        mode="direct",
        question="What’s a typical MOQ for {drug_name} API?",
        group="sourcing",
        answer_template=(
            "Typical minimum order quantities (MOQ) for {drug_name}: [[moq_info]]. "
            "Discuss flexibility for pilot, validation, or scale-up batches with suppliers early."
        ),
        context_keys=["supply"],
        tags=["sourcing", "moq"],
    )
]


FIELD_FALLBACKS: Mapping[str, Sequence[str]] = {
    "drug_type": ["molecule_type"],
    "drug_name": ["generic_name"],
    "generic_name": ["drug_name"],
}

ALWAYS_ALLOW_TEMPLATES = {
    "manufacturers",
    "sourcing_documents",
    "quote_requests",
    "smart_sourcing",
    "gmp_audit",
    "pro_data",
    "market_report",
    "supplier_count",
    "producing_countries",
    "gmp_certifications",
    "typical_moq",
}


def _load_json(path: str) -> Mapping[str, object]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise ValueError("Input JSON must be a mapping of ID to page model")
    return data


def _stringify(value: object, *, max_items: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        flattened: List[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            flattened.append(text)
            if max_items is not None and len(flattened) >= max_items:
                break
        return ", ".join(flattened) if flattened else None
    if isinstance(value, Mapping):
        return "; ".join(f"{k}: {v}" for k, v in value.items() if v)
    text = str(value).strip()
    return text or None


def _first_non_empty(*values: object) -> Optional[str]:
    for value in values:
        text = _stringify(value)
        if text:
            return text
    return None


def _clean_title(value: object) -> Optional[str]:
    text = _stringify(value)
    if not text:
        return None
    return text.split("|")[0].strip()


def _extract_market_countries(markets: object) -> Optional[str]:
    if not markets:
        return None
    if isinstance(markets, Mapping):
        markets = markets.values()
    if isinstance(markets, str):
        return _stringify(markets)
    countries: List[str] = []
    if isinstance(markets, Iterable):
        for entry in markets:
            if isinstance(entry, Mapping):
                country = _stringify(entry.get("country"))
            else:
                country = _stringify(entry)
            if not country:
                continue
            countries.append(country)
            if len(countries) >= 50:  # hard stop to avoid runaway lists
                break
    return ", ".join(dict.fromkeys(countries)) if countries else None


def _extract_context(drug_id: str, page: Mapping[str, object]) -> tuple[Dict[str, str], Dict[str, str]]:
    raw = page.get("raw") if isinstance(page, Mapping) else None
    hero = (raw or {}).get("hero") or page.get("hero") or {}
    overview = (raw or {}).get("overview") or page.get("overview") or {}
    pharmacology = (raw or {}).get("pharmacology") or page.get("pharmacology") or {}
    adme = (raw or {}).get("admePk") or page.get("admePk") or {}
    regulatory = (raw or {}).get("regulatoryAndMarket") or page.get("regulatoryAndMarket") or {}
    taxonomy = (raw or {}).get("categoriesAndTaxonomy") or page.get("categoriesAndTaxonomy") or {}
    formulation = (raw or {}).get("formulationNotes") or page.get("formulationNotes") or {}
    supply = (raw or {}).get("suppliersAndManufacturing") or page.get("suppliersAndManufacturing") or {}
    safety = (raw or {}).get("safety") or page.get("safety") or {}
    identification = (raw or {}).get("identification") or page.get("identification") or {}

    facts = hero.get("facts") if isinstance(hero, Mapping) else {}
    markets = regulatory.get("markets") if isinstance(regulatory, Mapping) else None

    context: Dict[str, str] = {}
    context["drug_id"] = drug_id
    context["drug_name"] = _first_non_empty(
        _clean_title(hero.get("title")), _clean_title(facts.get("genericName")), _clean_title(hero.get("name"))
    ) or drug_id
    context["generic_name"] = _first_non_empty(
        _clean_title(facts.get("genericName")), _clean_title(hero.get("title")), _clean_title(hero.get("name"))
    ) or context["drug_name"]
    context["cas"] = _first_non_empty(facts.get("casNumber"), hero.get("cas")) or "Unknown"
    context["therapeutic_categories"] = _first_non_empty(
        _stringify(taxonomy.get("therapeuticClasses"), max_items=5),
        _stringify(taxonomy.get("categories"), max_items=5),
        _stringify(taxonomy.get("drugClasses"), max_items=5),
    )
    context["primary_indications"] = _first_non_empty(page.get("primaryIndications"), hero.get("primaryUseCases"))
    context["regions_approved"] = _extract_market_countries(markets)
    context["half_life"] = _first_non_empty(adme.get("halfLife"), adme.get("pkSnapshot"))
    context["mechanism_of_action"] = _first_non_empty(
        pharmacology.get("mechanismOfAction"), pharmacology.get("summary"), overview.get("summary")
    )
    context["patent_status"] = _first_non_empty(regulatory.get("patentSummary"), regulatory.get("ipStatus"))
    context["manufacturers"] = _first_non_empty(supply.get("manufacturers"), supply.get("suppliers")) or "Not specified"
    context["supplier_count"] = _first_non_empty(supply.get("supplierCount")) or "Not specified"
    context["manufacturer_countries"] = _first_non_empty(
        supply.get("countries"), supply.get("manufacturingCountries"), supply.get("regions")
    ) or "Not specified"
    context["gmp_certifications"] = _first_non_empty(supply.get("gmpCertifications"), supply.get("certifications")) or "Not specified"
    context["gmp_audit_access"] = _first_non_empty(supply.get("auditAvailability"), supply.get("auditReports")) or "Check with supplier"
    context["pro_data_availability"] = _first_non_empty(regulatory.get("proData")) or "Check PRO Data Insights catalogue"
    context["market_report_link"] = _first_non_empty(regulatory.get("marketReport")) or "Market report availability not listed"
    context["quote_guidance"] = "specifications, target volume, delivery timeline, and destination"
    context["sourcing_documents"] = (
        "DMF/ASMF, CEP (if available), GMP certificate, CoA, SDS/MSDS, stability data, and method of analysis"
    )
    context["moq_info"] = _first_non_empty(supply.get("moq"), supply.get("minimumOrder")) or "MOQ varies by supplier"
    context["drug_type"] = _first_non_empty(
        page.get("drug_type"),
        page.get("type"),
        page.get("drugType"),
        page.get("moleculeType"),
        (raw or {}).get("drug_type"),
        (raw or {}).get("type"),
        (raw or {}).get("drugType"),
        hero.get("drugType"),
        hero.get("moleculeType"),
        facts.get("drugType"),
        facts.get("moleculeType"),
        identification.get("moleculeType"),
    )
    context["molecule_type"] = context["drug_type"]

    # Context slices for LLM or fallback answers
    context_slices: Dict[str, str] = {}
    context_slices["hero"] = _first_non_empty(hero.get("summary"), hero.get("summarySentence"), hero.get("title")) or ""
    context_slices["overview"] = _first_non_empty(overview.get("description"), overview.get("summary")) or ""
    context_slices["pharmacology"] = _first_non_empty(
        pharmacology.get("mechanismOfAction"), pharmacology.get("pharmacodynamics"), pharmacology.get("summary")
    ) or ""
    adme_lines = adme.get("pkSnapshot") if isinstance(adme, Mapping) else None
    context_slices["adme"] = _first_non_empty(adme.get("summary"), adme_lines, adme.get("table")) or ""
    context_slices["regulatory"] = _first_non_empty(
        regulatory.get("summary"),
        regulatory.get("ipStatus"),
        regulatory.get("patentSummary"),
        _extract_market_countries(markets),
    ) or ""
    context_slices["formulation"] = _first_non_empty(formulation.get("bullets"), formulation.get("notes")) or ""
    context_slices["supply"] = _first_non_empty(supply.get("supplyChainSummary"), supply.get("manufacturers")) or ""
    context_slices["safety"] = _first_non_empty(safety.get("highLevelWarnings"), safety.get("toxicity")) or ""

    return context, context_slices


def _has_required_fields(template: FAQTemplate, context: Dict[str, str]) -> bool:
    missing = []
    for field in template.required_fields():
        value = context.get(field)
        if value:
            continue

        fallback_value = _first_non_empty(*(context.get(key) for key in FIELD_FALLBACKS.get(field, ())))
        if fallback_value:
            context[field] = fallback_value
            continue

        missing.append(field)
    if missing:
        logger.debug("Skipping template %s due to missing fields: %s", template.id, ", ".join(missing))
        return False
    return True


def _render_direct_answer(template: FAQTemplate, context: Mapping[str, str], context_slices: Mapping[str, str]) -> Optional[str]:
    if template.answer_template:
        return template.answer_template.format(**context)

    if not template.context_keys:
        return None

    parts = [context_slices.get(key, "") for key in template.context_keys]
    merged = " ".join(part for part in parts if part).strip()
    return merged or None


def _build_llm_prompt(question: str, context_slices: Mapping[str, str], context_keys: Sequence[str]) -> str:
    ordered_keys = list(context_keys) if context_keys else ["hero", "overview", "pharmacology", "adme", "regulatory", "safety"]
    lines = []
    for key in ordered_keys:
        value = context_slices.get(key, "")
        if value:
            lines.append(f"- {key.title()}: {value}")
    context_block = "\n".join(lines)
    return (
        "You are an expert pharmaceutical writer creating FAQ answers for active pharmaceutical ingredients. "
        "Use only the provided context and do not mention missing or unavailable information.\n"
        f"Question: {question}\n"
        f"Context:\n{context_block}\n\n"
        "Constraints:\n- Keep responses to 2-4 sentences.\n- Avoid marketing language or speculation.\n- Do not fabricate data."
    )


def _has_context_for_template(
    template: FAQTemplate, context: Mapping[str, str], context_slices: Mapping[str, str]
) -> bool:
    if template.id in ALWAYS_ALLOW_TEMPLATES:
        return True

    if template.mode == "llm":
        if template.id == "regulatory_patent":
            return bool(context.get("patent_status") or context_slices.get("regulatory"))
        if template.id == "stability_concerns":
            return bool(context_slices.get("formulation") or context_slices.get("adme"))
        if template.id == "safety_toxicity":
            return bool(
                context_slices.get("safety")
                or context_slices.get("pharmacology")
                or context_slices.get("overview")
            )
        if template.id == "formulation_handling":
            return bool(context_slices.get("adme") or context_slices.get("formulation"))
        if template.id == "sourcing":
            return bool(context_slices.get("supply") or context_slices.get("regulatory"))
        return any(context_slices.get(key) for key in template.context_keys)

    if template.id == "patent_expiry":
        return bool(context.get("patent_status"))
    if template.id == "therapeutic_class":
        return bool(context.get("therapeutic_categories"))
    if template.id == "primary_indications":
        return bool(context.get("primary_indications"))
    if template.id == "regions_approved":
        return bool(context.get("regions_approved"))
    if template.id == "small_molecule":
        return bool(context.get("drug_type"))

    return True


def _generate_llm_answer(
    template: FAQTemplate,
    question: str,
    context_slices: Mapping[str, str],
    *,
    client: Optional[OpenAIClient],
    model: Optional[str],
) -> Optional[str]:
    if client is None:
        logger.warning("No OpenAI client available; skipping LLM FAQ %s", template.id)
        return None
    prompt = _build_llm_prompt(question, context_slices, template.context_keys)
    return client.generate_text(prompt, model=model)


def generate_faqs_for_page(
    drug_id: str,
    page: Mapping[str, object],
    *,
    templates: Sequence[FAQTemplate],
    client: Optional[OpenAIClient],
    model: Optional[str],
    max_faqs: Optional[int] = None,
) -> List[Dict[str, object]]:
    context, context_slices = _extract_context(drug_id, page)
    faqs: List[Dict[str, object]] = []

    for template in templates:
        if max_faqs is not None and len(faqs) >= max_faqs:
            break
        if not _has_required_fields(template, context):
            continue
        if not _has_context_for_template(template, context, context_slices):
            logger.debug("Skipping FAQ %s for %s due to insufficient context", template.id, drug_id)
            continue

        try:
            question_text = template.question.format(**context)
        except KeyError as exc:
            logger.debug("Missing placeholder %s for question %s", exc, template.id)
            continue

        answer: Optional[str] = None
        if template.mode == "direct":
            answer = _render_direct_answer(template, context, context_slices)
        elif template.mode == "llm":
            answer = _generate_llm_answer(template, question_text, context_slices, client=client, model=model)
        else:
            logger.warning("Unknown FAQ mode %s for template %s", template.mode, template.id)
            continue

        if not answer:
            logger.debug("Skipping FAQ %s for %s due to empty answer", template.id, drug_id)
            continue

        faqs.append(
            {
                "id": template.id,
                "group": template.group,
                "question": question_text,
                "answer": answer.strip(),
                "mode": template.mode,
                "tags": list(template.tags),
            }
        )
    return faqs


def _generate_for_single_page(
    drug_id: str,
    page: Mapping[str, object],
    *,
    templates: Sequence[FAQTemplate],
    client: Optional[OpenAIClient],
    model: Optional[str],
    max_faqs: Optional[int],
) -> tuple[str, List[Dict[str, object]]]:
    if not isinstance(page, Mapping):
        logger.warning("Skipping %s because page entry is not a mapping", drug_id)
        return drug_id, []

    faqs = generate_faqs_for_page(
        drug_id,
        page,
        templates=templates,
        client=client,
        model=model,
        max_faqs=max_faqs,
    )
    return drug_id, faqs


def generate_faqs(
    pages: Mapping[str, object],
    *,
    templates: Sequence[FAQTemplate] = FAQ_TEMPLATES,
    client: Optional[OpenAIClient] = None,
    model: Optional[str] = None,
    max_faqs: Optional[int] = None,
    max_workers: int = 8,
) -> Dict[str, List[Dict[str, object]]]:
    faq_output: Dict[str, List[Dict[str, object]]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_drug_id = {
            executor.submit(
                _generate_for_single_page,
                drug_id,
                page,
                templates=templates,
                client=client,
                model=model,
                max_faqs=max_faqs,
            ): drug_id
            for drug_id, page in pages.items()
        }

        for future in concurrent.futures.as_completed(future_to_drug_id):
            drug_id = future_to_drug_id[future]
            try:
                result_drug_id, faqs = future.result()
            except Exception:
                logger.exception("Failed to generate FAQs for %s", drug_id)
                continue

            if faqs:
                faq_output[result_drug_id] = faqs
    return faq_output


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate FAQs from existing API page models")
    parser.add_argument("--input", default="outputs/api_pages.json", help="Path to structured API pages JSON")
    parser.add_argument("--output", default="outputs/api_faqs.json", help="Output path for generated FAQs")
    parser.add_argument("--max-faqs", type=int, help="Maximum FAQs per drug")
    parser.add_argument("--model", help="Override model for LLM FAQs (defaults to summary model)")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv or [])
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    pages = _load_json(args.input)

    llm_needed = any(template.mode == "llm" for template in FAQ_TEMPLATES)
    client: Optional[OpenAIClient] = None
    if llm_needed:
        try:
            client = OpenAIClient(OpenAIConfig())
        except EnvironmentError as exc:  # pragma: no cover - env dependent
            logger.warning("OpenAI credentials missing; LLM FAQs will be skipped: %s", exc)
            client = None

    faqs = generate_faqs(pages, client=client, model=args.model, max_faqs=args.max_faqs)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(faqs, handle, ensure_ascii=False, indent=2)
    logger.info("Wrote FAQs for %d APIs to %s", len(faqs), output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

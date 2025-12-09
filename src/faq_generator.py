"""FAQ generator for existing API page data."""

from __future__ import annotations

import argparse
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
        mode="direct",
        question="What is {drug_name} (CAS {cas}) used for?",
        context_keys=["hero", "overview"],
        tags=["indications", "clinical", "high-intent"],
    ),
    
    FAQTemplate(
        id="therapeutic_class",
        mode="direct",
        question="Which therapeutic categories does {drug_name} belong to?",
        answer_template="{drug_name} belongs to the following therapeutic categories: {therapeutic_categories}.",
        tags=["classification", "clinical"],
    ),
    FAQTemplate(
        id="primary_indications",
        mode="direct",
        question="What are the primary indications for {drug_name}?",
        answer_template="The primary indications for {drug_name} include: {primary_indications}.",
        tags=["indications", "clinical"],
    ),
    FAQTemplate(
        id="regions_approved",
        mode="direct",
        question="In which major markets is {drug_name} approved?",
        answer_template="{drug_name} is reported as approved in the following major regions: {regions_approved}.",
        tags=["regulatory", "markets"],
    ),
    FAQTemplate(
        id="mechanism_of_action",
        mode="direct",
        question="How does {drug_name} work?",
        context_keys=["pharmacology"],
        tags=["mechanism", "pharmacology"],
    ),
    FAQTemplate(
        id="safety_toxicity",
        mode="llm",
        question="What are the key safety and toxicity considerations for {drug_name}?",
        context_keys=["safety", "overview", "pharmacology"],
        tags=["safety", "toxicity"],
    ),
    FAQTemplate(
        id="formulation_handling",
        mode="llm",
        question="What are important formulation and handling considerations for {drug_name} as an API?",
        context_keys=["adme", "formulation"],
        tags=["formulation", "handling"],
    ),
    FAQTemplate(
        id="regulatory_patent",
        mode="llm",
        question="What is the current regulatory lifecycle and patent situation for {drug_name}?",
        context_keys=["regulatory"],
        tags=["regulatory", "patents"],
    ),
    FAQTemplate(
        id="sourcing",
        mode="llm",
        question="What should buyers consider when sourcing {drug_name} API from GMP manufacturers?",
        context_keys=["regulatory", "supply"],
        tags=["sourcing", "buyers"],
    ),
    FAQTemplate(
        id="fda_approval",
        mode="llm",
        question="Is {drug_name} FDA-approved?",
        context_keys=["regulatory"],
        tags=["regulatory", "markets", "fda"],
    ),
    FAQTemplate(
        id="regions_approved_detail",
        mode="direct",
        question="In which regions is {drug_name} approved?",
        answer_template="{drug_name} is reported as approved in: {regions_approved}.",
        tags=["regulatory", "markets"],
    ),
    FAQTemplate(
        id="sourcing_documents",
        mode="direct",
        question="What documents should I request when sourcing {drug_name} API?",
        answer_template="Request the core API documentation set: {sourcing_documents}.",
        tags=["sourcing", "documentation"],
    ),
    FAQTemplate(
        id="small_molecule",
        mode="llm",
        question="Is {drug_name} a small molecule?",
        context_keys=["pharmacology", "overview", "hero"],
        tags=["classification", "chemistry"],
    ),
    FAQTemplate(
        id="formulation_handling_specific",
        mode="llm",
        question="How should {drug_name} API be handled during formulation?",
        context_keys=["formulation", "adme"],
        tags=["formulation", "handling"],
    ),
    FAQTemplate(
        id="stability_concerns",
        mode="llm",
        question="Are there special stability concerns for oral {drug_name}?",
        context_keys=["formulation", "adme"],
        tags=["formulation", "stability"],
    ),
    FAQTemplate(
        id="patent_expiry",
        mode="direct",
        question="When do {drug_name} patents expire?",
        answer_template="Patent timelines reported for {drug_name}: {patent_status}.",
        tags=["regulatory", "patents"],
    ),
    FAQTemplate(
        id="manufacturers",
        mode="direct",
        question="Who manufactures {drug_name} API?",
        answer_template="Known or reported manufacturers for {drug_name}: {manufacturers}.",
        tags=["suppliers", "manufacturing"],
    ),
    FAQTemplate(
        id="alternative_manufacturers",
        mode="direct",
        question="Are there alternative manufacturers for {drug_name} API?",
        answer_template="Alternate or additional manufacturers for {drug_name}: {manufacturers}.",
        tags=["suppliers", "alternatives"],
    ),
    FAQTemplate(
        id="quote_requests",
        mode="direct",
        question="How can I request quotes for {drug_name} API from GMP suppliers?",
        answer_template="Submit quote requests through the supplier listings with your specs and required documents ({quote_guidance}).",
        tags=["sourcing", "quotes"],
    ),
    FAQTemplate(
        id="smart_sourcing",
        mode="direct",
        question="How does Pharmaoffer’s Smart Sourcing Service help with {drug_name} procurement?",
        answer_template="Pharmaoffer's Smart Sourcing Service can coordinate compliant suppliers, documentation, and competitive quotes for {drug_name}.",
        tags=["pharmaoffer", "services"],
    ),
    FAQTemplate(
        id="gmp_audit",
        mode="direct",
        question="Can I get a GMP audit report for {drug_name} manufacturers?",
        answer_template="Audit reports may be requested from suppliers; availability for {drug_name}: {gmp_audit_access}.",
        tags=["gmp", "audit"],
    ),
    FAQTemplate(
        id="pro_data",
        mode="direct",
        question="Does {drug_name} appear in the PRO Data Insights subscription?",
        answer_template="PRO Data Insights coverage for {drug_name}: {pro_data_availability}.",
        tags=["analytics", "pro-data"],
    ),
    FAQTemplate(
        id="market_report",
        mode="direct",
        question="Where can I download the {drug_name} market report?",
        answer_template="Market report availability for {drug_name}: {market_report_link}.",
        tags=["market", "report"],
    ),
    FAQTemplate(
        id="supplier_count",
        mode="direct",
        question="How many {drug_name} API suppliers are available on Pharmaoffer?",
        answer_template="Reported supplier count for {drug_name}: {supplier_count}.",
        tags=["suppliers", "counts"],
    ),
    FAQTemplate(
        id="producing_countries",
        mode="direct",
        question="Which countries produce {drug_name} API?",
        answer_template="Production countries reported for {drug_name}: {manufacturer_countries}.",
        tags=["suppliers", "countries"],
    ),
    FAQTemplate(
        id="gmp_certifications",
        mode="direct",
        question="Which GMP certifications do {drug_name} suppliers typically hold?",
        answer_template="Common GMP certifications for {drug_name} suppliers: {gmp_certifications}.",
        tags=["gmp", "certifications"],
    ),
    FAQTemplate(
        id="sourcing_docs_generic",
        mode="direct",
        question="What documents are normally required when sourcing {drug_name} for formulation development?",
        answer_template="For formulation development, request: {sourcing_documents}.",
        tags=["sourcing", "documentation"],
    ),
    FAQTemplate(
        id="typical_moq",
        mode="direct",
        question="What is the typical MOQ for {drug_name} API?",
        answer_template="Typical minimum order quantities (MOQ) for {drug_name}: {moq_info}.",
        tags=["sourcing", "moq"],
    ),
]


def _load_json(path: str) -> Mapping[str, object]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise ValueError("Input JSON must be a mapping of ID to page model")
    return data


def _stringify(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        flattened = [str(item) for item in value if str(item).strip()]
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

    facts = hero.get("facts") if isinstance(hero, Mapping) else {}
    markets = regulatory.get("markets") if isinstance(regulatory, Mapping) else None

    context: Dict[str, str] = {}
    context["drug_id"] = drug_id
    context["drug_name"] = _first_non_empty(hero.get("title"), facts.get("genericName"), hero.get("name")) or drug_id
    context["generic_name"] = _first_non_empty(facts.get("genericName"), hero.get("title"), hero.get("name")) or context["drug_name"]
    context["cas"] = _first_non_empty(facts.get("casNumber"), hero.get("cas")) or "Unknown"
    context["therapeutic_categories"] = _first_non_empty(
        taxonomy.get("therapeuticClasses"), taxonomy.get("categories"), taxonomy.get("drugClasses")
    ) or "Not specified"
    context["primary_indications"] = _first_non_empty(page.get("primaryIndications"), hero.get("primaryUseCases")) or "Not specified"
    context["regions_approved"] = _first_non_empty(markets, regulatory.get("approvalStatus")) or "Not specified"
    context["half_life"] = _first_non_empty(adme.get("halfLife"), adme.get("pkSnapshot")) or "Not specified"
    context["mechanism_of_action"] = _first_non_empty(
        pharmacology.get("mechanismOfAction"), pharmacology.get("summary"), overview.get("summary")
    ) or "Not specified"
    context["patent_status"] = _first_non_empty(regulatory.get("patentSummary"), regulatory.get("ipStatus")) or "Not specified"
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

    # Context slices for LLM or fallback answers
    context_slices: Dict[str, str] = {}
    context_slices["hero"] = _first_non_empty(hero.get("summary"), hero.get("summarySentence"), hero.get("title")) or ""
    context_slices["overview"] = _first_non_empty(overview.get("description"), overview.get("summary")) or ""
    context_slices["pharmacology"] = _first_non_empty(
        pharmacology.get("mechanismOfAction"), pharmacology.get("pharmacodynamics"), pharmacology.get("summary")
    ) or ""
    adme_lines = adme.get("pkSnapshot") if isinstance(adme, Mapping) else None
    context_slices["adme"] = _first_non_empty(adme.get("summary"), adme_lines, adme.get("table")) or ""
    context_slices["regulatory"] = _first_non_empty(regulatory.get("summary"), regulatory.get("approvalStatus"), markets) or ""
    context_slices["formulation"] = _first_non_empty(formulation.get("bullets"), formulation.get("notes")) or ""
    context_slices["supply"] = _first_non_empty(supply.get("supplyChainSummary"), supply.get("manufacturers")) or ""
    context_slices["safety"] = _first_non_empty(safety.get("highLevelWarnings"), safety.get("toxicity")) or ""

    return context, context_slices


def _has_required_fields(template: FAQTemplate, context: Mapping[str, str]) -> bool:
    missing = [field for field in template.required_fields() if not context.get(field)]
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
    context_block = "\n".join(lines) if lines else "- No context available"
    return (
        "You are an expert pharmaceutical writer creating FAQ answers for active pharmaceutical ingredients. "
        "Use only the provided context. If details are missing, respond with 'Insufficient data available.'\n"
        f"Question: {question}\n"
        f"Context:\n{context_block}\n\n"
        "Constraints:\n- Keep responses to 2-4 sentences.\n- Avoid marketing language or speculation.\n- Do not fabricate data."
    )


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
                "question": question_text,
                "answer": answer.strip(),
                "mode": template.mode,
                "tags": list(template.tags),
            }
        )
    return faqs


def generate_faqs(
    pages: Mapping[str, object],
    *,
    templates: Sequence[FAQTemplate] = FAQ_TEMPLATES,
    client: Optional[OpenAIClient] = None,
    model: Optional[str] = None,
    max_faqs: Optional[int] = None,
) -> Dict[str, List[Dict[str, object]]]:
    faq_output: Dict[str, List[Dict[str, object]]] = {}
    for drug_id, page in pages.items():
        if not isinstance(page, Mapping):
            logger.warning("Skipping %s because page entry is not a mapping", drug_id)
            continue
        faqs = generate_faqs_for_page(
            drug_id,
            page,
            templates=templates,
            client=client,
            model=model,
            max_faqs=max_faqs,
        )
        if faqs:
            faq_output[drug_id] = faqs
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

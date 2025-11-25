"""DrugBank XML parser."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from lxml import etree

from src.config import PipelineConfig
from src.models import (
    ATCCode,
    ATCLevel,
    Dosage,
    DrugData,
    DrugInteraction,
    GeneralReferences,
    Patent,
    ReferenceArticle,
    RegulatoryLink,
    Product,
    Target,
)

logger = logging.getLogger(__name__)


def _text_or_none(element) -> Optional[str]:
    if element is None:
        return None
    text = "".join(element.itertext()).strip()
    return text or None


def _collect_subtexts(element, tag_name: str) -> List[str]:
    results: List[str] = []
    for child in element:
        if child.tag.split("}")[-1] == tag_name and child.text:
            cleaned = child.text.strip()
            if cleaned:
                results.append(cleaned)
    return results


def _get_first_text(parent, tag_name: str) -> Optional[str]:
    matches = parent.xpath(f"./*[local-name()='{tag_name}']")
    if matches:
        return _text_or_none(matches[0])
    return None


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    return None


def parse_drugbank_xml(config: PipelineConfig) -> Dict[str, DrugData]:
    logger.info("Parsing DrugBank XML from %s", config.xml_path)
    parser = etree.XMLParser(recover=True)
    tree = etree.parse(config.xml_path, parser=parser)
    root = tree.getroot()
    drugs = root.xpath('./*[local-name()="drug"]')

    results: Dict[str, DrugData] = {}
    processed = 0
    for drug in drugs:
        drug_id_elements = drug.xpath('./*[local-name()="drugbank-id"][@primary="true"]')
        if not drug_id_elements:
            continue
        drugbank_id = drug_id_elements[0].text.strip()

        if config.valid_drug_ids and drugbank_id not in config.valid_drug_ids:
            continue
        processed += 1
        if config.max_drugs and processed > config.max_drugs:
            logger.info("Reached max-drugs limit (%s). Stopping early.", config.max_drugs)
            break

        desired_fields = config.desired_fields
        raw_fields: Dict[str, str] = {}

        name = _get_first_text(drug, "name") if (not desired_fields or "name" in desired_fields) else None
        description = _get_first_text(drug, "description") if (not desired_fields or "description" in desired_fields) else None
        cas_number = _get_first_text(drug, "cas-number") if (not desired_fields or "cas-number" in desired_fields) else None
        unii = _get_first_text(drug, "unii") if (not desired_fields or "unii" in desired_fields) else None
        state = _get_first_text(drug, "state") if (not desired_fields or "state" in desired_fields) else None

        average_mass = _to_float(_get_first_text(drug, "average-mass"))
        monoisotopic_mass = _to_float(_get_first_text(drug, "monoisotopic-mass"))

        groups: List[str] = []
        groups_el = drug.xpath('./*[local-name()="groups"]')
        if groups_el:
            groups = _collect_subtexts(groups_el[0], "group")

        categories: List[str] = []
        categories_el = drug.xpath('./*[local-name()="categories"]/*[local-name()="category"]')
        for category in categories_el:
            cat_text = _get_first_text(category, "category") or _text_or_none(category)
            if cat_text:
                categories.append(cat_text)

        classification_data: Dict[str, object] = {}
        classification_el = drug.xpath('./*[local-name()="classification"]')
        if classification_el:
            classification = classification_el[0]
            classification_data = {
                "description": _get_first_text(classification, "description"),
                "direct_parent": _get_first_text(classification, "direct-parent"),
                "kingdom": _get_first_text(classification, "kingdom"),
                "superclass": _get_first_text(classification, "superclass"),
                "class": _get_first_text(classification, "class"),
                "subclass": _get_first_text(classification, "subclass"),
                "alternative_parents": _collect_subtexts(classification, "alternative-parent"),
                "substituents": _collect_subtexts(classification, "substituent"),
            }
            classification_data = {key: value for key, value in classification_data.items() if value}

        food_interactions: List[str] = []
        food_el = drug.xpath('./*[local-name()="food-interactions"]')
        if food_el:
            food_interactions = _collect_subtexts(food_el[0], "food-interaction")

        atc_codes: List[ATCCode] = []
        atc_el = drug.xpath('./*[local-name()="atc-codes"]/*[local-name()="atc-code"]')
        for atc in atc_el:
            code = atc.attrib.get("code")
            levels = []
            for level in atc.xpath('./*[local-name()="level"]'):
                levels.append(
                    ATCLevel(
                        code=level.attrib.get("code"),
                        description=_text_or_none(level),
                    )
                )
            atc_codes.append(ATCCode(code=code, levels=levels))

        dosages: List[Dosage] = []
        dosages_el = drug.xpath('./*[local-name()="dosages"]/*[local-name()="dosage"]')
        for dosage in dosages_el:
            dosages.append(
                Dosage(
                    form=_get_first_text(dosage, "form"),
                    route=_get_first_text(dosage, "route"),
                    strength=_get_first_text(dosage, "strength"),
                )
            )

        patents: List[Patent] = []
        patents_el = drug.xpath('./*[local-name()="patents"]/*[local-name()="patent"]')
        for patent in patents_el:
            patents.append(
                Patent(
                    number=_get_first_text(patent, "number"),
                    country=_get_first_text(patent, "country"),
                    approved_date=_get_first_text(patent, "approved"),
                    expires_date=_get_first_text(patent, "expires"),
                    pediatric_extension=_to_bool(_get_first_text(patent, "pediatric-extension")),
                )
            )

        targets: List[Target] = []
        targets_el = drug.xpath('./*[local-name()="targets"]/*[local-name()="target"]')
        for target in targets_el:
            actions = []
            actions_el = target.xpath('./*[local-name()="actions"]')
            if actions_el:
                actions = _collect_subtexts(actions_el[0], "action")
            go_processes: List[str] = []
            for classifier in target.xpath('.//*[local-name()="go-classifier"]'):
                category = _get_first_text(classifier, "category")
                if category and category.lower() == "biological process":
                    description_text = _get_first_text(classifier, "description")
                    if description_text:
                        go_processes.append(description_text)
            targets.append(
                Target(
                    id=_get_first_text(target, "id"),
                    name=_get_first_text(target, "name"),
                    organism=_get_first_text(target, "organism"),
                    actions=actions,
                    go_processes=go_processes,
                )
            )

        drug_interactions: List[DrugInteraction] = []
        interactions_el = drug.xpath('./*[local-name()="drug-interactions"]/*[local-name()="drug-interaction"]')
        for interaction in interactions_el:
            drug_interactions.append(
                DrugInteraction(
                    interacting_drugbank_id=_get_first_text(interaction, "drugbank-id"),
                    interacting_drug_name=_get_first_text(interaction, "name"),
                    effect=_get_first_text(interaction, "description"),
                )
            )

        external_links: List[RegulatoryLink] = []
        external_links_el = drug.xpath('./*[local-name()="external-links"]/*[local-name()="external-link"]')
        for link in external_links_el:
            external_links.append(
                RegulatoryLink(
                    ref_id=_get_first_text(link, "resource"),
                    title=_get_first_text(link, "resource"),
                    url=_get_first_text(link, "url"),
                    category=None,
                )
            )

        products: List[Product] = []
        products_el = drug.xpath('./*[local-name()="products"]/*[local-name()="product"]')
        for product in products_el:
            products.append(
                Product(
                    brand=_get_first_text(product, "name"),
                    marketing_authorisation_holder=_get_first_text(product, "labeller"),
                    ndc_product_code=_get_first_text(product, "ndc-product-code"),
                    dpd_id=_get_first_text(product, "dpd-id"),
                    ema_product_code=_get_first_text(product, "ema-product-code"),
                    ema_ma_number=_get_first_text(product, "ema-ma-number"),
                    started_marketing_on=_get_first_text(product, "started-marketing-on"),
                    ended_marketing_on=_get_first_text(product, "ended-marketing-on"),
                    dosage_form=_get_first_text(product, "dosage-form"),
                    strength=_get_first_text(product, "strength"),
                    route=_get_first_text(product, "route"),
                    fda_application_number=_get_first_text(product, "fda-application-number"),
                    generic=_to_bool(_get_first_text(product, "generic")),
                    over_the_counter=_to_bool(_get_first_text(product, "over-the-counter")),
                    approved=_to_bool(_get_first_text(product, "approved")),
                    country=_get_first_text(product, "country"),
                    regulatory_source=_get_first_text(product, "source"),
                )
            )

        international_brands = _collect_subtexts(
            drug.xpath('./*[local-name()="international-brands"]')[0], "name"
        ) if drug.xpath('./*[local-name()="international-brands"]') else []

        scientific_articles: List[ReferenceArticle] = []
        general_links: List[RegulatoryLink] = []
        general_refs_el = drug.xpath('./*[local-name()="general-references"]')
        if general_refs_el:
            general_ref = general_refs_el[0]
            articles_el = general_ref.xpath('./*[local-name()="articles"]/*[local-name()="article"]')
            for article in articles_el:
                scientific_articles.append(
                    ReferenceArticle(
                        ref_id=_get_first_text(article, "ref-id"),
                        pubmed_id=_get_first_text(article, "pubmed-id"),
                        citation=_get_first_text(article, "citation"),
                    )
                )
            links_el = general_ref.xpath('./*[local-name()="links"]/*[local-name()="link"]')
            attachments_el = general_ref.xpath('./*[local-name()="attachments"]/*[local-name()="attachment"]')
            for link in links_el + attachments_el:
                general_links.append(
                    RegulatoryLink(
                        ref_id=_get_first_text(link, "ref-id"),
                        title=_get_first_text(link, "title"),
                        url=_get_first_text(link, "url"),
                        category=None,
                    )
                )

        synthesis_reference = _get_first_text(drug, "synthesis-reference")

        calculated_props = drug.xpath('./*[local-name()="calculated-properties"]/*[local-name()="property"]')
        molecular_formula = None
        molecular_weight = None
        smiles = None
        logp = None
        water_solubility = None
        melting_point = None
        for prop in calculated_props:
            kind = _get_first_text(prop, "kind")
            value = _get_first_text(prop, "value")
            if not kind or not value:
                continue
            if kind == "Molecular Formula":
                molecular_formula = value
            elif kind == "Molecular Weight":
                molecular_weight = _to_float(value)
            elif kind == "logP":
                logp = value
            elif kind == "Water Solubility":
                water_solubility = value
            elif kind == "Melting Point":
                melting_point = value
            elif kind == "SMILES":
                smiles = value

        drug_type = drug.attrib.get("type")

        drug_data = DrugData(
            drugbank_id=drugbank_id,
            name=name,
            description=description,
            cas_number=cas_number,
            unii=unii,
            drug_type=drug_type,
            type=drug_type,
            state=state,
            molecular_formula=molecular_formula,
            average_mass=average_mass,
            monoisotopic_mass=monoisotopic_mass,
            molecular_weight=molecular_weight,
            smiles=smiles,
            logp=logp,
            water_solubility=water_solubility,
            melting_point=melting_point,
            indication=_get_first_text(drug, "indication"),
            pharmacodynamics=_get_first_text(drug, "pharmacodynamics"),
            mechanism_of_action=_get_first_text(drug, "mechanism-of-action"),
            toxicity=_get_first_text(drug, "toxicity"),
            absorption=_get_first_text(drug, "absorption"),
            half_life=_get_first_text(drug, "half-life"),
            protein_binding=_get_first_text(drug, "protein-binding"),
            metabolism=_get_first_text(drug, "metabolism"),
            route_of_elimination=_get_first_text(drug, "route-of-elimination"),
            volume_of_distribution=_get_first_text(drug, "volume-of-distribution"),
            clearance=_get_first_text(drug, "clearance"),
            groups=groups,
            classification=classification_data,
            categories=categories,
            food_interactions=food_interactions,
            atc_codes=atc_codes,
            dosages=dosages,
            patents=patents,
            targets=targets,
            drug_interactions=drug_interactions,
            regulatory_links=external_links,
            products=products,
            synthesis_reference=synthesis_reference,
            scientific_articles=scientific_articles,
            references=scientific_articles,
            general_references=GeneralReferences(
                articles=scientific_articles,
                links=general_links,
            ),
            external_links=external_links,
            international_brands=international_brands,
            packagers=_get_first_text(drug, "packagers"),
            manufacturers=_get_first_text(drug, "manufacturers"),
            external_identifiers=_get_first_text(drug, "external-identifiers"),
            raw_fields=raw_fields,
        )
        results[drugbank_id] = drug_data

    logger.info("Parsed %s drugs", len(results))
    return results

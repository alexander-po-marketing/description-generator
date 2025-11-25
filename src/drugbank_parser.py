"""DrugBank XML parser."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from lxml import etree

from src.config import PipelineConfig
from src.models import DrugData

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

        drug_info: Dict[str, object] = {}
        raw_fields: Dict[str, str] = {}
        for child in drug:
            tag_name = child.tag.split("}")[-1]
            if config.desired_fields and tag_name not in config.desired_fields:
                continue

            if tag_name == "groups":
                groups = _collect_subtexts(child, "group")
                if groups:
                    drug_info["groups"] = groups
            elif tag_name == "general-references":
                ref_data: Dict[str, str] = {}
                for sub in child:
                    sub_tag = sub.tag.split("}")[-1]
                    if sub_tag == "articles":
                        articles = []
                        for article in sub:
                            citation_elements = article.xpath("./*[local-name() = 'citation']")
                            if citation_elements:
                                citation = _text_or_none(citation_elements[0])
                                if citation:
                                    articles.append(citation)
                        if articles:
                            ref_data["articles"] = " | ".join(articles)
                    else:
                        entries: List[str] = []
                        for sub_child in sub:
                            sub_child_tag = sub_child.tag.split('}')[-1]
                            sub_text = _text_or_none(sub_child)
                            if sub_text:
                                entries.append(f"{sub_child_tag}: {sub_text}")
                        if entries:
                            ref_data[sub_tag] = " | ".join(entries)
                if ref_data:
                    drug_info["general_references"] = ref_data
            elif tag_name == "classification":
                class_data: Dict[str, str] = {}
                for sub in child:
                    sub_tag = sub.tag.split("}")[-1]
                    text = _text_or_none(sub)
                    if text:
                        class_data[sub_tag] = text
                if class_data:
                    drug_info["classification"] = class_data
            elif tag_name == "products":
                product_names: List[str] = []
                for product in child:
                    name_elements = product.xpath(".//*[local-name()='name']")
                    if name_elements:
                        name_text = _text_or_none(name_elements[0])
                        if name_text:
                            product_names.append(name_text)
                    if len(product_names) >= 5:
                        break
                if product_names:
                    drug_info["products"] = product_names
            elif tag_name == "international-brands":
                brand_names = []
                for brand in child:
                    name_elements = brand.xpath(".//*[local-name()='name']")
                    if name_elements:
                        name_text = _text_or_none(name_elements[0])
                        if name_text:
                            brand_names.append(name_text)
                if brand_names:
                    drug_info["international_brands"] = brand_names
            elif tag_name == "categories":
                categories = []
                for cat in child:
                    inner = cat.xpath(".//*[local-name()='category']")
                    if inner:
                        cat_text = _text_or_none(inner[0])
                        if cat_text:
                            categories.append(cat_text)
                if categories:
                    drug_info["categories"] = categories
            else:
                if len(child) > 0:
                    sub_texts: List[str] = []
                    for sub_child in child:
                        sub_tag = sub_child.tag.split("}")[-1]
                        sub_text = _text_or_none(sub_child)
                        if sub_text:
                            sub_texts.append(f"{sub_tag}: {sub_text}")
                    if sub_texts:
                        raw_fields[tag_name] = " | ".join(sub_texts)
                        drug_info[tag_name] = " | ".join(sub_texts)
                else:
                    text = _text_or_none(child)
                    if text:
                        raw_fields[tag_name] = text
                        drug_info[tag_name] = text

        drug_data = DrugData(
            drugbank_id=drugbank_id,
            name=drug_info.get("name"),
            cas_number=drug_info.get("cas-number"),
            description=drug_info.get("description"),
            unii=drug_info.get("unii"),
            average_mass=drug_info.get("average-mass"),
            monoisotopic_mass=drug_info.get("monoisotopic-mass"),
            state=drug_info.get("state"),
            indication=drug_info.get("indication"),
            pharmacodynamics=drug_info.get("pharmacodynamics"),
            mechanism_of_action=drug_info.get("mechanism-of-action"),
            toxicity=drug_info.get("toxicity"),
            metabolism=drug_info.get("metabolism"),
            absorption=drug_info.get("absorption"),
            half_life=drug_info.get("half-life"),
            protein_binding=drug_info.get("protein-binding"),
            route_of_elimination=drug_info.get("route-of-elimination"),
            volume_of_distribution=drug_info.get("volume-of-distribution"),
            clearance=drug_info.get("clearance"),
            molecular_formula=drug_info.get("Molecular Formula"),
            smiles=drug_info.get("SMILES"),
            logp=drug_info.get("logP"),
            water_solubility=drug_info.get("Water Solubility"),
            melting_point=drug_info.get("Melting Point"),
            molecular_weight=drug_info.get("Molecular Weight"),
            classification=drug_info.get("classification", {}),
            categories=drug_info.get("categories", []),
            groups=drug_info.get("groups", []),
            packagers=drug_info.get("packagers"),
            manufacturers=drug_info.get("manufacturers"),
            external_identifiers=drug_info.get("external-identifiers"),
            external_links=drug_info.get("external-links"),
            general_references=drug_info.get("general_references", {}),
            international_brands=drug_info.get("international_brands", []),
            products=drug_info.get("products", []),
            raw_fields=raw_fields,
        )
        results[drugbank_id] = drug_data

    logger.info("Parsed %s drugs", len(results))
    return results

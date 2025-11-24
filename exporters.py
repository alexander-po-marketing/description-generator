"""Export utilities for JSON and XML outputs."""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict

from models import DrugData, GeneratedContent

logger = logging.getLogger(__name__)


def export_database(path: str, data: Dict[str, DrugData]) -> None:
    logger.info("Writing parsed database to %s", path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({k: v.to_serializable() for k, v in data.items()}, handle, ensure_ascii=False, indent=2)


def export_descriptions_json(path: str, descriptions: Dict[str, str]) -> None:
    logger.info("Writing generated descriptions to %s", path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(descriptions, handle, ensure_ascii=False, indent=2)


def export_descriptions_xml(path: str, drug_data: Dict[str, DrugData], descriptions: Dict[str, str]) -> None:
    logger.info("Writing XML descriptions to %s", path)
    root = ET.Element("drugs")
    for drug_id, drug in drug_data.items():
        if drug_id not in descriptions:
            continue
        drug_elem = ET.SubElement(root, "drug")
        ET.SubElement(drug_elem, "name").text = drug.name or ""
        ET.SubElement(drug_elem, "cas-number").text = drug.cas_number or ""
        ET.SubElement(drug_elem, "description").text = descriptions[drug_id]

    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


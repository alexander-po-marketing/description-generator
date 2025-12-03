"""Enrich internal drug records with DrugBank IDs using DrugBank XML as reference.

The script reads an internal XLSX containing columns:
- id
- name
- casNumber
- drugBankID
- unii

It applies multi-stage matching against the DrugBank XML to populate missing
``drugBankID`` values and records how each match was made. The output is a JSON
array mirroring the input order, including the resolved ``match_type``.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
from lxml import etree

logger = logging.getLogger(__name__)


@dataclass
class DrugBankIndex:
    """Lookup tables for resolving DrugBank IDs by various identifiers."""

    by_unii: Dict[str, str]
    by_name: Dict[str, str]
    by_cas: Dict[str, str]


def _text(element: Optional[etree._Element]) -> Optional[str]:
    if element is None:
        return None
    text_value = "".join(element.itertext()).strip()
    return text_value or None


def _iter_matches(parent: etree._Element, name: str) -> Iterable[etree._Element]:
    yield from parent.xpath(f"./*[local-name()='{name}']")


def _primary_id(drug_el: etree._Element) -> Optional[str]:
    primary = drug_el.xpath("./*[local-name()='drugbank-id'][@primary='true']")
    if not primary:
        return None
    return _text(primary[0])


def _normalize_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_name(value: Optional[str]) -> Optional[str]:
    key = _normalize_key(value)
    return key.lower() if key else None


def build_drugbank_index(xml_path: Path) -> DrugBankIndex:
    """Parse DrugBank XML and prepare lookup tables for matching.

    The index prefers the primary DrugBank ID and collects direct mappings for
    UNII, the main name, and CAS number.
    """

    logger.info("Loading DrugBank XML from %s", xml_path)
    parser = etree.XMLParser(recover=True)
    tree = etree.parse(str(xml_path), parser=parser)
    root = tree.getroot()

    by_unii: Dict[str, str] = {}
    by_name: Dict[str, str] = {}
    by_cas: Dict[str, str] = {}

    for drug_el in root.xpath("./*[local-name()='drug']"):
        drugbank_id = _primary_id(drug_el)
        if not drugbank_id:
            continue

        name = _text(next(iter(_iter_matches(drug_el, "name")), None))
        cas_number = _text(next(iter(_iter_matches(drug_el, "cas-number")), None))
        unii = _text(next(iter(_iter_matches(drug_el, "unii")), None))

        if unii:
            normalized_unii = _normalize_key(unii)
            if normalized_unii and normalized_unii not in by_unii:
                by_unii[normalized_unii] = drugbank_id

        if name:
            normalized_name = _normalize_name(name)
            if normalized_name and normalized_name not in by_name:
                by_name[normalized_name] = drugbank_id

        if cas_number:
            normalized_cas = _normalize_key(cas_number)
            if normalized_cas and normalized_cas not in by_cas:
                by_cas[normalized_cas] = drugbank_id

    logger.info(
        "Built DrugBank index with %s UNIIs, %s names, %s CAS numbers",
        len(by_unii),
        len(by_name),
        len(by_cas),
    )
    return DrugBankIndex(by_unii=by_unii, by_name=by_name, by_cas=by_cas)


def _resolve_drugbank_id(
    record: Dict[str, Optional[str]],
    index: DrugBankIndex,
) -> Tuple[Optional[str], str]:
    """Return matched DrugBank ID and match_type for a single record."""

    existing_id = _normalize_key(record.get("drugBankID"))
    if existing_id:
        return existing_id, "drugBankID matched"

    unii = _normalize_key(record.get("unii"))
    if unii and unii in index.by_unii:
        return index.by_unii[unii], "unii matched"

    name = _normalize_name(record.get("name"))
    if name and name in index.by_name:
        return index.by_name[name], "name matched"

    cas_number = _normalize_key(record.get("casNumber"))
    if cas_number and cas_number in index.by_cas:
        return index.by_cas[cas_number], "cas matched"

    return None, "not matched"


def enrich_records(
    dataframe: pd.DataFrame,
    index: DrugBankIndex,
) -> List[Dict[str, Optional[str]]]:
    """Enrich dataframe rows with DrugBank IDs and match types."""

    enriched: List[Dict[str, Optional[str]]] = []

    for _, row in dataframe.iterrows():
        record = {
            "internal_id": row.get("id"),
            "name": row.get("name"),
            "casNumber": row.get("casNumber"),
            "unii": row.get("unii"),
            "drugBankID": row.get("drugBankID"),
        }

        matched_id, match_type = _resolve_drugbank_id(record, index)
        record["drugBankID"] = matched_id
        record["match_type"] = match_type
        enriched.append(record)

    return enriched


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich internal drug records with DrugBank IDs using DrugBank XML references.",
    )
    parser.add_argument("xlsx_path", type=Path, help="Path to the internal XLSX file")
    parser.add_argument("xml_path", type=Path, help="Path to the DrugBank XML file")
    parser.add_argument(
        "output_json",
        type=Path,
        help="Destination path for the enriched JSON output",
    )
    parser.add_argument(
        "--sheet",
        default=0,
        help="Worksheet name or index to read from the XLSX (default: first sheet)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))

    if not args.xlsx_path.exists():
        raise FileNotFoundError(f"XLSX file not found: {args.xlsx_path}")
    if not args.xml_path.exists():
        raise FileNotFoundError(f"DrugBank XML not found: {args.xml_path}")

    logger.info("Reading internal database from %s", args.xlsx_path)
    dataframe = pd.read_excel(args.xlsx_path, sheet_name=args.sheet, dtype=str)

    index = build_drugbank_index(args.xml_path)
    enriched = enrich_records(dataframe, index)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    logger.info("Wrote %s enriched records to %s", len(enriched), args.output_json)


if __name__ == "__main__":
    main()

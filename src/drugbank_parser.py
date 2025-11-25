"""DrugBank XML parser.

This module focuses solely on translating DrugBank-style XML into the rich
``DrugData`` schema. It keeps backwards compatibility with the previous
``parse_drugbank_xml`` entry point while offering a clearer, testable
structure.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Set, Tuple

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
    RegulatoryApproval,
    RegulatoryLink,
    Product,
    Target,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def _local_name(element: etree._Element) -> str:
    """Return a tag name without namespace prefix."""

    return element.tag.split("}")[-1]


def _first_match(parent: etree._Element, name: str) -> Optional[etree._Element]:
    matches = parent.xpath(f"./*[local-name()='{name}']")
    return matches[0] if matches else None


def _iter_matches(parent: etree._Element, name: str) -> Iterable[etree._Element]:
    yield from parent.xpath(f"./*[local-name()='{name}']")


def _text(element: Optional[etree._Element]) -> Optional[str]:
    if element is None:
        return None
    text_value = "".join(element.itertext()).strip()
    return text_value or None


def _child_texts(parent: etree._Element, name: str) -> List[str]:
    values: List[str] = []
    for child in _iter_matches(parent, name):
        value = _text(child)
        if value:
            values.append(value)
    return values


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
    normalized = value.strip().lower()
    if normalized in {"true", "yes"}:
        return True
    if normalized in {"false", "no"}:
        return False
    return None


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------


class DrugbankParser:
    """Encapsulates XML parsing for DrugBank-like sources."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.desired_fields: Set[str] = config.desired_fields or set()

    # ---- Public API -----------------------------------------------------
    def parse(self) -> Dict[str, DrugData]:
        logger.info("Parsing DrugBank XML from %s", self.config.xml_path)
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(self.config.xml_path, parser=parser)
        root = tree.getroot()
        drug_elements = root.xpath('./*[local-name()="drug"]')

        results: Dict[str, DrugData] = {}
        processed = 0
        for drug_el in drug_elements:
            drugbank_id = self._primary_id(drug_el)
            if not drugbank_id:
                continue

            if self.config.valid_drug_ids and drugbank_id not in self.config.valid_drug_ids:
                continue

            processed += 1
            if self.config.max_drugs and processed > self.config.max_drugs:
                logger.info("Reached max-drugs limit (%s). Stopping early.", self.config.max_drugs)
                break

            results[drugbank_id] = self._parse_drug(drug_el, drugbank_id)

        logger.info("Parsed %s drugs", len(results))
        return results

    # ---- Parsing helpers ------------------------------------------------
    def _want(self, tag: str) -> bool:
        return not self.desired_fields or tag in self.desired_fields

    def _primary_id(self, drug_el: etree._Element) -> Optional[str]:
        primary = drug_el.xpath('./*[local-name()="drugbank-id"][@primary="true"]')
        if not primary:
            return None
        return _text(primary[0])

    def _parse_drug(self, drug_el: etree._Element, drugbank_id: str) -> DrugData:
        handled_tags: Set[str] = set()

        def text_field(tag: str) -> Optional[str]:
            if not self._want(tag):
                return None
            handled_tags.add(tag)
            return _text(_first_match(drug_el, tag))

        name = text_field("name")
        description = text_field("description")
        cas_number = text_field("cas-number")
        unii = text_field("unii")
        state = text_field("state")

        average_mass = _to_float(text_field("average-mass"))
        monoisotopic_mass = _to_float(text_field("monoisotopic-mass"))

        groups = self._parse_groups(drug_el, handled_tags)
        classification = self._parse_classification(drug_el, handled_tags)
        categories = self._parse_categories(drug_el, handled_tags)
        food_interactions = self._parse_food_interactions(drug_el, handled_tags)
        atc_codes = self._parse_atc_codes(drug_el, handled_tags)
        dosages = self._parse_dosages(drug_el, handled_tags)
        patents = self._parse_patents(drug_el, handled_tags)
        targets = self._parse_targets(drug_el, handled_tags)
        drug_interactions = self._parse_interactions(drug_el, handled_tags)
        regulatory_links = self._parse_external_links(drug_el, handled_tags)
        regulatory_approvals = self._parse_regulatory_approvals(drug_el, handled_tags)
        products = self._parse_products(drug_el, handled_tags)
        international_brands = self._parse_international_brands(drug_el, handled_tags)
        scientific_articles, general_links = self._parse_general_references(drug_el, handled_tags)

        synthesis_reference = text_field("synthesis-reference")
        smiles, logp, water_solubility, melting_point, molecular_formula, molecular_weight = (
            self._parse_calculated_properties(drug_el, handled_tags)
        )

        packagers = text_field("packagers")
        manufacturers = text_field("manufacturers")
        external_identifiers = text_field("external-identifiers")

        raw_fields = self._capture_raw_fields(drug_el, handled_tags)

        drug_type = drug_el.attrib.get("type")

        return DrugData(
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
            indication=text_field("indication"),
            pharmacodynamics=text_field("pharmacodynamics"),
            mechanism_of_action=text_field("mechanism-of-action"),
            toxicity=text_field("toxicity"),
            absorption=text_field("absorption"),
            half_life=text_field("half-life"),
            protein_binding=text_field("protein-binding"),
            metabolism=text_field("metabolism"),
            route_of_elimination=text_field("route-of-elimination"),
            volume_of_distribution=text_field("volume-of-distribution"),
            clearance=text_field("clearance"),
            groups=groups,
            classification=classification,
            categories=categories,
            international_brands=international_brands,
            food_interactions=food_interactions,
            atc_codes=atc_codes,
            dosages=dosages,
            patents=patents,
            targets=targets,
            drug_interactions=drug_interactions,
            regulatory_links=regulatory_links,
            regulatory_approvals=regulatory_approvals,
            products=products,
            synthesis_reference=synthesis_reference,
            scientific_articles=scientific_articles,
            general_references=GeneralReferences(
                articles=scientific_articles,
                links=general_links,
            ),
            references=scientific_articles,
            external_links=regulatory_links,
            packagers=packagers,
            manufacturers=manufacturers,
            external_identifiers=external_identifiers,
            raw_fields=raw_fields,
        )

    # ---- Section parsers -----------------------------------------------
    def _parse_groups(self, drug_el: etree._Element, handled: Set[str]) -> List[str]:
        if not self._want("groups"):
            return []
        handled.add("groups")
        groups_el = _first_match(drug_el, "groups")
        if not groups_el:
            return []
        return _child_texts(groups_el, "group")

    def _parse_classification(self, drug_el: etree._Element, handled: Set[str]) -> Dict[str, object]:
        if not self._want("classification"):
            return {}
        handled.add("classification")
        classification_el = _first_match(drug_el, "classification")
        if not classification_el:
            return {}

        data = {
            "description": _text(_first_match(classification_el, "description")),
            "direct_parent": _text(_first_match(classification_el, "direct-parent")),
            "kingdom": _text(_first_match(classification_el, "kingdom")),
            "superclass": _text(_first_match(classification_el, "superclass")),
            "class": _text(_first_match(classification_el, "class")),
            "subclass": _text(_first_match(classification_el, "subclass")),
            "alternative_parents": _child_texts(classification_el, "alternative-parent"),
            "substituents": _child_texts(classification_el, "substituent"),
        }
        return {k: v for k, v in data.items() if v}

    def _parse_categories(self, drug_el: etree._Element, handled: Set[str]) -> List[str]:
        if not self._want("categories"):
            return []
        handled.add("categories")
        categories: List[str] = []
        for category in drug_el.xpath('./*[local-name()="categories"]/*[local-name()="category"]'):
            # <category><category>Foo</category></category> or text directly
            nested = _text(_first_match(category, "category"))
            value = nested or _text(category)
            if value:
                categories.append(value)
        return categories

    def _parse_food_interactions(self, drug_el: etree._Element, handled: Set[str]) -> List[str]:
        if not self._want("food-interactions"):
            return []
        handled.add("food-interactions")
        food_el = _first_match(drug_el, "food-interactions")
        if not food_el:
            return []
        return _child_texts(food_el, "food-interaction")

    def _parse_atc_codes(self, drug_el: etree._Element, handled: Set[str]) -> List[ATCCode]:
        if not self._want("atc-codes"):
            return []
        handled.add("atc-codes")
        codes: List[ATCCode] = []
        for atc_el in drug_el.xpath('./*[local-name()="atc-codes"]/*[local-name()="atc-code"]'):
            code_value = atc_el.attrib.get("code")
            levels: List[ATCLevel] = []
            for level_el in _iter_matches(atc_el, "level"):
                levels.append(
                    ATCLevel(
                        code=level_el.attrib.get("code"),
                        description=_text(level_el),
                    )
                )
            codes.append(ATCCode(code=code_value, levels=levels))
        return codes

    def _parse_dosages(self, drug_el: etree._Element, handled: Set[str]) -> List[Dosage]:
        if not self._want("dosages"):
            return []
        handled.add("dosages")
        dosages: List[Dosage] = []
        for dosage_el in drug_el.xpath('./*[local-name()="dosages"]/*[local-name()="dosage"]'):
            dosages.append(
                Dosage(
                    form=_text(_first_match(dosage_el, "form")),
                    route=_text(_first_match(dosage_el, "route")),
                    strength=_text(_first_match(dosage_el, "strength")),
                )
            )
        return dosages

    def _parse_patents(self, drug_el: etree._Element, handled: Set[str]) -> List[Patent]:
        if not self._want("patents"):
            return []
        handled.add("patents")
        patents: List[Patent] = []
        for patent_el in drug_el.xpath('./*[local-name()="patents"]/*[local-name()="patent"]'):
            patents.append(
                Patent(
                    number=_text(_first_match(patent_el, "number")),
                    country=_text(_first_match(patent_el, "country")),
                    approved_date=_text(_first_match(patent_el, "approved")),
                    expires_date=_text(_first_match(patent_el, "expires")),
                    pediatric_extension=_to_bool(_text(_first_match(patent_el, "pediatric-extension"))),
                )
            )
        return patents

    def _parse_targets(self, drug_el: etree._Element, handled: Set[str]) -> List[Target]:
        if not self._want("targets"):
            return []
        handled.add("targets")
        targets: List[Target] = []
        for target_el in drug_el.xpath('./*[local-name()="targets"]/*[local-name()="target"]'):
            actions = []
            actions_el = _first_match(target_el, "actions")
            if actions_el:
                actions = _child_texts(actions_el, "action")

            go_processes: List[str] = []
            for classifier in target_el.xpath('.//*[local-name()="go-classifier"]'):
                category = _text(_first_match(classifier, "category"))
                if category and category.lower() == "biological process":
                    description = _text(_first_match(classifier, "description"))
                    if description:
                        go_processes.append(description)

            targets.append(
                Target(
                    id=_text(_first_match(target_el, "id")),
                    name=_text(_first_match(target_el, "name")),
                    organism=_text(_first_match(target_el, "organism")),
                    actions=actions,
                    go_processes=go_processes,
                )
            )
        return targets

    def _parse_interactions(self, drug_el: etree._Element, handled: Set[str]) -> List[DrugInteraction]:
        if not self._want("drug-interactions"):
            return []
        handled.add("drug-interactions")
        interactions: List[DrugInteraction] = []
        for interaction_el in drug_el.xpath('./*[local-name()="drug-interactions"]/*[local-name()="drug-interaction"]'):
            interactions.append(
                DrugInteraction(
                    interacting_drugbank_id=_text(_first_match(interaction_el, "drugbank-id")),
                    interacting_drug_name=_text(_first_match(interaction_el, "name")),
                    effect=_text(_first_match(interaction_el, "description")),
                )
            )
        return interactions

    def _parse_external_links(self, drug_el: etree._Element, handled: Set[str]) -> List[RegulatoryLink]:
        if not self._want("external-links"):
            return []
        handled.add("external-links")
        links: List[RegulatoryLink] = []
        for link_el in drug_el.xpath('./*[local-name()="external-links"]/*[local-name()="external-link"]'):
            resource = _text(_first_match(link_el, "resource"))
            links.append(
                RegulatoryLink(
                    ref_id=resource,
                    title=resource,
                    url=_text(_first_match(link_el, "url")),
                    category=None,
                )
            )
        return links

    def _parse_regulatory_approvals(
        self, drug_el: etree._Element, handled: Set[str]
    ) -> List[RegulatoryApproval]:
        if not self._want("regulatory-approvals"):
            return []
        handled.add("regulatory-approvals")
        approvals: List[RegulatoryApproval] = []
        for approval_el in drug_el.xpath(
            './*[local-name()="regulatory-approvals"]/*[local-name()="regulatory-approval"]'
        ):
            approvals.append(
                RegulatoryApproval(
                    agency=_text(_first_match(approval_el, "agency")),
                    region=_text(_first_match(approval_el, "region")),
                    status=_text(_first_match(approval_el, "status")),
                    notes=_text(_first_match(approval_el, "notes")) or _text(approval_el),
                )
            )
        return approvals

    def _parse_products(self, drug_el: etree._Element, handled: Set[str]) -> List[Product]:
        if not self._want("products"):
            return []
        handled.add("products")
        products: List[Product] = []
        for product_el in drug_el.xpath('./*[local-name()="products"]/*[local-name()="product"]'):
            products.append(
                Product(
                    brand=_text(_first_match(product_el, "name")),
                    marketing_authorisation_holder=_text(_first_match(product_el, "labeller")),
                    ndc_product_code=_text(_first_match(product_el, "ndc-product-code")),
                    dpd_id=_text(_first_match(product_el, "dpd-id")),
                    ema_product_code=_text(_first_match(product_el, "ema-product-code")),
                    ema_ma_number=_text(_first_match(product_el, "ema-ma-number")),
                    started_marketing_on=_text(_first_match(product_el, "started-marketing-on")),
                    ended_marketing_on=_text(_first_match(product_el, "ended-marketing-on")),
                    dosage_form=_text(_first_match(product_el, "dosage-form")),
                    strength=_text(_first_match(product_el, "strength")),
                    route=_text(_first_match(product_el, "route")),
                    fda_application_number=_text(_first_match(product_el, "fda-application-number")),
                    generic=_to_bool(_text(_first_match(product_el, "generic"))),
                    over_the_counter=_to_bool(_text(_first_match(product_el, "over-the-counter"))),
                    approved=_to_bool(_text(_first_match(product_el, "approved"))),
                    country=_text(_first_match(product_el, "country")),
                    regulatory_source=_text(_first_match(product_el, "source")),
                )
            )
        return products

    def _parse_international_brands(
        self, drug_el: etree._Element, handled: Set[str]
    ) -> List[str]:
        if not self._want("international-brands"):
            return []
        handled.add("international-brands")
        brands_el = _first_match(drug_el, "international-brands")
        if not brands_el:
            return []
        return _child_texts(brands_el, "name")

    def _parse_general_references(
        self, drug_el: etree._Element, handled: Set[str]
    ) -> Tuple[List[ReferenceArticle], List[RegulatoryLink]]:
        if not self._want("general-references"):
            return [], []
        handled.add("general-references")
        scientific_articles: List[ReferenceArticle] = []
        general_links: List[RegulatoryLink] = []

        general_ref_el = _first_match(drug_el, "general-references")
        if not general_ref_el:
            return scientific_articles, general_links

        for article_el in general_ref_el.xpath('./*[local-name()="articles"]/*[local-name()="article"]'):
            scientific_articles.append(
                ReferenceArticle(
                    ref_id=_text(_first_match(article_el, "ref-id")),
                    pubmed_id=_text(_first_match(article_el, "pubmed-id")),
                    citation=_text(_first_match(article_el, "citation")) or _text(article_el),
                )
            )

        link_nodes = general_ref_el.xpath('./*[local-name()="links"]/*[local-name()="link"]')
        attachment_nodes = general_ref_el.xpath(
            './*[local-name()="attachments"]/*[local-name()="attachment"]'
        )
        for link_el in link_nodes + attachment_nodes:
            general_links.append(
                RegulatoryLink(
                    ref_id=_text(_first_match(link_el, "ref-id")),
                    title=_text(_first_match(link_el, "title")) or _text(link_el),
                    url=_text(_first_match(link_el, "url")),
                    category=None,
                )
            )

        return scientific_articles, general_links

    def _parse_calculated_properties(
        self, drug_el: etree._Element, handled: Set[str]
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[float]]:
        desired_property_keys = {
            "Molecular Formula",
            "SMILES",
            "logP",
            "Water Solubility",
            "Melting Point",
            "Molecular Weight",
        }
        if self.desired_fields and not (desired_property_keys & self.desired_fields):
            return None, None, None, None, None, None

        handled.add("calculated-properties")
        smiles = None
        logp = None
        water_solubility = None
        melting_point = None
        molecular_formula = None
        molecular_weight = None

        for prop_el in drug_el.xpath(
            './*[local-name()="calculated-properties"]/*[local-name()="property"]'
        ):
            kind = _text(_first_match(prop_el, "kind"))
            value = _text(_first_match(prop_el, "value"))
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

        return smiles, logp, water_solubility, melting_point, molecular_formula, molecular_weight

    def _capture_raw_fields(self, drug_el: etree._Element, handled: Set[str]) -> Dict[str, object]:
        raw: Dict[str, object] = {}
        for child in drug_el:
            tag = _local_name(child)
            if tag in handled:
                continue
            value = _text(child)
            if not value:
                continue
            if tag in raw:
                existing = raw[tag]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    raw[tag] = [existing, value]
            else:
                raw[tag] = value
        return raw


def parse_drugbank_xml(config: PipelineConfig) -> Dict[str, DrugData]:
    """Backward-compatible entry point."""

    return DrugbankParser(config).parse()


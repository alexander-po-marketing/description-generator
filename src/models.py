"""Data models for parsed and generated content."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class Classification:
    description: Optional[str] = None
    direct_parent: Optional[str] = None
    kingdom: Optional[str] = None
    superclass: Optional[str] = None
    class_name: Optional[str] = None
    subclass: Optional[str] = None
    alternative_parents: List[str] = field(default_factory=list)
    substituents: List[str] = field(default_factory=list)


@dataclass
class ATCLevel:
    code: Optional[str] = None
    description: Optional[str] = None


@dataclass
class ATCCode:
    code: Optional[str] = None
    levels: List[ATCLevel] = field(default_factory=list)


@dataclass
class Dosage:
    form: Optional[str] = None
    route: Optional[str] = None
    strength: Optional[str] = None


@dataclass
class Patent:
    number: Optional[str] = None
    country: Optional[str] = None
    approved_date: Optional[str] = None
    expires_date: Optional[str] = None
    pediatric_extension: Optional[bool] = None


@dataclass
class Target:
    id: Optional[str] = None
    name: Optional[str] = None
    organism: Optional[str] = None
    actions: List[str] = field(default_factory=list)
    go_processes: List[str] = field(default_factory=list)


@dataclass
class DrugInteraction:
    interacting_drugbank_id: Optional[str] = None
    interacting_drug_name: Optional[str] = None
    effect: Optional[str] = None


@dataclass
class RegulatoryLink:
    ref_id: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    category: Optional[str] = None


@dataclass
class ExternalIdentifier:
    resource: Optional[str] = None
    identifier: Optional[str] = None


@dataclass
class RegulatoryApproval:
    agency: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class Product:
    brand: Optional[str] = None
    marketing_authorisation_holder: Optional[str] = None
    ndc_product_code: Optional[str] = None
    dpd_id: Optional[str] = None
    ema_product_code: Optional[str] = None
    ema_ma_number: Optional[str] = None
    started_marketing_on: Optional[str] = None
    ended_marketing_on: Optional[str] = None
    dosage_form: Optional[str] = None
    strength: Optional[str] = None
    route: Optional[str] = None
    fda_application_number: Optional[str] = None
    generic: Optional[bool] = None
    over_the_counter: Optional[bool] = None
    approved: Optional[bool] = None
    country: Optional[str] = None
    regulatory_source: Optional[str] = None


@dataclass
class ReferenceArticle:
    ref_id: Optional[str] = None
    pubmed_id: Optional[str] = None
    citation: Optional[str] = None


@dataclass
class GeneralReferences:
    links: List[RegulatoryLink] = field(default_factory=list)


@dataclass
class DrugData:
    drugbank_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    cas_number: Optional[str] = None
    unii: Optional[str] = None
    drug_type: Optional[str] = None
    type: Optional[str] = None

    state: Optional[str] = None
    drug_type_short: Optional[str] = None

    molecular_formula: Optional[str] = None
    average_mass: Optional[float] = None
    monoisotopic_mass: Optional[float] = None
    molecular_weight: Optional[float] = None
    smiles: Optional[str] = None
    logp: Optional[str] = None
    water_solubility: Optional[str] = None
    melting_point: Optional[str] = None

    indication: Optional[str] = None
    pharmacodynamics: Optional[str] = None
    mechanism_of_action: Optional[str] = None
    toxicity: Optional[str] = None
    absorption: Optional[str] = None
    half_life: Optional[str] = None
    protein_binding: Optional[str] = None
    metabolism: Optional[str] = None
    route_of_elimination: Optional[str] = None
    volume_of_distribution: Optional[str] = None
    clearance: Optional[str] = None

    groups: List[str] = field(default_factory=list)
    classification: Dict[str, object] = field(default_factory=dict)
    categories: List[str] = field(default_factory=list)
    international_brands: List[str] = field(default_factory=list)

    food_interactions: List[str] = field(default_factory=list)
    atc_codes: List[ATCCode] = field(default_factory=list)
    dosages: List[Dosage] = field(default_factory=list)
    patents: List[Patent] = field(default_factory=list)
    targets: List[Target] = field(default_factory=list)
    drug_interactions: List[DrugInteraction] = field(default_factory=list)
    regulatory_links: List[RegulatoryLink] = field(default_factory=list)
    regulatory_approvals: List[RegulatoryApproval] = field(default_factory=list)
    products: List[Product] = field(default_factory=list)

    synthesis_reference: Optional[str] = None
    scientific_articles: List[ReferenceArticle] = field(default_factory=list)
    general_references: GeneralReferences = field(default_factory=GeneralReferences)

    packagers: List[str] = field(default_factory=list)
    manufacturers: List[str] = field(default_factory=list)
    external_identifiers: List[ExternalIdentifier] = field(default_factory=list)
    raw_fields: Dict[str, object] = field(default_factory=dict)

    def to_serializable(self) -> Dict[str, object]:
        data = asdict(self)
        # CamelCase aliases for downstream consumers
        data["drugbankId"] = self.drugbank_id
        data["casNumber"] = self.cas_number
        data["unii"] = self.unii
        data["drugType"] = self.drug_type
        data["averageMass"] = self.average_mass
        data["monoisotopicMass"] = self.monoisotopic_mass
        data["molecularFormula"] = self.molecular_formula
        data["molecularWeight"] = self.molecular_weight
        data["foodInteractions"] = self.food_interactions
        data["drugInteractions"] = [asdict(interaction) for interaction in self.drug_interactions]
        data["regulatoryLinks"] = [asdict(link) for link in self.regulatory_links]
        data["regulatoryApprovals"] = [asdict(approval) for approval in self.regulatory_approvals]
        data["products"] = [asdict(product) for product in self.products]
        data["scientificArticles"] = [asdict(article) for article in self.scientific_articles]
        data["generalReferences"] = asdict(self.general_references) if self.general_references else {}
        data["externalIdentifiers"] = [asdict(identifier) for identifier in self.external_identifiers]
        data["atcCodes"] = [asdict(code) for code in self.atc_codes]
        data["dosages"] = [asdict(dosage) for dosage in self.dosages]
        data["patents"] = [asdict(patent) for patent in self.patents]
        data["targets"] = [asdict(target) for target in self.targets]
        return data


@dataclass
class GeneratedContent:
    description_html: str
    summary: str
    summary_sentence: Optional[str] = None


@dataclass
class DrugGenerationResult:
    drug: DrugData
    generated: GeneratedContent


"""Data models for parsed and generated content."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class DrugData:
    drugbank_id: str
    name: Optional[str] = None
    cas_number: Optional[str] = None
    description: Optional[str] = None
    unii: Optional[str] = None
    average_mass: Optional[str] = None
    monoisotopic_mass: Optional[str] = None
    state: Optional[str] = None
    indication: Optional[str] = None
    pharmacodynamics: Optional[str] = None
    mechanism_of_action: Optional[str] = None
    toxicity: Optional[str] = None
    metabolism: Optional[str] = None
    absorption: Optional[str] = None
    half_life: Optional[str] = None
    protein_binding: Optional[str] = None
    route_of_elimination: Optional[str] = None
    volume_of_distribution: Optional[str] = None
    clearance: Optional[str] = None
    molecular_formula: Optional[str] = None
    smiles: Optional[str] = None
    logp: Optional[str] = None
    water_solubility: Optional[str] = None
    melting_point: Optional[str] = None
    molecular_weight: Optional[str] = None
    classification: Dict[str, str] = field(default_factory=dict)
    categories: List[str] = field(default_factory=list)
    groups: List[str] = field(default_factory=list)
    packagers: Optional[str] = None
    manufacturers: Optional[str] = None
    external_identifiers: Optional[str] = None
    external_links: Optional[str] = None
    general_references: Dict[str, str] = field(default_factory=dict)
    international_brands: List[str] = field(default_factory=list)
    products: List[str] = field(default_factory=list)
    raw_fields: Dict[str, str] = field(default_factory=dict)

    def to_serializable(self) -> Dict[str, object]:
        data = asdict(self)
        return data


@dataclass
class GeneratedContent:
    description_html: str
    summary: str


@dataclass
class DrugGenerationResult:
    drug: DrugData
    generated: GeneratedContent


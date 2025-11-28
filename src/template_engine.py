"""Template engine for UI-driven API page JSON generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


@dataclass
class RenderedNode:
    """Normalized node returned by the renderer."""

    id: str
    name: str
    type: str
    value: Any

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "type": self.type, "value": self.value}


@dataclass
class TemplateNode:
    """Configurable block or field within a template definition."""

    id: str
    label: str
    path: List[str] = field(default_factory=list)
    type: str = "group"  # group | field | array | openapi
    visible: bool = True
    limit: Optional[int] = None
    data_source: str = "data"  # data | openapi
    children: List["TemplateNode"] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TemplateNode":
        return cls(
            id=str(payload.get("id")),
            label=str(payload.get("label") or payload.get("name") or payload.get("id")),
            path=list(payload.get("path") or []),
            type=str(payload.get("type", "group")),
            visible=bool(payload.get("visible", True)),
            limit=payload.get("limit"),
            data_source=str(payload.get("data_source") or payload.get("dataSource") or "data"),
            children=[cls.from_dict(child) for child in payload.get("children", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "path": self.path,
            "type": self.type,
            "visible": self.visible,
            "limit": self.limit,
            "dataSource": self.data_source,
            "children": [child.to_dict() for child in self.children],
        }

    def _resolve_context(self, context: Any, openapi_data: Any) -> Any:
        if self.data_source == "openapi":
            return openapi_data
        target = context
        if self.path:
            for key in self.path:
                if not isinstance(target, Mapping):
                    return None
                target = target.get(key)
        return target

    def _limit_items(self, value: Any) -> Any:
        if self.limit is None or not isinstance(value, list):
            return value
        return value[: self.limit]

    def render(self, root_data: Mapping[str, Any], openapi_data: Any, context: Any = None) -> Optional[RenderedNode]:
        if not self.visible:
            return None

        context_data = root_data if context is None else context
        current_value = self._resolve_context(context_data, openapi_data)
        if current_value is None:
            return None

        if self.children:
            rendered_children: Dict[str, Any] | List[Dict[str, Any]]
            if isinstance(current_value, list):
                rendered_children = []
                for entry in self._limit_items(current_value) or []:
                    if not isinstance(entry, Mapping):
                        continue
                    child_map: Dict[str, Any] = {}
                    for child in self.children:
                        rendered = child.render(root_data, openapi_data, entry)
                        if rendered is not None:
                            child_map[rendered.name] = rendered.value
                    if child_map:
                        rendered_children.append(child_map)
            else:
                rendered_children = {}
                for child in self.children:
                    rendered = child.render(root_data, openapi_data, current_value)
                    if rendered is not None:
                        rendered_children[rendered.name] = rendered.value
            if not rendered_children:
                return None
            return RenderedNode(id=self.id, name=self.label, type=self.type, value=rendered_children)

        value = current_value
        if isinstance(value, list):
            value = self._limit_items(value)
        return RenderedNode(id=self.id, name=self.label, type=self.type, value=value)


@dataclass
class TemplateDefinition:
    """Top-level template representation used by the generator."""

    name: str
    blocks: List[TemplateNode]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TemplateDefinition":
        return cls(
            name=str(payload.get("name") or "API Page Template"),
            blocks=[TemplateNode.from_dict(block) for block in payload.get("blocks", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "blocks": [block.to_dict() for block in self.blocks]}

    def render(self, page_data: Mapping[str, Any], openapi_data: Any = None) -> List[Dict[str, Any]]:
        rendered: List[Dict[str, Any]] = []
        for block in self.blocks:
            node = block.render(page_data, openapi_data, page_data)
            if node is not None:
                rendered.append(node.to_dict())
        return rendered


DEFAULT_TEMPLATE = TemplateDefinition(
    name="Pharmaoffer API page",
    blocks=[
        TemplateNode(
            id="hero",
            label="Hero",
            path=["hero"],
            children=[
                TemplateNode(id="hero-title", label="Title", path=["title"], type="field"),
                TemplateNode(id="hero-summary", label="Summary sentence", path=["summarySentence"], type="field"),
                TemplateNode(id="hero-tags", label="Tags", path=["tags"], type="array", limit=6),
                TemplateNode(id="hero-use-cases", label="Primary use cases", path=["primaryUseCases"], type="array", limit=6),
            ],
        ),
        TemplateNode(
            id="overview",
            label="Overview",
            path=["overview"],
            children=[
                TemplateNode(id="overview-summary", label="Key takeaway", path=["summary"], type="field"),
                TemplateNode(id="overview-description", label="Description", path=["description"], type="field"),
            ],
        ),
        TemplateNode(
            id="identification",
            label="Identification",
            path=["identification"],
            children=[
                TemplateNode(id="identification-generic", label="Generic name", path=["genericName"], type="field"),
                TemplateNode(id="identification-brands", label="Brand names", path=["brandNames"], type="array", limit=12),
                TemplateNode(id="identification-synonyms", label="Synonyms", path=["synonyms"], type="array", limit=12),
                TemplateNode(id="identification-molecule-type", label="Molecule type", path=["moleculeType"], type="field"),
                TemplateNode(id="identification-groups", label="Groups", path=["groups"], type="array", limit=8),
                TemplateNode(
                    id="identification-identifiers",
                    label="Identifiers",
                    path=["identifiers"],
                    children=[
                        TemplateNode(id="identifiers-cas", label="CAS", path=["casNumber"], type="field"),
                        TemplateNode(id="identifiers-unii", label="UNII", path=["unii"], type="field"),
                        TemplateNode(id="identifiers-drugbank", label="DrugBank ID", path=["drugbankId"], type="field"),
                        TemplateNode(id="identifiers-external", label="External", path=["external"], type="array", limit=12),
                    ],
                ),
            ],
        ),
        TemplateNode(
            id="chemistry",
            label="Chemistry",
            path=["chemistry"],
            children=[
                TemplateNode(id="chemistry-formula", label="Formula", path=["formula"], type="field"),
                TemplateNode(id="chemistry-average-mw", label="Average molecular weight", path=["averageMolecularWeight"], type="field"),
                TemplateNode(id="chemistry-mono-mass", label="Monoisotopic mass", path=["monoisotopicMass"], type="field"),
                TemplateNode(id="chemistry-logp", label="logP", path=["logP"], type="field"),
                TemplateNode(
                    id="chemistry-properties",
                    label="Experimental properties",
                    path=["experimentalProperties"],
                    type="array",
                    limit=20,
                    children=[
                        TemplateNode(id="chemistry-property-name", label="Name", path=["name"], type="field"),
                        TemplateNode(id="chemistry-property-value", label="Value", path=["value"], type="field"),
                    ],
                ),
            ],
        ),
        TemplateNode(
            id="regulatory",
            label="Regulatory and market",
            path=["regulatoryAndMarket"],
            children=[
                TemplateNode(id="regulatory-status", label="Approval status", path=["approvalStatus"], type="field"),
                TemplateNode(id="regulatory-markets", label="Markets", path=["markets"], type="array", limit=20),
                TemplateNode(
                    id="regulatory-patents",
                    label="Patents",
                    path=["patents"],
                    type="array",
                    limit=20,
                    children=[
                        TemplateNode(id="patent-number", label="Number", path=["number"], type="field"),
                        TemplateNode(id="patent-country", label="Country", path=["country"], type="field"),
                        TemplateNode(id="patent-approved", label="Approved", path=["approvedDate"], type="field"),
                        TemplateNode(id="patent-expires", label="Expires", path=["expiresDate"], type="field"),
                        TemplateNode(id="patent-pediatric", label="Pediatric extension", path=["pediatricExtension"], type="field"),
                    ],
                ),
                TemplateNode(id="regulatory-lifecycle", label="Lifecycle summary", path=["lifecycleSummary"], type="field"),
                TemplateNode(id="regulatory-label-highlights", label="Label highlights", path=["labelHighlights"], type="array", limit=6),
            ],
        ),
        TemplateNode(
            id="formulation-notes",
            label="Formulation notes",
            path=["formulationNotes"],
            children=[TemplateNode(id="formulation-bullets", label="Bullets", path=["bullets"], type="array", limit=6)],
        ),
        TemplateNode(
            id="taxonomy",
            label="Categories and taxonomy",
            path=["categoriesAndTaxonomy"],
            children=[
                TemplateNode(id="taxonomy-classes", label="Therapeutic classes", path=["therapeuticClasses"], type="array", limit=12),
                TemplateNode(
                    id="taxonomy-atc",
                    label="ATC codes",
                    path=["atcCodes"],
                    type="array",
                    limit=20,
                    children=[
                        TemplateNode(id="atc-code", label="Code", path=["code"], type="field"),
                        TemplateNode(id="atc-levels", label="Levels", path=["levels"], type="array", limit=10),
                    ],
                ),
                TemplateNode(id="taxonomy-classification", label="Classification", path=["classification"], type="field"),
            ],
        ),
        TemplateNode(
            id="pharmacology",
            label="Pharmacology",
            path=["pharmacology"],
            children=[
                TemplateNode(id="pharmacology-moa", label="Mechanism of action", path=["mechanismOfAction"], type="field"),
                TemplateNode(id="pharmacology-dynamics", label="Pharmacodynamics", path=["pharmacodynamics"], type="field"),
                TemplateNode(
                    id="pharmacology-targets",
                    label="Targets",
                    path=["targets"],
                    type="array",
                    limit=20,
                    children=[
                        TemplateNode(id="target-name", label="Name", path=["name"], type="field"),
                        TemplateNode(id="target-organism", label="Organism", path=["organism"], type="field"),
                        TemplateNode(id="target-actions", label="Actions", path=["actions"], type="array", limit=8),
                        TemplateNode(id="target-go-processes", label="GO processes", path=["goProcesses"], type="array", limit=8),
                    ],
                ),
                TemplateNode(id="pharmacology-summary", label="High level summary", path=["highLevelSummary"], type="field"),
            ],
        ),
        TemplateNode(
            id="adme-pk",
            label="ADME/PK",
            path=["admePk"],
            children=[
                TemplateNode(id="adme-absorption", label="Absorption", path=["absorption"], type="field"),
                TemplateNode(id="adme-half-life", label="Half-life", path=["halfLife"], type="field"),
                TemplateNode(id="adme-binding", label="Protein binding", path=["proteinBinding"], type="field"),
                TemplateNode(id="adme-metabolism", label="Metabolism", path=["metabolism"], type="field"),
                TemplateNode(id="adme-elimination", label="Route of elimination", path=["routeOfElimination"], type="field"),
                TemplateNode(id="adme-volume", label="Volume of distribution", path=["volumeOfDistribution"], type="field"),
                TemplateNode(id="adme-clearance", label="Clearance", path=["clearance"], type="field"),
                TemplateNode(
                    id="adme-pk-snapshot",
                    label="PK snapshot",
                    path=["pkSnapshot"],
                    children=[TemplateNode(id="adme-pk-bullets", label="Key points", path=["keyPoints"], type="array", limit=6)],
                ),
            ],
        ),
        TemplateNode(
            id="products",
            label="Products and dosage forms",
            path=["productsAndDosageForms"],
            children=[
                TemplateNode(
                    id="products-dosage",
                    label="Dosage forms",
                    path=["dosageForms"],
                    type="array",
                    limit=25,
                    children=[
                        TemplateNode(id="dosage-form", label="Form", path=["form"], type="field"),
                        TemplateNode(id="dosage-route", label="Route", path=["route"], type="field"),
                        TemplateNode(id="dosage-strength", label="Strength", path=["strength"], type="field"),
                    ],
                ),
                TemplateNode(id="products-by-market", label="Brands by market", path=["brandsByMarket"], type="field"),
                TemplateNode(id="products-market-summary", label="Market presence summary", path=["marketPresenceSummary"], type="field"),
            ],
        ),
        TemplateNode(
            id="clinical",
            label="Clinical trials",
            path=["clinicalTrials"],
            children=[
                TemplateNode(id="clinical-by-phase", label="Trials by phase", path=["trialsByPhase"], type="field"),
                TemplateNode(id="clinical-has-data", label="Has data", path=["hasClinicalTrialsData"], type="field"),
            ],
        ),
        TemplateNode(
            id="supply",
            label="Suppliers and manufacturing",
            path=["suppliersAndManufacturing"],
            children=[
                TemplateNode(id="supply-manufacturers", label="Manufacturers", path=["manufacturers"], type="array", limit=20),
                TemplateNode(id="supply-packagers", label="Packagers", path=["packagers"], type="array", limit=20),
                TemplateNode(id="supply-notes", label="External manufacturing notes", path=["externalManufacturingNotes"], type="field"),
                TemplateNode(id="supply-pharmaoffer", label="Pharmaoffer suppliers", path=["pharmaofferSuppliers"], type="array", limit=20),
                TemplateNode(id="supply-summary", label="Supply chain summary", path=["supplyChainSummary"], type="field"),
            ],
        ),
        TemplateNode(
            id="safety",
            label="Safety",
            path=["safety"],
            children=[
                TemplateNode(id="safety-toxicity", label="Toxicity", path=["toxicity"], type="field"),
                TemplateNode(id="safety-warnings", label="High level warnings", path=["highLevelWarnings"], type="array", limit=6),
            ],
        ),
        TemplateNode(
            id="experimental",
            label="Experimental properties",
            path=["experimentalProperties"],
            children=[TemplateNode(id="experimental-list", label="Properties", path=["properties"], type="array", limit=25)],
        ),
        TemplateNode(
            id="references",
            label="References",
            path=["references"],
            children=[
                TemplateNode(id="references-articles", label="Scientific articles", path=["scientificArticles"], type="array", limit=20),
                TemplateNode(id="references-regulatory", label="Regulatory links", path=["regulatoryLinks"], type="array", limit=20),
                TemplateNode(id="references-other", label="Other links", path=["otherLinks"], type="array", limit=20),
            ],
        ),
        TemplateNode(
            id="seo",
            label="SEO",
            path=["seo"],
            children=[
                TemplateNode(id="seo-title", label="Title", path=["title"], type="field"),
                TemplateNode(id="seo-meta", label="Meta description", path=["metaDescription"], type="field"),
                TemplateNode(id="seo-keywords", label="Keywords", path=["keywords"], type="array", limit=25),
            ],
        ),
        TemplateNode(
            id="buyer-cheatsheet",
            label="Buyer cheatsheet",
            path=["buyerCheatsheet"],
            children=[TemplateNode(id="buyer-bullets", label="Bullets", path=["bullets"], type="array", limit=6)],
        ),
        TemplateNode(
            id="metadata",
            label="Metadata",
            path=["metadata"],
            children=[
                TemplateNode(id="metadata-drugbank", label="DrugBank ID", path=["drugbankId"], type="field"),
                TemplateNode(id="metadata-cas", label="CAS number", path=["casNumber"], type="field"),
                TemplateNode(id="metadata-unii", label="UNII", path=["unii"], type="field"),
                TemplateNode(id="metadata-created", label="Created at", path=["createdAt"], type="field"),
                TemplateNode(id="metadata-updated", label="Updated at", path=["updatedAt"], type="field"),
                TemplateNode(id="metadata-sources", label="Source systems", path=["sourceSystems"], type="array", limit=10),
            ],
        ),
        TemplateNode(
            id="openapi",
            label="OpenAPI schema",
            path=["openapi"],
            type="openapi",
            data_source="openapi",
            visible=False,
        ),
    ],
)


def load_template_definition(path: str | Path | None) -> TemplateDefinition:
    """Load a template definition from disk or fall back to the default."""

    if path:
        file_path = Path(path)
        if file_path.exists():
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            return TemplateDefinition.from_dict(payload)
    return DEFAULT_TEMPLATE


def save_template_definition(template: TemplateDefinition, path: str | Path) -> Path:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(template.to_dict(), indent=2), encoding="utf-8")
    return file_path


__all__ = [
    "TemplateDefinition",
    "TemplateNode",
    "RenderedNode",
    "DEFAULT_TEMPLATE",
    "load_template_definition",
    "save_template_definition",
]

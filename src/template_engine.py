"""Template engine for UI-driven API page JSON generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set


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
    generation_id: Optional[str] = None
    generation_enabled: bool = True
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
            generation_id=payload.get("generation_id")
            or payload.get("generationId")
            or payload.get("generationID"),
            generation_enabled=bool(payload.get("generation_enabled", payload.get("generationEnabled", True))),
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
            "generationId": self.generation_id,
            "generationEnabled": self.generation_enabled,
            "children": [child.to_dict() for child in self.children],
        }

    def has_generation_controls(self, visible_ancestor: bool = True) -> bool:
        current_visible = visible_ancestor and self.visible
        if current_visible and self.generation_id is not None:
            return True
        return any(child.has_generation_controls(current_visible) for child in self.children)

    def has_generation_id(self) -> bool:
        if self.generation_id is not None:
            return True
        return any(child.has_generation_id() for child in self.children)

    def generation_flags(self, visible_ancestor: bool = True) -> Dict[str, bool]:
        current_visible = visible_ancestor and self.visible
        flags: Dict[str, bool] = {}
        if self.generation_id:
            flags[self.generation_id] = bool(current_visible and self.generation_enabled)
        for child in self.children:
            flags.update(child.generation_flags(current_visible))
        return flags

    def enabled_generations(self, visible_ancestor: bool = True) -> Set[str]:
        current_visible = visible_ancestor and self.visible
        enabled: Set[str] = set()
        if current_visible and self.generation_id and self.generation_enabled:
            enabled.add(self.generation_id)
        for child in self.children:
            enabled.update(child.enabled_generations(current_visible))
        return enabled

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

    def has_generation_controls(self) -> bool:
        return any(block.has_generation_controls() for block in self.blocks)

    def has_generation_ids(self) -> bool:
        return any(block.has_generation_id() for block in self.blocks)

    def enabled_generations(self) -> Set[str]:
        enabled: Set[str] = set()
        for block in self.blocks:
            enabled.update(block.enabled_generations())
        return enabled

    def generation_flags(self) -> Dict[str, bool]:
        flags: Dict[str, bool] = {}
        for block in self.blocks:
            flags.update(block.generation_flags())
        return flags

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
                TemplateNode(
                    id="hero-summary",
                    label="Summary sentence",
                    path=["summarySentence"],
                    type="field",
                    generation_id="summary_sentence",
                ),
                TemplateNode(
                    id="hero-therapeutic-categories",
                    label="Therapeutic categories",
                    path=["therapeuticCategories"],
                    type="array",
                    limit=6,
                ),
                TemplateNode(
                    id="hero-facts",
                    label="Key facts",
                    path=["facts"],
                    children=[
                        TemplateNode(id="fact-generic", label="Generic name", path=["genericName"], type="field"),
                        TemplateNode(id="fact-molecule-type", label="Molecule type", path=["moleculeType"], type="field"),
                        TemplateNode(id="fact-cas", label="CAS number", path=["casNumber"], type="field"),
                        TemplateNode(id="fact-drugbank", label="DrugBank ID", path=["drugbankId"], type="field"),
                        TemplateNode(id="fact-approval", label="Approval status", path=["approvalStatus"], type="field"),
                        TemplateNode(id="fact-atc", label="ATC code", path=["atcCode"], type="field"),
                    ],
                ),
            ],
        ),
        TemplateNode(id="primary-indications", label="Primary indications", path=["primaryIndications"], type="array", limit=6),
        TemplateNode(
            id="buyer-cheatsheet",
            label="Buyer cheatsheet",
            path=["buyerCheatsheet"],
            children=[
                TemplateNode(
                    id="buyer-bullets",
                    label="Bullets",
                    path=["bullets"],
                    type="array",
                    limit=6,
                    generation_id="buyer_cheatsheet",
                )
            ],
        ),
        TemplateNode(
            id="clinical-overview",
            label="Clinical overview",
            path=["clinicalOverview"],
            children=[
                TemplateNode(
                    id="clinical-summary",
                    label="Key takeaway",
                    path=["summary"],
                    type="field",
                    generation_id="summary",
                ),
                TemplateNode(
                    id="clinical-description",
                    label="Long description",
                    path=["longDescription"],
                    type="field",
                    generation_id="description",
                ),
                TemplateNode(
                    id="identification-classification",
                    label="Identification and classification",
                    path=["identificationClassification"],
                    children=[
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
                            ],
                        ),
                    ],
                ),
                TemplateNode(
                    id="pharmacology-targets",
                    label="Pharmacology and targets",
                    path=["pharmacologyTargets"],
                    children=[
                        TemplateNode(
                            id="pharmacology-summary",
                            label="Summary",
                            path=["summary"],
                            type="field",
                            generation_id="pharmacology_summary",
                        ),
                        TemplateNode(
                            id="pharmacology-details",
                            label="Pharmacology",
                            path=["pharmacology"],
                            children=[
                                TemplateNode(id="pharmacology-moa", label="Mechanism of action", path=["mechanismOfAction"], type="field"),
                                TemplateNode(id="pharmacology-dynamics", label="Pharmacodynamics", path=["pharmacodynamics"], type="field"),
                            ],
                        ),
                        TemplateNode(
                            id="pharmacology-target-list",
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
                    ],
                ),
                TemplateNode(
                    id="adme",
                    label="ADME and PK",
                    path=["admePk", "table"],
                    children=[
                        TemplateNode(id="adme-absorption", label="Absorption", path=["absorption"], type="field"),
                        TemplateNode(id="adme-half-life", label="Half-life", path=["halfLife"], type="field"),
                        TemplateNode(id="adme-protein-binding", label="Protein binding", path=["proteinBinding"], type="field"),
                        TemplateNode(id="adme-metabolism", label="Metabolism", path=["metabolism"], type="field"),
                        TemplateNode(id="adme-elimination", label="Route of elimination", path=["routeOfElimination"], type="field"),
                        TemplateNode(id="adme-volume", label="Volume of distribution", path=["volumeOfDistribution"], type="field"),
                        TemplateNode(id="adme-clearance", label="Clearance", path=["clearance"], type="field"),
                        TemplateNode(id="adme-pk-snapshot", label="PK snapshot", path=["pkSnapshot", "keyPoints"], type="array", limit=10),
                    ],
                ),
                TemplateNode(
                    id="formulation-handling",
                    label="Formulation and handling",
                    path=["formulationHandling"],
                    children=[
                        TemplateNode(
                            id="formulation-notes",
                            label="Notes",
                            path=["notes"],
                            type="array",
                            limit=6,
                            generation_id="formulation_notes",
                        )
                    ],
                ),
                TemplateNode(
                    id="regulatory-market",
                    label="Regulatory and market",
                    path=["regulatoryMarket"],
                    children=[
                        TemplateNode(
                            id="regulatory-summary",
                            label="Lifecycle summary",
                            path=["summary"],
                            type="field",
                            generation_id="lifecycle_summary",
                        ),
                        TemplateNode(id="regulatory-markets", label="Markets", path=["markets"], type="array", limit=20),
                        TemplateNode(
                            id="regulatory-classification",
                            label="Regulatory classification",
                            path=["regulatoryClassification"],
                            children=[
                                TemplateNode(id="reg-groups", label="Groups", path=["groups"], type="array", limit=10),
                                TemplateNode(id="reg-therapeutic", label="Therapeutic classes", path=["therapeuticClasses"], type="array", limit=6),
                                TemplateNode(id="reg-classification", label="Classification", path=["classification"], type="field"),
                                TemplateNode(
                                    id="reg-atc",
                                    label="ATC codes",
                                    path=["atcCodes"],
                                    type="array",
                                    limit=10,
                                    children=[TemplateNode(id="reg-atc-code", label="Code", path=["code"], type="field")],
                                ),
                            ],
                        ),
                        TemplateNode(id="regulatory-label-highlights", label="Label highlights", path=["labelHighlights"], type="array", limit=10),
                        TemplateNode(
                            id="regulatory-supply",
                            label="Supply chain",
                            path=["supplyChain"],
                            children=[
                                TemplateNode(
                                    id="supply-summary",
                                    label="Supply chain summary",
                                    path=["supplyChainSummary"],
                                    type="field",
                                    generation_id="supply_chain_summary",
                                ),
                                TemplateNode(id="supply-manufacturers", label="Manufacturers", path=["manufacturers"], type="array", limit=20),
                                TemplateNode(id="supply-packagers", label="Packagers", path=["packagers"], type="array", limit=20),
                                TemplateNode(id="supply-notes", label="External manufacturing notes", path=["externalManufacturingNotes"], type="field"),
                                TemplateNode(id="supply-pharmaoffer", label="Pharmaoffer suppliers", path=["pharmaofferSuppliers"], type="array", limit=20),
                            ],
                        ),
                    ],
                ),
                TemplateNode(
                    id="safety",
                    label="Safety and risks",
                    path=["safetyRisks"],
                    children=[
                        TemplateNode(id="safety-toxicity", label="Toxicity", path=["toxicity"], type="field"),
                        TemplateNode(
                            id="safety-warnings",
                            label="High level warnings",
                            path=["highLevelWarnings"],
                            type="array",
                            limit=6,
                            generation_id="safety_highlights",
                        ),
                    ],
                ),
            ],
        ),
        TemplateNode(
            id="seo",
            label="SEO",
            path=["seo"],
            children=[
                TemplateNode(id="seo-title", label="Title", path=["title"], type="field"),
                TemplateNode(
                    id="seo-meta",
                    label="Meta description",
                    path=["metaDescription"],
                    type="field",
                    generation_id="seo_description",
                ),
                TemplateNode(id="seo-keywords", label="Keywords", path=["keywords"], type="array", limit=25),
            ],
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

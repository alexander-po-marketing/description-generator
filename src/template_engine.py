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
    name="Technical profile",
    blocks=[
        TemplateNode(
            id="technical-profile",
            label="Technical profile",
            path=["technicalProfile"],
            children=[
                TemplateNode(
                    id="hero",
                    label="Hero",
                    path=["hero"],
                    children=[
                        TemplateNode(id="hero-title", label="Title", path=["title"], type="field"),
                        TemplateNode(
                            id="hero-short-desc",
                            label="Short description",
                            path=["shortDesc"],
                            type="field",
                            generation_id="summary_sentence",
                        ),
                        TemplateNode(id="hero-tags", label="Tags", path=["tags"], type="array", limit=6),
                        TemplateNode(
                            id="hero-facts",
                            label="Facts",
                            path=["facts"],
                            children=[
                                TemplateNode(id="fact-generic-name", label="Generic name", path=["genericName"], type="field"),
                                TemplateNode(id="fact-molecule-type", label="Molecule type", path=["moleculeType"], type="field"),
                                TemplateNode(id="fact-cas-number", label="CAS number", path=["casNumber"], type="field"),
                                TemplateNode(id="fact-drugbank-id", label="DrugBank ID", path=["drugbankId"], type="field"),
                                TemplateNode(id="fact-approval-status", label="Approval status", path=["approvalStatus"], type="field"),
                                TemplateNode(id="fact-atc-code", label="ATC code", path=["atcCode"], type="field"),
                            ],
                        ),
                    ],
                ),
                TemplateNode(
                    id="primary-indications",
                    label="Primary indications",
                    path=["primaryIndications"],
                    type="array",
                    limit=6,
                ),
                TemplateNode(
                    id="sections",
                    label="Sections",
                    path=["sections"],
                    children=[
                        TemplateNode(
                            id="clinical-overview",
                            label="Clinical overview",
                            path=["clinicalOverview"],
                            children=[
                                TemplateNode(
                                    id="clinical-summary",
                                    label="Summary",
                                    path=["summary"],
                                    type="field",
                                    generation_id="summary",
                                ),
                                TemplateNode(id="clinical-details", label="Details", path=["details"], type="array", limit=6),
                            ],
                        ),
                        TemplateNode(
                            id="identification-classification",
                            label="Identification & classification",
                            path=["identificationClassification"],
                            children=[
                                TemplateNode(id="identification-summary", label="Summary", path=["summary"], type="field"),
                                TemplateNode(id="identification-table", label="Table", path=["table"], type="group"),
                                TemplateNode(id="identification-details", label="Details", path=["details"], type="array", limit=6),
                            ],
                        ),
                        TemplateNode(
                            id="pharmacology-targets",
                            label="Pharmacology & targets",
                            path=["pharmacologyTargets"],
                            children=[
                                TemplateNode(
                                    id="pharmacology-summary",
                                    label="Summary",
                                    path=["summary"],
                                    type="field",
                                    generation_id="pharmacology_summary",
                                ),
                                TemplateNode(id="pharmacology-details", label="Details", path=["details"], type="array", limit=6),
                                TemplateNode(id="pharmacology-targets-table", label="Targets", path=["targets"], type="array", limit=20),
                            ],
                        ),
                        TemplateNode(
                            id="adme-pk",
                            label="ADME/PK",
                            path=["admePk"],
                            children=[
                                TemplateNode(id="adme-summary", label="Summary", path=["summary"], type="field"),
                                TemplateNode(id="adme-table", label="Table", path=["table"], type="group"),
                            ],
                        ),
                        TemplateNode(
                            id="formulation-handling",
                            label="Formulation & handling",
                            path=["formulationHandling"],
                            children=[
                                TemplateNode(
                                    id="formulation-summary",
                                    label="Summary",
                                    path=["summary"],
                                    type="field",
                                    generation_id="formulation_notes",
                                ),
                                TemplateNode(id="formulation-bullets", label="Bullets", path=["bullets"], type="array", limit=6),
                            ],
                        ),
                        TemplateNode(
                            id="regulatory-market",
                            label="Regulatory & market",
                            path=["regulatoryMarket"],
                            children=[
                                TemplateNode(
                                    id="regulatory-summary",
                                    label="Summary",
                                    path=["summary"],
                                    type="field",
                                    generation_id="lifecycle_summary",
                                ),
                                TemplateNode(
                                    id="regulatory-details",
                                    label="Details",
                                    path=["details"],
                                    type="array",
                                    limit=6,
                                    generation_id="supply_chain_summary",
                                ),
                            ],
                        ),
                        TemplateNode(
                            id="safety-risks",
                            label="Safety & risks",
                            path=["safetyRisks"],
                            children=[
                                TemplateNode(
                                    id="safety-summary",
                                    label="Summary",
                                    path=["summary"],
                                    type="field",
                                    generation_id="safety_highlights",
                                ),
                                TemplateNode(id="safety-warnings", label="Warnings", path=["warnings"], type="array", limit=6),
                                TemplateNode(id="safety-toxicity", label="Toxicity", path=["toxicity"], type="field"),
                            ],
                        ),
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
                    ],
                ),
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

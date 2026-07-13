"""
diagram_schema.py — Pydantic models for As-Is and To-Be diagram validation.

Prevents hallucination by enforcing strict structure on LLM-extracted diagrams.
"""

from pydantic import BaseModel, Field, field_validator


class DiagramNode(BaseModel):
    """A single node in a diagram (role, tool, process, etc.)."""
    id: str = Field(..., description="Unique node identifier")
    label: str = Field(..., description="Human-readable node label")
    node_type: str | None = Field(
        None, description="Node type: role, tool, process, platform, etc."
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or len(v.strip()) == 0:
            raise ValueError("Node id cannot be empty")
        return v.strip()

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        if not v or len(v.strip()) == 0:
            raise ValueError("Node label cannot be empty")
        return v.strip()


class DiagramEdge(BaseModel):
    """An edge (relationship) between two diagram nodes."""
    source: str = Field(..., description="Source node id")
    target: str = Field(..., description="Target node id")
    label: str | None = Field(None, description="Optional edge label")

    @field_validator("source", "target")
    @classmethod
    def validate_nodes(cls, v: str) -> str:
        if not v or len(v.strip()) == 0:
            raise ValueError("Node reference cannot be empty")
        return v.strip()


class DiagramNodeAsIs(DiagramNode):
    """As-Is node: must exist in the verified questionnaire."""
    pass


class DiagramNodeToBe(DiagramNode):
    """To-Be node: classified as KEPT, IMPROVED, REPLACED, or NEW."""
    status: str | None = Field(
        None,
        description="Classification: KEPT, IMPROVED, REPLACED, or NEW",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        valid = {"KEPT", "IMPROVED", "REPLACED", "NEW"}
        if v.upper() not in valid:
            raise ValueError(f"status must be one of {valid}")
        return v.upper()


class DiagramAsIs(BaseModel):
    """Validated As-Is diagram structure."""
    diagram_type: str = Field(..., description="people, process, or technology")
    nodes: list[DiagramNodeAsIs] = Field(default_factory=list)
    edges: list[DiagramEdge] = Field(default_factory=list)
    summary: str | None = Field(None, description="Brief architecture summary")

    @field_validator("diagram_type")
    @classmethod
    def validate_diagram_type(cls, v: str) -> str:
        valid = {"people", "process", "technology"}
        if v.lower() not in valid:
            raise ValueError(f"diagram_type must be one of {valid}")
        return v.lower()


class DiagramToBe(BaseModel):
    """Validated To-Be diagram structure with status annotations."""
    diagram_type: str = Field(..., description="people, process, or technology")
    nodes: list[DiagramNodeToBe] = Field(default_factory=list)
    edges: list[DiagramEdge] = Field(default_factory=list)
    summary: str | None = Field(None, description="Target-state summary")
    changes_summary: str | None = Field(
        None, description="Summary of changes from As-Is"
    )

    @field_validator("diagram_type")
    @classmethod
    def validate_diagram_type(cls, v: str) -> str:
        valid = {"people", "process", "technology"}
        if v.lower() not in valid:
            raise ValueError(f"diagram_type must be one of {valid}")
        return v.lower()

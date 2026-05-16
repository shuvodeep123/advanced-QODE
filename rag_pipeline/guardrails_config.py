"""
guardrails_config.py — Conversation policies & output validation.

Enforces:
  1. Diagram structure validation (nodes/edges only from As-Is when present)
  2. No hallucinated toolchain suggestions (stay within verified architecture)
  3. Policy-based conversation filtering (e.g., no refusals on valid requests)
"""

from pydantic import BaseModel, Field


class DiagramOutputPolicy(BaseModel):
    """Policy for diagram outputs: must have valid structure."""
    has_diagram: bool = Field(
        ..., description="Output contains at least one diagram (DOT or Mermaid)"
    )
    node_count: int = Field(
        ..., ge=1, description="Must have at least 1 node"
    )
    edge_count: int = Field(
        ..., ge=0, description="May have 0+ edges"
    )


class ToolchainPolicy(BaseModel):
    """Policy: toolchain suggestions must reference existing tools."""
    uses_existing_tools: bool = Field(
        ..., description="All tool recommendations must already exist in As-Is"
    )
    no_trendy_suggestions: bool = Field(
        ..., description="No random internet-sourced tools; stick to verified tech"
    )


class ConversationPolicy(BaseModel):
    """Policy: conversation rules (no harmful refusals, grounded responses)."""
    is_grounded: bool = Field(
        ..., description="Response grounded in provided context or Knowledge Graph"
    )
    is_respectful: bool = Field(
        ..., description="Response maintains professional tone"
    )


def validate_conversation(data: dict) -> bool:
    """Validate conversation response against quality policy."""
    try:
        ConversationPolicy(**data)
        return True
    except Exception:
        return False


# Policy rules for As-Is architecture groundedness
ASIS_GROUNDEDNESS_RULES = """
When a user requests diagram generation or analysis:

1. **Node Validation**: Every node in the To-Be diagram must be traceable to:
   - The As-Is architecture (if questionnaire data present), OR
   - A role/tool/process from the QODE Knowledge Graph

2. **Edge Validation**: Edges must represent actual relationships:
   - "tool A integrates with tool B" must be verifiable
   - No hypothetical or invented integrations

3. **New Nodes Rule**: Mark new nodes explicitly with status="NEW"
   - NEW nodes are allowed only when justified by the user request
   - NEW nodes must not duplicate existing As-Is functionality

4. **No Hallucinated Tooling**: For Technology discipline:
   - Do NOT recommend tools not present in the As-Is or Knowledge Graph
   - Focus on enhancing existing tools with AI/agentic capabilities
   - If external tool is needed, explicitly justify why

5. **Refusal Handling**: NEVER refuse valid requests
   - If questionnaire not loaded: use Knowledge Graph to generate best-practice diagrams
   - Label clearly: "Best-Practice To-Be Architecture (QODE Framework)"
"""

# Policy rules for conversation quality
CONVERSATION_QUALITY_RULES = """
1. **Grounding**: Every statement must cite context source:
   - "According to the Knowledge Graph..." OR
   - "From the As-Is questionnaire..." OR
   - "Best practice from QODE framework..."

2. **No Assumptions**: Never assume missing data
   - If a role/tool/process is absent, say so explicitly
   - Do not invent to fill gaps

3. **Respect User Intent**:
   - User asks for To-Be? Provide To-Be (never refuse)
   - User asks for gap analysis? Show all impacts (no warnings only)
   - User asks for quick wins? List them (no philosophical disclaimers)

4. **Structured Output**:
   - Use sections (## heading) for clarity
   - Use tables for multi-dimensional data (impact matrices, roadmaps)
   - Use diagrams (DOT + Mermaid) for architectural questions
"""

"""
graph_builder.py — QODE Knowledge Graph construction and persistence.

Builds a directed NetworkX graph representing structural relationships between
SDLC pillars, human roles, automation tools, and Q_Stories activities.
This graph is the backbone of the Graph-RAG retrieval layer, enabling the LLM
to reason across multi-hop connections that flat vector search cannot traverse.

Node types (stored as 'node_type' attribute):
    pillar   — one of the 9 SDLC pillars
    role     — a human role  (e.g. "Product Owner")
    tool     — an automation tool (e.g. "Jira")
    activity — a Q_Stories activity row from the Excel questionnaire

Edge relationship types (stored as 'rel' attribute):
    HAS_ROLE      : pillar   → role      (pillar owns this role)
    USES_TOOL     : pillar   → tool      (pillar uses this tool)
    PRECEDES      : pillar   → pillar    (sequential SDLC order 1→2→…→9)
    OWNS_ACTIVITY : role     → activity  (role is responsible for this activity)
    USED_IN       : tool     → activity  (tool is used in this activity)

Public API
----------
    PILLAR_DEFINITIONS : list[dict]  — authoritative structured pillar data

    QODEKnowledgeGraph
        .build_from_pillars() -> QODEKnowledgeGraph
        .add_excel_activities(excel_path) -> None
        .get_subgraph_text(seed_node_ids, hops) -> str
        .community_summaries() -> dict[str, str]
        .all_entity_labels() -> dict[str, str]
        .save(graph_path) -> None
        .load(graph_path) -> QODEKnowledgeGraph  [classmethod]
        .node_count : int
        .edge_count : int

    build_graph(excel_path=None) -> QODEKnowledgeGraph  [convenience]
    save_graph(graph, graph_path) -> None
    load_graph(graph_path) -> QODEKnowledgeGraph | None
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import networkx as nx
from . import eval_metrics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default persistence path
# ---------------------------------------------------------------------------
DEFAULT_GRAPH_PATH = "./graph_db/qode_graph.json"

# ---------------------------------------------------------------------------
# Stop-words to exclude from single-word entity label matching
# ---------------------------------------------------------------------------
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "with", "from", "that", "this", "have", "been", "their", "there",
        "about", "covers", "which", "these", "those", "after", "before",
        "management", "operations", "practices",  # too generic for QODE
    }
)

# ---------------------------------------------------------------------------
# Authoritative QODE pillar definitions — single source of truth for the graph
# Aligned with QODE_methodologies.md Section 3: Engineering Practices (9 practices)
# and Section 4: Three Propensities (Practice, Technology Usage, Collaboration)
# ---------------------------------------------------------------------------
PILLAR_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "pillar_1",
        "label": "Requirements Engineering",
        "pillar_num": 1,
        "diagram_type": "process",
        "roles": ["IT Product Owner", "Business Analyst", "IT Lead"],
        "tools": ["Jira", "Confluence", "Azure DevOps Boards"],
        "summary": (
            "Capturing, translating, categorizing, and integrating requirements; "
            "traceability automation."
        ),
    },
    {
        "id": "pillar_2",
        "label": "Code Engineering",
        "pillar_num": 2,
        "diagram_type": "technology",
        "roles": ["Developer", "Tech Lead"],
        "tools": ["GitHub", "GitLab", "Bitbucket", "SonarQube"],
        "summary": (
            "Modularity, microservices architecture, in-line code quality, "
            "model-driven code generation, application security."
        ),
    },
    {
        "id": "pillar_3",
        "label": "Data Engineering",
        "pillar_num": 3,
        "diagram_type": "technology",
        "roles": ["Data Architect", "Data Modeler"],
        "tools": ["DBaaS", "ETL Tools", "Data Pipeline", "Apache Spark"],
        "summary": (
            "Schema optimization, unstructured data management, data migration, "
            "data security, archival automation."
        ),
    },
    {
        "id": "pillar_4",
        "label": "Quality Engineering",
        "pillar_num": 4,
        "diagram_type": "technology",
        "roles": ["Tester", "QA Team", "QA Lead"],
        "tools": ["Selenium", "JUnit", "pytest", "TestNG", "Cypress"],
        "summary": (
            "TDD/BDD, in-sprint automation, regression and performance test automation, "
            "shift-left testing."
        ),
    },
    {
        "id": "pillar_5",
        "label": "Build & Release Engineering",
        "pillar_num": 5,
        "diagram_type": "process",
        "roles": ["Operations", "Release Team", "DevOps Lead"],
        "tools": ["Jenkins", "GitHub Actions", "CircleCI", "Nexus", "JFrog"],
        "summary": (
            "CI/CD frameworks, toolchain integration, zero-downtime deployment, "
            "release pipeline reliability."
        ),
    },
    {
        "id": "pillar_6",
        "label": "Environment Engineering",
        "pillar_num": 6,
        "diagram_type": "technology",
        "roles": ["Operations", "Infrastructure Team", "Cloud Engineer"],
        "tools": ["Terraform", "Ansible", "Puppet", "CloudFormation", "Helm"],
        "summary": (
            "Infrastructure-as-code, environment provisioning automation, "
            "configuration management, containerization, cloud."
        ),
    },
    {
        "id": "pillar_7",
        "label": "Service Operations Engineering",
        "pillar_num": 7,
        "diagram_type": "process",
        "roles": ["Operations", "Production Support", "Support Lead"],
        "tools": ["ServiceNow", "Jira", "Splunk", "ELK Stack"],
        "summary": (
            "Production monitoring, automated incident detection and resolution, "
            "feedback loops to SDLC, ITSM workflows."
        ),
    },
    {
        "id": "pillar_8",
        "label": "Security Engineering",
        "pillar_num": 8,
        "diagram_type": "process",
        "roles": ["IT Security Team", "Security Engineer"],
        "tools": ["Snyk", "Checkmarx", "OWASP ZAP", "Twistlock"],
        "summary": (
            "Application, data, infrastructure, and code security; "
            "vulnerability scanning; chaos engineering for security; DevSecOps."
        ),
    },
    {
        "id": "pillar_9",
        "label": "Reliability Engineering",
        "pillar_num": 9,
        "diagram_type": "process",
        "roles": ["Ops", "SRE"],
        "tools": ["Prometheus", "Grafana", "Datadog", "Dynatrace"],
        "summary": (
            "Monitoring-based failure detection, self-healing, chaos engineering, "
            "SLO/SLA management."
        ),
    },
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _node_id(node_type: str, label: str) -> str:
    """Return a normalised, stable node ID from *node_type* and *label*."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return f"{node_type}_{slug}"


# ---------------------------------------------------------------------------
# QODEKnowledgeGraph
# ---------------------------------------------------------------------------

class QODEKnowledgeGraph:
    """Directed knowledge graph for QODE domain entities and relationships.

    The graph stores SDLC pillars, human roles, automation tools, and
    questionnaire activities as nodes, connected by typed edges such as
    HAS_ROLE, USES_TOOL, PRECEDES, OWNS_ACTIVITY, and USED_IN.

    This structure allows multi-hop reasoning that flat vector search cannot
    perform — for example, finding all tools shared across two pillars, or
    tracing the complete critical path from planning to deployment.
    """

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def build_from_pillars(self) -> "QODEKnowledgeGraph":
        """Populate the graph from ``PILLAR_DEFINITIONS``.

        Creates pillar nodes, role nodes, tool nodes, and edges connecting
        them.  Also adds PRECEDES edges to encode the sequential SDLC order.

        Returns:
            self — enables method chaining.
        """
        pillar_ids = [p["id"] for p in PILLAR_DEFINITIONS]

        for pillar in PILLAR_DEFINITIONS:
            pid = pillar["id"]

            # Pillar node
            self._g.add_node(
                pid,
                node_type="pillar",
                label=pillar["label"],
                pillar_num=pillar["pillar_num"],
                diagram_type=pillar["diagram_type"],
                summary=pillar["summary"],
            )

            # Role nodes + HAS_ROLE edges
            for role_label in pillar["roles"]:
                rid = _node_id("role", role_label)
                if not self._g.has_node(rid):
                    self._g.add_node(rid, node_type="role", label=role_label)
                self._g.add_edge(pid, rid, rel="HAS_ROLE")

            # Tool nodes + USES_TOOL edges
            for tool_label in pillar["tools"]:
                tid = _node_id("tool", tool_label)
                if not self._g.has_node(tid):
                    self._g.add_node(tid, node_type="tool", label=tool_label)
                self._g.add_edge(pid, tid, rel="USES_TOOL")

        # PRECEDES edges: pillar 1 → 2 → 3 → … → 9
        for i in range(len(pillar_ids) - 1):
            self._g.add_edge(pillar_ids[i], pillar_ids[i + 1], rel="PRECEDES")

        logger.info(
            "Graph built from pillar definitions: %d nodes, %d edges",
            self._g.number_of_nodes(),
            self._g.number_of_edges(),
        )
        return self

    def add_excel_activities(self, excel_path: str | Path) -> None:
        """Add activity nodes from the Q_Stories Excel sheet.

        Each "Yes" row becomes an activity node.  Edges are created to the
        owning role (OWNS_ACTIVITY) and the automation tool (USED_IN) when
        those values are present in the row.

        Args:
            excel_path: Path to the QODE questionnaire ``.xlsm`` file.
        """
        try:
            import pandas as pd  # noqa: PLC0415 — optional lazy import

            df_raw = pd.read_excel(
                str(excel_path), sheet_name="Q_Stories", header=3
            ).iloc[2:]
        except Exception as exc:
            logger.warning(
                "Graph builder: could not read Q_Stories from '%s': %s",
                excel_path,
                exc,
            )
            return

        yes_df = df_raw[df_raw.get("Yes / No", df_raw.iloc[:, 1]) == "Yes"]
        activity_count = 0

        for _, row in yes_df.iterrows():
            s_num = str(row.get("S#", "")).strip()
            if not s_num or s_num.lower() == "nan":
                continue

            act_id = f"activity_s{s_num}"
            team = str(row.get("Team / owner role", "")).strip()
            tool = str(row.get("Automation tool", "")).strip()
            inp = str(row.get("Input", "")).strip()
            out = str(row.get("Output", "")).strip()
            criticality = str(row.get("Criticality", "")).strip()
            pred = str(row.get("Predecessor 1 (incl. INIT)", "")).strip()

            # Build a meaningful label
            if inp and out and inp.lower() != "nan" and out.lower() != "nan":
                label = f"Activity S{s_num}: {inp} → {out}"
            else:
                label = f"Activity S{s_num}"

            self._g.add_node(
                act_id,
                node_type="activity",
                label=label,
                s_num=s_num,
                team=team if team.lower() != "nan" else "",
                tool=tool if tool.lower() != "nan" else "",
                criticality=criticality if criticality.lower() != "nan" else "",
                predecessor=pred if pred.lower() != "nan" else "",
            )
            activity_count += 1

            # Role → activity edge
            if team and team.lower() not in ("nan", ""):
                rid = _node_id("role", team)
                if not self._g.has_node(rid):
                    self._g.add_node(rid, node_type="role", label=team)
                self._g.add_edge(rid, act_id, rel="OWNS_ACTIVITY")

            # Tool → activity edge
            if tool and tool.lower() not in ("nan", ""):
                tid = _node_id("tool", tool)
                if not self._g.has_node(tid):
                    self._g.add_node(tid, node_type="tool", label=tool)
                self._g.add_edge(tid, act_id, rel="USED_IN")

        logger.info(
            "Added %d activity nodes from Excel; graph now has %d nodes, %d edges",
            activity_count,
            self._g.number_of_nodes(),
            self._g.number_of_edges(),
        )

    # ------------------------------------------------------------------
    # Graph traversal
    # ------------------------------------------------------------------

    def get_subgraph_text(
        self,
        seed_node_ids: list[str],
        hops: int = 2,
        max_activity_nodes: int = 12,
    ) -> str:
        """Return a human-readable description of the neighbourhood.

        Performs undirected BFS from each seed node up to *hops* edges and
        serialises the discovered nodes and typed edges into structured text
        suitable for inclusion in an LLM prompt.

        Args:
            seed_node_ids:      Seed node IDs (from entity extraction).
            hops:               BFS depth (2 is recommended for QODE queries).
            max_activity_nodes: Cap on activity nodes shown (avoids bloat).

        Returns:
            A formatted multi-line string, or ``""`` when no seeds are valid.
        """
        if not seed_node_ids:
            return ""

        # Seed only from nodes that actually exist in the graph
        frontier: set[str] = set(seed_node_ids) & set(self._g.nodes)
        if not frontier:
            return ""

        visited: set[str] = set()

        for _ in range(hops):
            next_frontier: set[str] = set()
            for nid in frontier:
                if nid not in visited:
                    visited.add(nid)
                    # Traverse both directions (undirected BFS over a directed graph)
                    next_frontier.update(self._g.successors(nid))
                    next_frontier.update(self._g.predecessors(nid))
            frontier = next_frontier - visited

        visited.update(frontier)
        visited = {n for n in visited if self._g.has_node(n)}

        lines: list[str] = ["[QODE Knowledge Graph — Relevant Subgraph]"]

        # Render by node type in a defined order for readability
        for node_type, section_title in (
            ("pillar", "SDLC PILLARS"),
            ("role", "ROLES"),
            ("tool", "TOOLS"),
            ("activity", "ACTIVITIES"),
        ):
            nodes_of_type = sorted(
                n for n in visited if self._g.nodes[n].get("node_type") == node_type
            )
            if not nodes_of_type:
                continue

            # Cap activity nodes to avoid flooding the context window
            if node_type == "activity":
                nodes_of_type = nodes_of_type[:max_activity_nodes]

            lines.append(f"\n{section_title}:")
            for nid in nodes_of_type:
                attrs = self._g.nodes[nid]
                label = attrs.get("label", nid)
                summary = attrs.get("summary", "")
                line = f"  • {label}"
                if summary:
                    line += f"  —  {summary}"
                lines.append(line)

                # Show outgoing edges to other visited nodes
                for succ in self._g.successors(nid):
                    if succ in visited:
                        rel = self._g.edges[nid, succ].get("rel", "RELATED_TO")
                        succ_label = self._g.nodes[succ].get("label", succ)
                        lines.append(f"      ──[{rel}]──▶ {succ_label}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Community summaries
    # ------------------------------------------------------------------

    def evaluate_propensities(self, pillar_id: str) -> eval_metrics.PropensityScore | None:
        """Compute propensity scores for a given pillar based on roles and tools.

        Analyzes tool propensity category and role seniority to derive Practice,
        Technology Usage, and Collaboration scores for a pillar.

        Args:
            pillar_id: Node ID of the pillar (e.g. "pillar_3")

        Returns:
            PropensityScore with (practice, technology_usage, collaboration) levels,
            or None if pillar not found.
        """
        if not self._g.has_node(pillar_id):
            logger.warning("Pillar %s not found in graph", pillar_id)
            return None

        # Collect tool categories for this pillar
        tool_nodes = [
            n for n in self._g.successors(pillar_id)
            if self._g.nodes[n].get("node_type") == "tool"
        ]
        tool_labels = [self._g.nodes[n].get("label", "") for n in tool_nodes]

        # Infer technology propensity from tool categories
        tech_propensity = self._infer_technology_propensity(tool_labels)

        # Default practice propensity (baseline: medium)
        practice_propensity = eval_metrics.PropensityLevel.MEDIUM

        # Default collaboration propensity (baseline: medium)
        collaboration_propensity = eval_metrics.PropensityLevel.MEDIUM

        return eval_metrics.PropensityScore(
            practice=practice_propensity,
            technology_usage=tech_propensity,
            collaboration=collaboration_propensity,
        )

    def _infer_technology_propensity(self, tool_labels: list[str]) -> eval_metrics.PropensityLevel:
        """Infer technology usage propensity from tool categories.

        Mapping:
        - Documentation/UI-based (Jira, ServiceNow) → Low
        - Configuration-centric (Jenkins, Ansible) → Medium
        - Coding-centric (Jenkinsfile, Terraform) → High
        """
        coding_tools = {"terraform", "ansible", "jenkinsfile", "helm", "docker", "kubernetes"}
        config_tools = {"jenkins", "github actions", "circleci", "jira", "servicenow"}
        doc_tools = {"confluence", "word", "excel", "sharepoint"}

        lower_labels = [l.lower() for l in tool_labels]
        has_coding = any(any(ct in label for ct in coding_tools) for label in lower_labels)
        has_config = any(any(ct in label for ct in config_tools) for label in lower_labels)
        has_doc = any(any(dt in label for dt in doc_tools) for label in lower_labels)

        if has_coding:
            return eval_metrics.PropensityLevel.HIGH
        elif has_config:
            return eval_metrics.PropensityLevel.MEDIUM
        else:
            return eval_metrics.PropensityLevel.LOW

    def community_summaries(self) -> dict[str, str]:
        """Return a per-pillar prose summary including roles, tools, and position.

        Used for global questions (e.g. "summarise our DevSecOps landscape")
        that require an overview of every community rather than a targeted
        subgraph traversal.

        Returns:
            A dict mapping ``pillar_id`` → formatted summary string.
        """
        summaries: dict[str, str] = {}

        for pillar in PILLAR_DEFINITIONS:
            pid = pillar["id"]
            if not self._g.has_node(pid):
                continue

            roles = sorted(
                self._g.nodes[n].get("label", n)
                for n in self._g.successors(pid)
                if self._g.nodes[n].get("node_type") == "role"
            )
            tools = sorted(
                self._g.nodes[n].get("label", n)
                for n in self._g.successors(pid)
                if self._g.nodes[n].get("node_type") == "tool"
            )
            precedes_labels = [
                self._g.nodes[n].get("label", n)
                for n in self._g.successors(pid)
                if self._g.edges[pid, n].get("rel") == "PRECEDES"
            ]
            preceded_by_labels = [
                self._g.nodes[n].get("label", n)
                for n in self._g.predecessors(pid)
                if self._g.edges[n, pid].get("rel") == "PRECEDES"
            ]

            parts = [f"Pillar {pillar['pillar_num']} — {pillar['label']}"]
            parts.append(f"  Description: {pillar['summary']}")
            if preceded_by_labels:
                parts.append(f"  Comes after: {', '.join(preceded_by_labels)}")
            if precedes_labels:
                parts.append(f"  Leads into:  {', '.join(precedes_labels)}")
            if roles:
                parts.append(f"  Key roles:   {', '.join(roles)}")
            if tools:
                parts.append(f"  Tools used:  {', '.join(tools)}")

            summaries[pid] = "\n".join(parts)

        return summaries

    # ------------------------------------------------------------------
    # Entity label index (used by EntityExtractor)
    # ------------------------------------------------------------------

    def all_entity_labels(self) -> dict[str, str]:
        """Return a mapping of lowercase label variants → node_id.

        Covers full node labels, pillar number forms ("pillar 3"), and
        significant single-word keywords extracted from pillar labels.
        Used by ``EntityExtractor`` for fast, deterministic entity lookup.

        Returns:
            Dict where keys are lowercase label strings and values are node IDs.
            When multiple labels could map to the same node, the more specific
            (longer) match is preferred via insertion order.
        """
        label_map: dict[str, str] = {}

        for nid, attrs in self._g.nodes(data=True):
            label: str = attrs.get("label", "")
            node_type: str = attrs.get("node_type", "")

            if not label:
                continue

            # Full label (lowercase) — highest priority
            label_map[label.lower()] = nid

            if node_type == "pillar":
                pillar_num = attrs.get("pillar_num")
                if pillar_num:
                    label_map[f"pillar {pillar_num}"] = nid
                    label_map[f"p{pillar_num}"] = nid

                # Single significant keywords from the pillar label
                for word in re.findall(r"[a-z]{5,}", label.lower()):
                    if word not in _STOP_WORDS:
                        # setdefault: first (lower-numbered) pillar wins ties
                        label_map.setdefault(word, nid)

            elif node_type == "tool":
                # Tools are often referenced by lowercase short name (e.g. "sonar")
                # Add the first token if it's at least 4 characters
                first_token = re.split(r"[\s/]", label)[0].lower()
                if len(first_token) >= 4:
                    label_map.setdefault(first_token, nid)

        return label_map

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, graph_path: str | Path) -> None:
        """Persist the graph to a JSON file using NetworkX node-link format.

        The parent directory is created if it does not exist.

        Args:
            graph_path: Destination file path (e.g. ``"./graph_db/qode_graph.json"``).
        """
        path = Path(graph_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self._g)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        logger.info(
            "Knowledge graph saved → %s  (%d nodes, %d edges)",
            path,
            self._g.number_of_nodes(),
            self._g.number_of_edges(),
        )

    @classmethod
    def load(cls, graph_path: str | Path) -> "QODEKnowledgeGraph":
        """Load a previously saved graph from *graph_path*.

        Args:
            graph_path: Path to the JSON file produced by :meth:`save`.

        Returns:
            A fully reconstructed ``QODEKnowledgeGraph`` instance.

        Raises:
            FileNotFoundError: If *graph_path* does not exist.
            ValueError: If the file cannot be deserialised.
        """
        path = Path(graph_path)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        instance = cls()
        directed = data.get("directed", True)
        instance._g = nx.node_link_graph(data, directed=directed)
        logger.info(
            "Knowledge graph loaded ← %s  (%d nodes, %d edges)",
            path,
            instance._g.number_of_nodes(),
            instance._g.number_of_edges(),
        )
        return instance

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        """Total number of nodes in the graph."""
        return self._g.number_of_nodes()

    @property
    def edge_count(self) -> int:
        """Total number of edges in the graph."""
        return self._g.number_of_edges()


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def build_graph(
    excel_path: str | Path | None = None,
) -> QODEKnowledgeGraph:
    """Build a fresh QODE knowledge graph.

    Always constructs the pillar/role/tool graph from ``PILLAR_DEFINITIONS``.
    Optionally enriches it with activity nodes from the Excel questionnaire.

    Args:
        excel_path: Path to the QODE questionnaire ``.xlsm`` file, or ``None``
                    to build the base graph only.

    Returns:
        A fully populated ``QODEKnowledgeGraph``.
    """
    graph = QODEKnowledgeGraph().build_from_pillars()
    if excel_path is not None:
        graph.add_excel_activities(excel_path)
    return graph


def save_graph(
    graph: QODEKnowledgeGraph,
    graph_path: str | Path = DEFAULT_GRAPH_PATH,
) -> None:
    """Save *graph* to *graph_path* (thin wrapper over :meth:`QODEKnowledgeGraph.save`)."""
    graph.save(graph_path)


def load_graph(
    graph_path: str | Path = DEFAULT_GRAPH_PATH,
) -> QODEKnowledgeGraph | None:
    """Load a graph from *graph_path*, returning ``None`` on any failure.

    Args:
        graph_path: Path to the previously saved JSON file.

    Returns:
        A loaded ``QODEKnowledgeGraph``, or ``None`` if the file does not exist
        or cannot be deserialised.
    """
    path = Path(graph_path)
    if not path.exists():
        logger.warning(
            "Graph file not found at '%s' — run ingest to build the graph.", path
        )
        return None
    try:
        return QODEKnowledgeGraph.load(path)
    except Exception as exc:
        logger.error("Failed to load graph from '%s': %s", path, exc)
        return None

"""
neo4j_sync.py — Optional Neo4j second read path for advanced-QODE.

This module provides two capabilities:

1. **Graph sync** — after each ``ingest_all()`` run the NetworkX
   ``QODEKnowledgeGraph`` is mirrored into Neo4j using MERGE statements so
   Neo4j always reflects the latest state of the graph.

2. **Cypher retrieval** — ``Neo4jSync.query_subgraph_text()`` runs a
   variable-length path Cypher query from seed entity nodes and returns
   structured text in the same format as
   ``QODEKnowledgeGraph.get_subgraph_text()``.  The result is merged with
   the NetworkX BFS result by ``HybridGraphRetriever``, giving two
   independent subgraph views that are then deduplicated by content hash.

Neo4j is **fully optional**.  When the three environment variables
``NEO4J_URI``, ``NEO4J_USER``, ``NEO4J_PASSWORD`` are absent (or when the
connection fails), ``get_neo4j_sync()`` returns ``None`` and all callers
fall back to the NetworkX-only path transparently.

Configuration
-------------
Set the following environment variables (or add them to ``.env``):

    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=your-password

    # Optional — leave unset to use the default database
    NEO4J_DATABASE=neo4j

Public API
----------
    Neo4jSync(uri, user, password, database)
        .sync_graph(graph: QODEKnowledgeGraph) -> None
        .query_subgraph_text(seed_node_ids, hops) -> str
        .is_available() -> bool
        .close() -> None

    get_neo4j_sync() -> Neo4jSync | None
        Module-level factory — reads env vars, returns None when unconfigured.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .graph_builder import QODEKnowledgeGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Node-type → Neo4j secondary label (whitelist prevents Cypher injection)
# ---------------------------------------------------------------------------
_NODE_TYPE_LABELS: dict[str, str] = {
    "pillar": "Pillar",
    "role": "Role",
    "tool": "Tool",
    "activity": "Activity",
}

# ---------------------------------------------------------------------------
# Known QODE relationship types.
# Each key maps to a Cypher MERGE template for that relationship type.
# Using string interpolation of a *whitelisted* value is safe here.
# ---------------------------------------------------------------------------
_KNOWN_REL_TYPES: frozenset[str] = frozenset(
    {"HAS_ROLE", "USES_TOOL", "PRECEDES", "OWNS_ACTIVITY", "USED_IN"}
)
_FALLBACK_REL_TYPE = "RELATED_TO"


def _safe_rel_type(rel: str) -> str:
    """Return *rel* if it is a known relationship type, else the fallback."""
    return rel if rel in _KNOWN_REL_TYPES else _FALLBACK_REL_TYPE


# ---------------------------------------------------------------------------
# Neo4jSync
# ---------------------------------------------------------------------------

class Neo4jSync:
    """Bidirectional bridge between QODEKnowledgeGraph and a Neo4j instance.

    Provides two core operations:
    - :meth:`sync_graph`           — mirror the NetworkX graph into Neo4j.
    - :meth:`query_subgraph_text`  — Cypher BFS returning formatted context.

    Thread safety:
        ``neo4j.GraphDatabase.driver`` is thread-safe for concurrent reads.
        :meth:`sync_graph` performs writes and should be called from a
        single thread (e.g. the ingest path).
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
    ) -> None:
        from neo4j import GraphDatabase  # type: ignore[import]

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database
        logger.info("Neo4jSync: connected to %s (database=%s)", uri, database)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if the Neo4j driver can reach the server."""
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.debug("Neo4j connectivity check failed: %s", exc)
            return False

    def sync_graph(self, graph: "QODEKnowledgeGraph") -> None:
        """Mirror *graph* into Neo4j using MERGE (upsert) semantics.

        All nodes and edges from the NetworkX ``QODEKnowledgeGraph`` are
        synchronised.  Existing Neo4j nodes/relationships are updated in-place
        rather than deleted and re-created, so live queries against Neo4j
        remain available during sync.

        Runs within a single write transaction per batch for efficiency.

        Args:
            graph: The fully built ``QODEKnowledgeGraph`` after ingest.
        """
        # Expose the internal NetworkX DiGraph for iteration
        nx_graph = graph._g  # noqa: SLF001 — intentional internal access

        with self._driver.session(database=self._database) as session:
            # 1. Upsert all nodes
            for node_id, attrs in nx_graph.nodes(data=True):
                self._upsert_node(session, node_id, attrs)

            # 2. Upsert all edges grouped by relationship type
            edges_by_rel: dict[str, list[tuple[str, str]]] = {}
            for src, tgt, edge_data in nx_graph.edges(data=True):
                rel = _safe_rel_type(edge_data.get("rel", _FALLBACK_REL_TYPE))
                edges_by_rel.setdefault(rel, []).append((src, tgt))

            for rel_type, pairs in edges_by_rel.items():
                self._upsert_edges(session, rel_type, pairs)

        logger.info(
            "Neo4jSync: synced %d nodes and %d edges",
            nx_graph.number_of_nodes(),
            nx_graph.number_of_edges(),
        )

    def query_subgraph_text(
        self,
        seed_node_ids: list[str],
        hops: int = 2,
        max_activity_nodes: int = 12,
    ) -> str:
        """Return a formatted subgraph context string via Cypher BFS.

        Runs a variable-length path query from each seed node up to *hops*
        edges (undirected) and serialises the discovered nodes and edges into
        the same structured text format as
        ``QODEKnowledgeGraph.get_subgraph_text()``.

        Args:
            seed_node_ids:      List of ``node_id`` values to start from.
            hops:               Maximum traversal depth (default 2).
            max_activity_nodes: Cap on activity nodes to avoid context bloat.

        Returns:
            A formatted multi-line string, or ``""`` when nothing is found.
        """
        if not seed_node_ids:
            return ""

        with self._driver.session(database=self._database) as session:
            # --- Discover neighbourhood nodes ---
            node_rows = session.run(
                """
                UNWIND $seed_ids AS sid
                MATCH (start:QodeNode {node_id: sid})
                MATCH (start)-[*0..{hops}]-(neighbor:QodeNode)
                RETURN DISTINCT
                    neighbor.node_id   AS node_id,
                    neighbor.node_type AS node_type,
                    neighbor.label     AS label,
                    neighbor.summary   AS summary
                """.replace("{hops}", str(int(hops))),
                seed_ids=seed_node_ids,
            ).data()

        if not node_rows:
            return ""

        # Collect discovered node IDs for edge query
        visited_ids: list[str] = [
            r["node_id"] for r in node_rows if r.get("node_id")
        ]

        with self._driver.session(database=self._database) as session:
            # --- Discover edges between discovered nodes ---
            edge_rows = session.run(
                """
                UNWIND $node_ids AS nid
                MATCH (a:QodeNode {node_id: nid})-[r]->(b:QodeNode)
                WHERE b.node_id IN $node_ids
                RETURN
                    a.node_id AS source_id,
                    a.label   AS source_label,
                    type(r)   AS rel_type,
                    b.label   AS target_label
                """,
                node_ids=visited_ids,
            ).data()

        return self._format_subgraph_text(
            node_rows, edge_rows, max_activity_nodes
        )

    def close(self) -> None:
        """Close the underlying Neo4j driver and release resources."""
        self._driver.close()
        logger.debug("Neo4jSync: driver closed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _upsert_node(self, session, node_id: str, attrs: dict) -> None:
        """MERGE a single node into Neo4j with all its properties."""
        node_type = attrs.get("node_type", "")
        extra_label = _NODE_TYPE_LABELS.get(node_type, "")

        # Build a safe props dict (all attrs + explicit node_id)
        props = {k: v for k, v in attrs.items() if isinstance(v, (str, int, float, bool))}
        props["node_id"] = node_id

        if extra_label:
            cypher = (
                f"MERGE (n:QodeNode:{extra_label} {{node_id: $node_id}}) "
                "SET n += $props"
            )
        else:
            cypher = (
                "MERGE (n:QodeNode {node_id: $node_id}) "
                "SET n += $props"
            )

        session.run(cypher, node_id=node_id, props=props)

    def _upsert_edges(
        self, session, rel_type: str, pairs: list[tuple[str, str]]
    ) -> None:
        """MERGE a batch of edges of the same relationship type."""
        # rel_type has already been whitelisted by _safe_rel_type()
        cypher = (
            f"UNWIND $pairs AS pair "
            f"MATCH (a:QodeNode {{node_id: pair[0]}}), (b:QodeNode {{node_id: pair[1]}}) "
            f"MERGE (a)-[:{rel_type}]->(b)"
        )
        session.run(cypher, pairs=[[s, t] for s, t in pairs])

    @staticmethod
    def _format_subgraph_text(
        node_rows: list[dict],
        edge_rows: list[dict],
        max_activity_nodes: int,
    ) -> str:
        """Serialise Neo4j query results into structured context text."""
        # Group edges by source label for lookup
        outgoing: dict[str, list[tuple[str, str]]] = {}
        for er in edge_rows:
            src_label = er.get("source_label", "")
            rel_type = er.get("rel_type", "RELATED_TO")
            tgt_label = er.get("target_label", "")
            outgoing.setdefault(src_label, []).append((rel_type, tgt_label))

        lines: list[str] = ["[QODE Knowledge Graph — Neo4j Subgraph]"]

        for node_type, section_title in (
            ("pillar", "SDLC PILLARS"),
            ("role", "ROLES"),
            ("tool", "TOOLS"),
            ("activity", "ACTIVITIES"),
        ):
            nodes_of_type = sorted(
                (r for r in node_rows if r.get("node_type") == node_type),
                key=lambda r: r.get("label", ""))

            if not nodes_of_type:
                continue

            if node_type == "activity":
                nodes_of_type = nodes_of_type[:max_activity_nodes]

            lines.append(f"\n{section_title}:")
            for row in nodes_of_type:
                label = row.get("label") or row.get("node_id", "")
                summary = row.get("summary") or ""
                line = f"  • {label}"
                if summary:
                    line += f"  —  {summary}"
                lines.append(line)

                for rel_type, tgt_label in outgoing.get(label, []):
                    lines.append(f"      ──[{rel_type}]──▶ {tgt_label}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

_NEO4J_SYNC_INSTANCE: "Neo4jSync | None" = None
_NEO4J_SYNC_CHECKED: bool = False


def get_neo4j_sync() -> "Neo4jSync | None":
    """Return a cached ``Neo4jSync`` instance, or ``None`` if unconfigured.

    Reads ``NEO4J_URI``, ``NEO4J_USER``, ``NEO4J_PASSWORD`` and optionally
    ``NEO4J_DATABASE`` from the environment.  Returns ``None`` (silently) when
    any required variable is absent or when the connection check fails.

    The instance is cached so subsequent calls return the same object without
    re-connecting.

    Returns:
        A ready ``Neo4jSync`` instance, or ``None``.
    """
    global _NEO4J_SYNC_INSTANCE, _NEO4J_SYNC_CHECKED  # noqa: PLW0603

    if _NEO4J_SYNC_CHECKED:
        return _NEO4J_SYNC_INSTANCE

    _NEO4J_SYNC_CHECKED = True

    uri = os.environ.get("NEO4J_URI", "")
    user = os.environ.get("NEO4J_USER", "")
    password = os.environ.get("NEO4J_PASSWORD", "")

    if not (uri and user and password):
        logger.info(
            "Neo4j not configured (NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD absent) "
            "— running NetworkX-only graph retrieval."
        )
        return None

    database = os.environ.get("NEO4J_DATABASE", "neo4j")

    try:
        sync = Neo4jSync(uri=uri, user=user, password=password, database=database)
        if not sync.is_available():
            logger.warning(
                "Neo4j configured but unreachable at '%s' "
                "— falling back to NetworkX-only graph retrieval.",
                uri,
            )
            sync.close()
            return None
        _NEO4J_SYNC_INSTANCE = sync
        logger.info("Neo4jSync ready (uri=%s, database=%s)", uri, database)
    except Exception as exc:
        logger.warning(
            "Neo4j initialisation failed: %s — NetworkX-only mode active.", exc
        )

    return _NEO4J_SYNC_INSTANCE


def reset_neo4j_sync_cache() -> None:
    """Reset the cached ``Neo4jSync`` singleton (useful in tests).

    Closes the existing driver if present, then clears the cache so the next
    :func:`get_neo4j_sync` call re-reads environment variables.
    """
    global _NEO4J_SYNC_INSTANCE, _NEO4J_SYNC_CHECKED  # noqa: PLW0603
    if _NEO4J_SYNC_INSTANCE is not None:
        try:
            _NEO4J_SYNC_INSTANCE.close()
        except Exception:
            pass
    _NEO4J_SYNC_INSTANCE = None
    _NEO4J_SYNC_CHECKED = False

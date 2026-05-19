"""
entity_extractor.py — QODE entity extraction from natural language queries.

Identifies references to QODE pillars, human roles and automation tools
in a free-text query using the knowledge graph's entity label index.
No external LLM call is required — extraction is deterministic keyword matching,
making it fast and suitable for the hot path of every retrieval request.

Strategy:
    1. Build an entity label map from the knowledge graph (label → node_id).
    2. For each query, attempt greedy longest-match substring search.
    3. Deduplicate and sort matches by match-string length (longer = more specific).

Public API
----------
    EntityExtractor(graph: QODEKnowledgeGraph)
    EntityExtractor.extract(query: str) -> list[str]
        Returns a deduplicated list of graph node_ids matching entities
        mentioned in the query, ordered by specificity (most specific first).
"""

from __future__ import annotations

from .graph_builder import QODEKnowledgeGraph

# Minimum number of characters a label must have to be considered for matching.
# Avoids spurious matches on very short tokens like "qa" or "p1".
_MIN_LABEL_LEN = 3


class EntityExtractor:
    """Keyword-based QODE entity extractor backed by the knowledge graph.

    Accepts a ``QODEKnowledgeGraph`` at construction time and builds an
    internal label → node_id index.  Each call to :meth:`extract` scans the
    query for any matching label and returns the corresponding node IDs.

    Thread safety:
        ``EntityExtractor`` instances are read-only after construction and safe
        to call from multiple threads concurrently.
    """

    def __init__(self, graph: QODEKnowledgeGraph) -> None:
        # Build the label map once at construction time.
        # Keys are lowercase label strings; values are graph node IDs.
        self._label_map: dict[str, str] = graph.all_entity_labels()

    def extract(self, query: str) -> list[str]:
        """Return a deduplicated list of node IDs referenced in *query*.

        Uses greedy longest-match: when multiple labels match, longer matches
        are considered more specific and preferred.  A node can only appear
        once in the result regardless of how many of its labels match.

        Args:
            query: The user's natural-language query string.

        Returns:
            A list of graph node IDs, ordered from most-specific to
            least-specific match.  Returns an empty list when no QODE
            entities are detected.
        """
        lower_query = query.lower()

        # node_id → length of the longest label that matched it
        best_match_len: dict[str, int] = {}

        for label, node_id in self._label_map.items():
            if len(label) < _MIN_LABEL_LEN:
                continue
            if label in lower_query:
                current_best = best_match_len.get(node_id, 0)
                if len(label) > current_best:
                    best_match_len[node_id] = len(label)

        # Sort by match length descending so most-specific entities come first
        return [
            node_id
            for node_id, _ in sorted(best_match_len.items(), key=lambda x: -x[1])
        ]

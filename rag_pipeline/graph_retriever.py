"""
graph_retriever.py — Hybrid Graph + Vector retrieval for advanced-QODE.

Combines structural multi-hop graph traversal with ChromaDB vector similarity
search to provide richer, more accurate context for the LLM than either
approach could deliver alone.

Retrieval strategy
------------------
1. **Entity extraction** — identify QODE entities (pillars, roles, tools) in
   the query using the knowledge graph's label index (no LLM call needed).

2. **Graph traversal** — perform undirected BFS up to *graph_hops* edges from
   each matched entity, serialise the discovered subgraph into structured text.

3. **Global fallback** — when no specific entities are found but the query
   looks like a global question ("overall", "all pillars", etc.), return
   community summaries for every pillar instead.

4. **Vector search** — run a ChromaDB cosine-similarity query for semantic
   coverage on long-tail questions not covered by the graph.

5. **Merge & deduplicate** — graph context comes first (structural, exact),
   followed by vector context (semantic).  Duplicate chunks are eliminated
   by content hash.

Public API
----------
    HybridGraphRetriever(graph, chroma_path)
    HybridGraphRetriever.retrieve(query, k, diagram_type, graph_hops) -> list[dict]
        Each dict has keys: text, metadata, distance, source ("graph"|"vector")

    get_retriever(graph_path, chroma_path) -> HybridGraphRetriever
        Module-level singleton factory — caches one retriever per path pair.

    invalidate_cache(graph_path, chroma_path) -> None
        Evict a cached retriever so it reloads from disk on the next call.
        Call this immediately after re-ingesting data.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Optional

from .entity_extractor import EntityExtractor
from .graph_builder import (
    DEFAULT_GRAPH_PATH,
    QODEKnowledgeGraph,
    build_graph,
    load_graph,
)
from .retriever import retrieve as _vector_retrieve

if TYPE_CHECKING:
    from .neo4j_sync import Neo4jSync

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global query keywords that trigger community-summary mode
# ---------------------------------------------------------------------------
_GLOBAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "all", "every", "entire", "whole", "overall", "across",
        "summary", "summarise", "summarize", "overview", "landscape",
        "maturity", "full", "complete", "each pillar", "all pillars",
    }
)

# ---------------------------------------------------------------------------
# Module-level singleton cache — one retriever per (graph_path, chroma_path)
# ---------------------------------------------------------------------------
_RETRIEVER_CACHE: dict[str, "HybridGraphRetriever"] = {}


class HybridGraphRetriever:
    """Production-grade hybrid retriever for the QODE Graph-RAG pipeline.

    Combines structured graph traversal with vector similarity search.
    When Neo4j is configured (``NEO4J_URI`` / ``NEO4J_USER`` /
    ``NEO4J_PASSWORD`` env vars present), a Cypher BFS query is run
    alongside the NetworkX BFS and the results are merged and deduplicated
    by content hash, providing two independent structural views.

    Each retrieved context chunk is tagged with ``"source": "graph"``,
    ``"source": "neo4j"``, or ``"source": "vector"`` so the prompt builder
    can render them in separate, labelled sections.

    Thread safety:
        After construction the retriever is effectively read-only.
        It is safe to call :meth:`retrieve` from multiple threads simultaneously
        as long as the underlying ChromaDB collection supports concurrent reads
        (which the default PersistentClient does).
    """

    def __init__(
        self,
        graph: QODEKnowledgeGraph,
        chroma_path: str = "./chroma_db",
        neo4j_sync: "Neo4jSync | None" = None,
    ) -> None:
        self._graph = graph
        self._chroma_path = chroma_path
        self._extractor = EntityExtractor(graph)
        self._neo4j: "Neo4jSync | None" = neo4j_sync
        # Pre-compute community summaries once at construction time
        self._community_summaries: dict[str, str] = graph.community_summaries()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        k: int = 5,
        diagram_type: Optional[str] = None,
        graph_hops: int = 2,
    ) -> list[dict]:
        """Return hybrid context chunks for *query*.

        Graph context is placed first (structural, high-precision), followed
        by vector context (semantic, high-recall).  Duplicate chunks are
        removed by content hash so the LLM never sees the same text twice.

        Args:
            query:        The user's natural-language question.
            k:            Number of vector results to retrieve from ChromaDB.
            diagram_type: Optional diagram-type filter for the vector search
                          (``"process"``, ``"people"``, ``"technology"``).
            graph_hops:   BFS depth for graph traversal (default 2).

        Returns:
            A list of context dicts, each with:
                ``text``      : str   — context content
                ``metadata``  : dict  — provenance metadata
                ``distance``  : float — relevance score (0 = most relevant)
                ``source``    : str   — ``"graph"`` or ``"vector"``
        """
        results: list[dict] = []
        seen_hashes: set[str] = set()

        # 1. Graph-traversal context (structural, exact-match)
        for chunk in self._graph_context(query, hops=graph_hops):
            h = _content_hash(chunk["text"])
            if h not in seen_hashes:
                seen_hashes.add(h)
                results.append(chunk)

        # 2. Vector context (semantic, broad coverage)
        for chunk in self._vector_context(query, k=k, diagram_type=diagram_type):
            h = _content_hash(chunk["text"])
            if h not in seen_hashes:
                seen_hashes.add(h)
                results.append(chunk)

        return results

    def global_summary(self) -> str:
        """Return a concatenated text of all pillar community summaries.

        Useful for building a static "knowledge overview" section in the
        system prompt, independent of the user query.
        """
        return "\n\n".join(self._community_summaries.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _graph_context(self, query: str, hops: int) -> list[dict]:
        """Extract entities from *query* and return graph-traversal chunks.

        Produces up to two chunks:
        1. **NetworkX BFS** — always present when entities are matched.
        2. **Neo4j Cypher BFS** — added when a ``Neo4jSync`` instance is
           available; tagged ``source="neo4j"`` so callers can distinguish it.
        Both chunks are deduplicated by content hash in :meth:`retrieve`.
        """
        entity_ids = self._extractor.extract(query)

        if not entity_ids:
            # No specific entities — check for global/overview intent
            lower = query.lower()
            if any(kw in lower for kw in _GLOBAL_KEYWORDS):
                return [
                    {
                        "text": summary,
                        "metadata": {
                            "source": "graph_community_summary",
                            "pillar_id": pid,
                        },
                        "distance": 0.0,
                        "source": "graph",
                    }
                    for pid, summary in self._community_summaries.items()
                ]
            return []

        results: list[dict] = []

        # 1. NetworkX BFS (always)
        subgraph_text = self._graph.get_subgraph_text(entity_ids, hops=hops)
        if subgraph_text:
            results.append(
                {
                    "text": subgraph_text,
                    "metadata": {
                        "source": "graph_traversal",
                        "seed_entities": ", ".join(entity_ids[:5]),
                        "hops": str(hops),
                    },
                    "distance": 0.0,
                    "source": "graph",
                }
            )

        # 2. Neo4j Cypher BFS (optional second read path)
        if self._neo4j is not None:
            try:
                neo4j_text = self._neo4j.query_subgraph_text(
                    entity_ids, hops=hops
                )
                if neo4j_text:
                    results.append(
                        {
                            "text": neo4j_text,
                            "metadata": {
                                "source": "neo4j_traversal",
                                "seed_entities": ", ".join(entity_ids[:5]),
                                "hops": str(hops),
                            },
                            "distance": 0.0,
                            "source": "neo4j",
                        }
                    )
            except Exception as exc:
                logger.warning(
                    "Neo4j subgraph query failed (non-fatal, NetworkX result kept): %s",
                    exc,
                )

        return results

    def _vector_context(
        self, query: str, k: int, diagram_type: Optional[str]
    ) -> list[dict]:
        """Run ChromaDB vector search and tag each result as ``source="vector"``."""
        try:
            chunks = _vector_retrieve(
                query=query,
                k=k,
                diagram_type=diagram_type,
                chroma_path=self._chroma_path,
            )
        except Exception as exc:
            logger.warning("Vector retrieval failed (non-fatal): %s", exc)
            return []

        for chunk in chunks:
            chunk["source"] = "vector"
        return chunks


# ---------------------------------------------------------------------------
# Factory + singleton cache
# ---------------------------------------------------------------------------

def get_retriever(
    graph_path: str = DEFAULT_GRAPH_PATH,
    chroma_path: str = "./chroma_db",
) -> HybridGraphRetriever:
    """Return a cached ``HybridGraphRetriever`` for the given path pair.

    Loads the knowledge graph from *graph_path* on the first call.  Falls
    back to building a fresh base graph (pillars only, no Excel activities)
    if the file does not yet exist — ensuring the retriever always returns
    something useful even before the first ingest run.

    When ``NEO4J_URI``, ``NEO4J_USER``, and ``NEO4J_PASSWORD`` environment
    variables are set and the Neo4j instance is reachable, a
    :class:`~rag_pipeline.neo4j_sync.Neo4jSync` instance is wired into the
    retriever as an optional second read path.  The pipeline degrades
    gracefully to NetworkX-only when Neo4j is absent or unavailable.

    Args:
        graph_path:  Path to the persisted graph JSON file.
        chroma_path: Path to the ChromaDB persistence directory.

    Returns:
        A ready-to-use ``HybridGraphRetriever`` instance.
    """
    cache_key = f"{graph_path}::{chroma_path}"

    if cache_key in _RETRIEVER_CACHE:
        return _RETRIEVER_CACHE[cache_key]

    graph = load_graph(graph_path)
    if graph is None:
        logger.info(
            "No persisted graph found at '%s' — building base graph from "
            "pillar definitions (Excel activities not included).",
            graph_path,
        )
        graph = build_graph()

    # Attempt to acquire the Neo4j second read path (non-fatal if absent)
    neo4j_sync: "Neo4jSync | None" = None
    try:
        from .neo4j_sync import get_neo4j_sync

        neo4j_sync = get_neo4j_sync()
    except Exception as exc:
        logger.warning("Could not initialise Neo4jSync (non-fatal): %s", exc)

    retriever = HybridGraphRetriever(
        graph=graph,
        chroma_path=chroma_path,
        neo4j_sync=neo4j_sync,
    )
    _RETRIEVER_CACHE[cache_key] = retriever
    logger.info(
        "HybridGraphRetriever cached for key '%s'  "
        "(graph: %d nodes / %d edges, neo4j=%s)",
        cache_key,
        graph.node_count,
        graph.edge_count,
        "enabled" if neo4j_sync is not None else "disabled",
    )
    return retriever


def invalidate_cache(
    graph_path: str = DEFAULT_GRAPH_PATH,
    chroma_path: str = "./chroma_db",
) -> None:
    """Evict the cached retriever for the given path pair.

    Call this immediately after :func:`rag_pipeline.ingest.ingest_all` so
    that the next :func:`get_retriever` call reloads the freshly saved graph
    (with any new Excel activity nodes).

    Args:
        graph_path:  Same path used when calling :func:`get_retriever`.
        chroma_path: Same path used when calling :func:`get_retriever`.
    """
    cache_key = f"{graph_path}::{chroma_path}"
    evicted = _RETRIEVER_CACHE.pop(cache_key, None)
    if evicted is not None:
        logger.info("HybridGraphRetriever cache evicted for key '%s'", cache_key)


# ---------------------------------------------------------------------------
# Internal utility
# ---------------------------------------------------------------------------

def _content_hash(text: str) -> str:
    """Return an MD5 hex digest of *text* for deduplication purposes only."""
    return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()

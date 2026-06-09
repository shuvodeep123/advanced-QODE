"""
tests/test_neo4j_sync.py — Unit tests for rag_pipeline/neo4j_sync.py.

All Neo4j driver calls are mocked — no running Neo4j instance is required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — build a minimal mock QODEKnowledgeGraph
# ---------------------------------------------------------------------------

def _make_mock_graph(
    nodes: list[tuple[str, dict]] | None = None,
    edges: list[tuple[str, str, dict]] | None = None,
) -> MagicMock:
    """Return a mock whose ._g behaves like a minimal NetworkX DiGraph."""
    mock_graph = MagicMock()
    mock_nx = MagicMock()

    nodes = nodes or [
        ("pillar_1", {"node_type": "pillar", "label": "Requirements Engineering", "summary": "..."}),
        ("role_developer", {"node_type": "role", "label": "Developer"}),
        ("tool_jira", {"node_type": "tool", "label": "Jira"}),
    ]
    edges = edges or [
        ("pillar_1", "role_developer", {"rel": "HAS_ROLE"}),
        ("pillar_1", "tool_jira", {"rel": "USES_TOOL"}),
    ]

    mock_nx.nodes.return_value = [(nid, attrs) for nid, attrs in nodes]
    mock_nx.nodes.side_effect = None
    # Support nodes(data=True) iteration
    mock_nx.nodes.__iter__ = lambda s: iter([nid for nid, _ in nodes])
    mock_nx.nodes.data = MagicMock(return_value=nodes)

    mock_nx.edges.return_value = edges
    mock_nx.edges.side_effect = None
    mock_nx.edges.data = MagicMock(return_value=edges)

    mock_nx.number_of_nodes.return_value = len(nodes)
    mock_nx.number_of_edges.return_value = len(edges)

    mock_graph._g = mock_nx
    return mock_graph


# ---------------------------------------------------------------------------
# _safe_rel_type
# ---------------------------------------------------------------------------
from rag_pipeline.neo4j_sync import _safe_rel_type, _FALLBACK_REL_TYPE


class TestSafeRelType:
    def test_known_rel_types_pass_through(self):
        for rt in ("HAS_ROLE", "USES_TOOL", "PRECEDES", "OWNS_ACTIVITY", "USED_IN"):
            assert _safe_rel_type(rt) == rt

    def test_unknown_rel_type_returns_fallback(self):
        assert _safe_rel_type("WEIRD_TYPE") == _FALLBACK_REL_TYPE

    def test_empty_string_returns_fallback(self):
        assert _safe_rel_type("") == _FALLBACK_REL_TYPE


# ---------------------------------------------------------------------------
# _format_subgraph_text (static method, no driver needed)
# ---------------------------------------------------------------------------
from rag_pipeline.neo4j_sync import Neo4jSync


class TestFormatSubgraphText:
    def test_empty_nodes_returns_header_only(self):
        result = Neo4jSync._format_subgraph_text([], [], max_activity_nodes=12)
        assert "[QODE Knowledge Graph — Neo4j Subgraph]" in result

    def test_pillar_nodes_appear_in_output(self):
        node_rows = [
            {
                "node_id": "pillar_1",
                "node_type": "pillar",
                "label": "Requirements Engineering",
                "summary": "Req summary",
            }
        ]
        result = Neo4jSync._format_subgraph_text(node_rows, [], max_activity_nodes=12)
        assert "Requirements Engineering" in result
        assert "Req summary" in result
        assert "SDLC PILLARS" in result

    def test_role_and_tool_sections_rendered(self):
        node_rows = [
            {"node_id": "role_dev", "node_type": "role", "label": "Developer", "summary": ""},
            {"node_id": "tool_jira", "node_type": "tool", "label": "Jira", "summary": ""},
        ]
        result = Neo4jSync._format_subgraph_text(node_rows, [], max_activity_nodes=12)
        assert "ROLES" in result
        assert "Developer" in result
        assert "TOOLS" in result
        assert "Jira" in result

    def test_edge_arrows_rendered(self):
        node_rows = [
            {"node_id": "pillar_1", "node_type": "pillar", "label": "Req Eng", "summary": ""},
            {"node_id": "role_dev", "node_type": "role", "label": "Developer", "summary": ""},
        ]
        edge_rows = [
            {
                "source_id": "pillar_1",
                "source_label": "Req Eng",
                "rel_type": "HAS_ROLE",
                "target_label": "Developer",
            }
        ]
        result = Neo4jSync._format_subgraph_text(node_rows, edge_rows, max_activity_nodes=12)
        assert "HAS_ROLE" in result
        assert "Developer" in result

    def test_activity_nodes_capped(self):
        node_rows = [
            {
                "node_id": f"activity_s{i}",
                "node_type": "activity",
                "label": f"Activity S{i}",
                "summary": "",
            }
            for i in range(20)
        ]
        result = Neo4jSync._format_subgraph_text(node_rows, [], max_activity_nodes=5)
        # Exactly 5 activities should appear
        assert result.count("Activity S") == 5


# ---------------------------------------------------------------------------
# Neo4jSync.__init__ and is_available
# ---------------------------------------------------------------------------

class TestNeo4jSyncInit:
    def test_init_calls_driver(self):
        mock_driver = MagicMock()
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver):
            sync = Neo4jSync(
                uri="bolt://localhost:7687",
                user="neo4j",
                **{"password": "test"},
            )
            assert sync._driver is mock_driver

    def test_is_available_returns_true_when_connected(self):
        mock_driver = MagicMock()
        mock_driver.verify_connectivity.return_value = None
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver):
            sync = Neo4jSync("bolt://localhost:7687", "neo4j", **{"password": "x"})
            assert sync.is_available() is True

    def test_is_available_returns_false_on_error(self):
        mock_driver = MagicMock()
        mock_driver.verify_connectivity.side_effect = Exception("unreachable")
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver):
            sync = Neo4jSync("bolt://localhost:7687", "neo4j", **{"password": "x"})
            assert sync.is_available() is False


# ---------------------------------------------------------------------------
# Neo4jSync.sync_graph
# ---------------------------------------------------------------------------

class TestSyncGraph:
    def _make_sync(self) -> tuple[Neo4jSync, MagicMock]:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver):
            sync = Neo4jSync("bolt://localhost:7687", "neo4j", **{"password": "x"})
        return sync, mock_session

    def test_sync_graph_calls_session(self):
        sync, mock_session = self._make_sync()
        mock_graph = _make_mock_graph()
        sync.sync_graph(mock_graph)
        assert mock_session.run.called

    def test_sync_graph_upserts_nodes(self):
        sync, mock_session = self._make_sync()
        nodes = [
            ("pillar_1", {"node_type": "pillar", "label": "Req Eng", "summary": "s"}),
        ]
        mock_graph = _make_mock_graph(nodes=nodes, edges=[])
        sync.sync_graph(mock_graph)
        # run should have been called for the node upsert
        calls = mock_session.run.call_args_list
        cypher_calls = [str(c) for c in calls]
        assert any("MERGE" in c for c in cypher_calls)

    def test_sync_graph_handles_unknown_rel_type(self):
        sync, mock_session = self._make_sync()
        edges = [("pillar_1", "role_dev", {"rel": "UNKNOWN_REL"})]
        nodes = [
            ("pillar_1", {"node_type": "pillar", "label": "P1", "summary": ""}),
            ("role_dev", {"node_type": "role", "label": "Dev"}),
        ]
        mock_graph = _make_mock_graph(nodes=nodes, edges=edges)
        # Should not raise — unknown rel type maps to RELATED_TO
        sync.sync_graph(mock_graph)


# ---------------------------------------------------------------------------
# get_neo4j_sync — factory function
# ---------------------------------------------------------------------------
from rag_pipeline.neo4j_sync import get_neo4j_sync, reset_neo4j_sync_cache


class TestGetNeo4jSync:
    def setup_method(self):
        reset_neo4j_sync_cache()

    def test_returns_none_when_env_vars_absent(self, monkeypatch):
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.delenv("NEO4J_USER", raising=False)
        monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
        result = get_neo4j_sync()
        assert result is None

    def test_returns_none_when_uri_missing(self, monkeypatch):
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")
        monkeypatch.delenv("NEO4J_URI", raising=False)
        result = get_neo4j_sync()
        assert result is None

    def test_returns_none_when_connection_fails(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "bad")
        mock_driver = MagicMock()
        mock_driver.verify_connectivity.side_effect = Exception("unreachable")
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver):
            result = get_neo4j_sync()
        assert result is None

    def test_returns_instance_when_configured(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "ok")
        mock_driver = MagicMock()
        mock_driver.verify_connectivity.return_value = None
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver):
            result = get_neo4j_sync()
        assert result is not None
        assert isinstance(result, Neo4jSync)

    def test_caches_instance_on_second_call(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "ok")
        mock_driver = MagicMock()
        mock_driver.verify_connectivity.return_value = None
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver) as mock_gd:
            first = get_neo4j_sync()
            second = get_neo4j_sync()
        assert first is second
        # Driver constructor called only once despite two get_neo4j_sync() calls
        assert mock_gd.call_count == 1

    def test_reset_clears_cache(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "ok")
        mock_driver = MagicMock()
        mock_driver.verify_connectivity.return_value = None
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver):
            first = get_neo4j_sync()
            reset_neo4j_sync_cache()
            second = get_neo4j_sync()
        # Two separate instances after reset
        assert first is not second


# ---------------------------------------------------------------------------
# HybridGraphRetriever — Neo4j second read path integration
# ---------------------------------------------------------------------------
from unittest.mock import patch as _patch
from rag_pipeline.graph_retriever import HybridGraphRetriever, _RETRIEVER_CACHE


class TestHybridRetrieverNeo4j:
    def _make_retriever(self, neo4j_sync=None):
        from rag_pipeline.graph_builder import build_graph
        graph = build_graph()
        return HybridGraphRetriever(
            graph=graph,
            chroma_path="/tmp/fake_chroma",
            neo4j_sync=neo4j_sync,
        )

    def test_no_neo4j_returns_graph_only(self):
        retriever = self._make_retriever(neo4j_sync=None)
        with _patch.object(retriever, "_vector_context", return_value=[]):
            results = retriever.retrieve("Requirements Engineering pillar")
        sources = {r["source"] for r in results}
        assert "neo4j" not in sources

    def test_neo4j_chunk_added_when_available(self):
        mock_neo4j = MagicMock()
        mock_neo4j.query_subgraph_text.return_value = (
            "[QODE Knowledge Graph — Neo4j Subgraph]\nSOME NEO4J CONTENT"
        )
        retriever = self._make_retriever(neo4j_sync=mock_neo4j)
        with _patch.object(retriever, "_vector_context", return_value=[]):
            results = retriever.retrieve("Requirements Engineering pillar")
        sources = [r["source"] for r in results]
        assert "neo4j" in sources

    def test_neo4j_error_is_non_fatal(self):
        mock_neo4j = MagicMock()
        mock_neo4j.query_subgraph_text.side_effect = Exception("Neo4j down")
        retriever = self._make_retriever(neo4j_sync=mock_neo4j)
        with _patch.object(retriever, "_vector_context", return_value=[]):
            # Should not raise
            results = retriever.retrieve("Requirements Engineering pillar")
        # NetworkX result still present
        sources = [r["source"] for r in results]
        assert "graph" in sources
        assert "neo4j" not in sources

    def test_duplicate_neo4j_content_deduplicated(self):
        from rag_pipeline.graph_builder import build_graph
        graph = build_graph()
        # Make Neo4j return identical text to NetworkX
        networkx_text = graph.get_subgraph_text(["pillar_1"], hops=2)

        mock_neo4j = MagicMock()
        mock_neo4j.query_subgraph_text.return_value = networkx_text

        retriever = HybridGraphRetriever(
            graph=graph,
            chroma_path="/tmp/fake_chroma",
            neo4j_sync=mock_neo4j,
        )
        with _patch.object(retriever, "_vector_context", return_value=[]):
            results = retriever.retrieve("requirements engineering")

        # Duplicate content should be removed — only one copy survives
        texts = [r["text"] for r in results]
        assert texts.count(networkx_text) <= 1

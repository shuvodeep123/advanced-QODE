"""
tests/test_chain.py — Unit tests for chain.py intent detection and routing logic.

Tests are isolated: no LLM calls, no ChromaDB, no disk I/O.
All external dependencies are mocked.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# detect_intent
# ---------------------------------------------------------------------------
from rag_pipeline.chain import detect_intent, detect_asis_request


class TestDetectIntent:
    def test_people_keyword(self):
        assert detect_intent("Show me the people diagram") == "people"

    def test_technology_keyword(self):
        assert detect_intent("Generate a technology diagram for the toolchain") == "technology"

    def test_process_keyword(self):
        assert detect_intent("Create a process network flow diagram") == "process"

    def test_general_no_match(self):
        assert detect_intent("Hello, how are you?") == "general"

    def test_case_insensitive(self):
        assert detect_intent("PEOPLE DIAGRAM") == "people"

    def test_multi_keyword_wins_by_score(self):
        # "process" and "network" → process wins with 2 hits vs 0 for people/technology
        assert detect_intent("Show the process network flow") == "process"

    def test_sdlc_maps_to_process(self):
        assert detect_intent("What are the SDLC bottlenecks?") == "process"

    def test_cicd_maps_to_technology(self):
        assert detect_intent("Show me the ci/cd pipeline tool") == "technology"

    def test_empty_query(self):
        assert detect_intent("") == "general"

    def test_role_maps_to_people(self):
        assert detect_intent("Which role owns the security activity?") == "people"


class TestDetectAsIsRequest:
    def test_as_is_hyphen(self):
        assert detect_asis_request("Create an as-is people architecture") is True

    def test_as_is_space(self):
        assert detect_asis_request("Show the as is process diagram") is True

    def test_asis_no_space(self):
        assert detect_asis_request("generate as is technology") is True

    def test_generate_keyword(self):
        assert detect_asis_request("generate a people diagram") is True

    def test_create_keyword(self):
        assert detect_asis_request("create the process network diagram") is True

    def test_question_not_asis(self):
        # A pure question about improvement should NOT trigger As-Is
        assert detect_asis_request("How can I improve security?") is False

    def test_existing_state(self):
        assert detect_asis_request("Show the existing technology architecture") is True

    def test_case_insensitive(self):
        assert detect_asis_request("GENERATE A PEOPLE DIAGRAM") is True


# ---------------------------------------------------------------------------
# run_chain routing — As-Is path (no LLM)
# ---------------------------------------------------------------------------

class TestRunChainAsIsPath:
    """Verify the As-Is path returns mode='asis' and never calls the LLM."""

    def _mock_retriever(self):
        retriever = MagicMock()
        retriever.retrieve.return_value = [
            {"text": "People pillar context", "source": "graph"}
        ]
        return retriever

    @patch("rag_pipeline.chain.run_diagram", return_value="/tmp/fake.png")
    @patch("rag_pipeline.chain.get_retriever")
    @patch("rag_pipeline.chain.get_tracer")
    def test_asis_mode_no_llm(self, mock_tracer, mock_get_retriever, mock_run_diagram):
        mock_get_retriever.return_value = self._mock_retriever()
        mock_tracer.return_value = MagicMock(
            __enter__=MagicMock(return_value=MagicMock()),
            __exit__=MagicMock(return_value=False),
            trace=MagicMock(return_value=MagicMock(
                __enter__=MagicMock(return_value=MagicMock()),
                __exit__=MagicMock(return_value=False),
            )),
        )

        from rag_pipeline.chain import run_chain
        result = run_chain(
            user_message="Create an as-is people architecture diagram",
            stream=False,
        )

        assert result["mode"] == "asis"
        assert result["diagram_type"] == "people"
        assert result["diagram_path"] == "/tmp/fake.png"
        assert result["eval_score"] is None  # No eval on As-Is path

    @patch("rag_pipeline.chain.run_diagram", return_value=None)
    @patch("rag_pipeline.chain.get_retriever")
    @patch("rag_pipeline.chain.get_tracer")
    def test_asis_no_excel_returns_warning(
        self, mock_tracer, mock_get_retriever, mock_run_diagram
    ):
        mock_get_retriever.return_value = self._mock_retriever()
        mock_tracer.return_value = MagicMock(
            trace=MagicMock(return_value=MagicMock(
                __enter__=MagicMock(return_value=MagicMock()),
                __exit__=MagicMock(return_value=False),
            ))
        )

        from rag_pipeline.chain import run_chain
        result = run_chain(
            user_message="Generate as-is process diagram",
            excel_path=None,
            stream=False,
        )
        assert result["mode"] == "asis"
        assert "⚠️" in result["text"] or result["diagram_path"] is None


# ---------------------------------------------------------------------------
# run_chain routing — Principles path (LLM called)
# ---------------------------------------------------------------------------

class TestRunChainPrinciplesPath:
    def _mock_retriever(self):
        retriever = MagicMock()
        retriever.retrieve.return_value = [
            {"text": "Security pillar context", "source": "graph"},
            {"text": "Vector context", "source": "vector"},
        ]
        return retriever

    @patch("rag_pipeline.chain.run_diagram", return_value=None)
    @patch("rag_pipeline.chain.get_retriever")
    @patch("rag_pipeline.chain.get_tracer")
    def test_principles_path_calls_llm(
        self, mock_tracer, mock_get_retriever, mock_run_diagram
    ):
        mock_get_retriever.return_value = self._mock_retriever()
        span = MagicMock()
        span.set_output = MagicMock()
        mock_tracer.return_value = MagicMock(
            trace=MagicMock(return_value=MagicMock(
                __enter__=MagicMock(return_value=span),
                __exit__=MagicMock(return_value=False),
            ))
        )

        with patch("rag_pipeline.llm_client.chat", return_value="LLM answer") as mock_llm:
            from rag_pipeline.chain import run_chain
            result = run_chain(
                user_message="How can I improve security for the technology stack?",
                stream=False,
            )

        assert result["mode"] == "principles"
        mock_llm.assert_called_once()

    @patch("rag_pipeline.chain.run_diagram", return_value=None)
    @patch("rag_pipeline.chain.get_retriever")
    @patch("rag_pipeline.chain.get_tracer")
    def test_principles_llm_error_returns_error_text(
        self, mock_tracer, mock_get_retriever, mock_run_diagram
    ):
        mock_get_retriever.return_value = self._mock_retriever()
        span = MagicMock()
        span.set_output = MagicMock()
        mock_tracer.return_value = MagicMock(
            trace=MagicMock(return_value=MagicMock(
                __enter__=MagicMock(return_value=span),
                __exit__=MagicMock(return_value=False),
            ))
        )

        with patch("rag_pipeline.llm_client.chat", side_effect=RuntimeError("API down")):
            from rag_pipeline.chain import run_chain
            result = run_chain(
                user_message="Suggest reliability improvements for process",
                stream=False,
            )

        assert "❌" in result["text"]
        assert result["mode"] == "principles"

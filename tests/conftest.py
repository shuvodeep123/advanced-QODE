"""
tests/conftest.py — Shared pytest configuration and import stubs.

The ``rag_pipeline`` package's ``__init__.py`` eagerly imports several heavy
optional dependencies (openai, instructor, langchain, langgraph, langfuse,
chromadb, sentence-transformers …).  Many of these are not installed in the
lightweight test environment.

This conftest stubs them out in ``sys.modules`` *before* any test module is
collected, so that unit tests can import individual sub-modules (ingest.py,
graph_builder.py, neo4j_sync.py, etc.) in isolation without requiring the
full production dependency tree.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


def _stub_third_party(name: str) -> None:
    """Stub a third-party package and all its parent namespaces."""
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        pkg = ".".join(parts[:i])
        if pkg not in sys.modules:
            sys.modules[pkg] = MagicMock()


def _stub_submodule(name: str) -> None:
    """Stub a rag_pipeline sub-module WITHOUT touching the parent package.

    This lets the real ``rag_pipeline`` package be imported normally while
    intercepting specific sub-module imports (e.g. ``rag_pipeline.chain``)
    that depend on missing files or heavy third-party deps.
    """
    if name not in sys.modules:
        sys.modules[name] = MagicMock()


# ---------------------------------------------------------------------------
# 1. Third-party stubs — packages not installed in the test environment
# ---------------------------------------------------------------------------
_THIRD_PARTY_STUBS = [
    "instructor",
    "langchain",
    "langchain.schema",
    "langchain.schema.messages",
    "langchain_openai",
    "langgraph",
    "langgraph.graph",
    "langfuse",
    "langfuse.decorators",
    "ragas",
    "datasets",
    "llama_index",
    "llama_index.core",
    "sentence_transformers",
    "chromadb",
    "chromadb.utils",
    "chromadb.utils.embedding_functions",
    "pptx",
    "fpdf",
    "fpdf2",
    "sklearn",
    "skimage",
    "matplotlib",
    "pydot",
    "pandas",
    "openpyxl",
]

for _mod in _THIRD_PARTY_STUBS:
    _stub_third_party(_mod)

# ---------------------------------------------------------------------------
# 2. rag_pipeline sub-module stubs — sub-modules with missing files or deep
#    deps that aren't needed for unit tests of ingest/graph_builder/neo4j_sync.
#    We stub only the sub-module entry; the parent ``rag_pipeline`` package is
#    left for Python to import normally so real sub-modules remain accessible.
# ---------------------------------------------------------------------------
_SUBMODULE_STUBS = [
    "rag_pipeline.diagram_schema",  # file doesn't exist in repo
    "rag_pipeline.retriever",       # imports chromadb at module level
    "rag_pipeline.llm_client",      # imports openai/instructor at module level
]

for _mod in _SUBMODULE_STUBS:
    _stub_submodule(_mod)


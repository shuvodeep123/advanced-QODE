"""
rag_pipeline — Graph-RAG pipeline for advanced-QODE.

Modules
-------
    llm_client        : HuggingFace (OpenAI-compatible) LLM wrapper.
    ingest            : Multi-format ChromaDB ingestion + knowledge graph build.
    retriever         : ChromaDB vector similarity retrieval (low-level).
    graph_builder     : QODE knowledge graph construction and persistence.
    entity_extractor  : Keyword-based QODE entity extraction from queries.
    graph_retriever   : Hybrid Graph + Vector retrieval (production retriever).
    principles_engine : 9 Engineering Principles × 3 Discipline reasoning layer.
    chain             : LangGraph agentic router (As-Is path + Principles path).
    diagram_executor  : Bridge to the existing diagram generator Python files.
    langfuse_tracer   : Langfuse observability wrapper (no-op when unconfigured).
    eval_metrics      : RAGAS / lexical RAG evaluation scoring.
"""

from .llm_client import chat, chat_stream
from .ingest import ingest_all, ingest_documents
from .retriever import retrieve
from .graph_builder import (
    QODEKnowledgeGraph,
    build_graph,
    save_graph,
    load_graph,
    DEFAULT_GRAPH_PATH,
    PILLAR_DEFINITIONS,
)
from .entity_extractor import EntityExtractor
from .graph_retriever import HybridGraphRetriever, get_retriever, invalidate_cache
from .principles_engine import PrinciplesEngine, extract_principle_context, PRINCIPLES
from .chain import run_chain, detect_intent, detect_asis_request
from .diagram_executor import run as run_diagram
from .langfuse_tracer import get_tracer
from .eval_metrics import score_response

__all__ = [
    # LLM
    "chat",
    "chat_stream",
    # Ingestion
    "ingest_all",
    "ingest_documents",
    # Vector retrieval (low-level)
    "retrieve",
    # Graph-RAG
    "QODEKnowledgeGraph",
    "build_graph",
    "save_graph",
    "load_graph",
    "DEFAULT_GRAPH_PATH",
    "PILLAR_DEFINITIONS",
    "EntityExtractor",
    "HybridGraphRetriever",
    "get_retriever",
    "invalidate_cache",
    # Engineering Principles
    "PrinciplesEngine",
    "extract_principle_context",
    "PRINCIPLES",
    # Chain
    "run_chain",
    "detect_intent",
    "detect_asis_request",
    # Diagrams
    "run_diagram",
    # Observability & Eval
    "get_tracer",
    "score_response",
]

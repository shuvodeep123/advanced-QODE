"""
rag_pipeline — RAG-based pipeline for advanced-QODE chatbot.

Modules:
    llm_client      : KodeKloud (OpenAI-compatible) LLM wrapper.
    ingest          : ChromaDB document ingestion from QODE data sources.
    retriever       : ChromaDB similarity retrieval.
    chain           : Intent detection + RAG orchestration.
    diagram_executor: Bridge to the existing diagram generators.
"""

from .llm_client import chat, chat_stream
from .ingest import ingest_all, ingest_documents
from .retriever import retrieve
from .chain import run_chain
from .diagram_executor import run as run_diagram

__all__ = [
    "chat",
    "chat_stream",
    "ingest_all",
    "ingest_documents",
    "retrieve",
    "run_chain",
    "run_diagram",
]

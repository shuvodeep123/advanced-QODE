"""
retriever.py — ChromaDB similarity retrieval for advanced-QODE.

Public API
----------
    retrieve(
        query      : str,
        k          : int = 5,
        diagram_type: str | None = None,
        chroma_path : str = "./chroma_db",
    ) -> list[dict]

Returns a list of dicts, each with keys:
    "text"     : the document text
    "metadata" : the stored metadata dict
    "distance" : cosine distance (lower = more similar)
"""

from __future__ import annotations

import logging

import chromadb
from chromadb.utils import embedding_functions

from .ingest import COLLECTION_NAME, _EMBED_MODEL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid diagram type values accepted by the metadata filter
# ---------------------------------------------------------------------------
DIAGRAM_TYPES = {"process", "people", "technology", "general"}


def _get_collection(chroma_path: str) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=chroma_path)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=_EMBED_MODEL
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def retrieve(
    query: str,
    k: int = 5,
    diagram_type: str | None = None,
    chroma_path: str = "./chroma_db",
) -> list[dict]:
    """Query ChromaDB and return the top-*k* most relevant documents.

    Args:
        query:        Natural-language search string.
        k:            Number of results to return.
        diagram_type: Optional filter — one of ``"process"``, ``"people"``,
                      ``"technology"``, or ``"general"``.  When provided, only
                      documents whose ``diagram_type`` metadata matches are
                      considered.
        chroma_path:  Path to the ChromaDB persistence directory.

    Returns:
        A list of dicts ``{"text": ..., "metadata": ..., "distance": ...}``,
        ordered from most to least similar.
    """
    collection = _get_collection(chroma_path)

    where: dict | None = None
    if diagram_type and diagram_type in DIAGRAM_TYPES:
        where = {"diagram_type": {"$eq": diagram_type}}

    query_kwargs: dict = {
        "query_texts": [query],
        "n_results": k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where is not None:
        query_kwargs["where"] = where

    try:
        results = collection.query(**query_kwargs)
    except Exception as exc:
        # If the collection is empty or the filter yields no results, fall back
        # to an unfiltered query so the user still gets relevant context.
        logger.warning(
            "Filtered ChromaDB query failed (%s); retrying without filter.", exc
        )
        query_kwargs.pop("where", None)
        results = collection.query(**query_kwargs)

    docs: list[dict] = []
    if not results["documents"] or not results["documents"][0]:
        return docs

    for text, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        docs.append({"text": text, "metadata": meta, "distance": dist})

    return docs

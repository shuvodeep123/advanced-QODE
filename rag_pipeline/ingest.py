"""
ingest.py — Multi-format ChromaDB document ingestion for advanced-QODE.

Supported file types:
  .xlsm / .xlsx   QODE questionnaire (Q_Stories sheet)
  .docx           Word documents (python-docx)
  .pdf            PDF documents (pypdf)
  .txt            Plain text

Knowledge sources ingested:
  1. Hardcoded QODE pillar descriptions (9 pillars, always ingested).
  2. README.md from the repo root.
  3. Three diagram generator Python scripts.
  4. Q_Stories rows from the QODE Excel questionnaire (Yes-rows only).
  5. Any extra files passed via extra_file_paths (.docx / .pdf / .txt).

Public API
----------
    ingest_all(excel_path, chroma_path, repo_root, graph_path, extra_file_paths) -> int
    ingest_documents(docs, chroma_path) -> None
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardcoded QODE domain knowledge: 9 Engineering Pillars
# ---------------------------------------------------------------------------
_QODE_PILLARS: list[dict[str, Any]] = [
    {
        "id": "pillar_1",
        "text": (
            "QODE Pillar 1 — Requirements & Planning: Covers user story creation, "
            "backlog grooming, sprint planning, and requirement traceability. "
            "Key roles: Product Owner, Business Analyst. "
            "Tools: Jira, Confluence, Azure DevOps Boards."
        ),
        "metadata": {"source": "qode_pillars", "pillar": "1", "diagram_type": "process"},
    },
    {
        "id": "pillar_2",
        "text": (
            "QODE Pillar 2 — Design & Architecture: Covers solution design, "
            "architecture review, threat modelling, and design approval gates. "
            "Key roles: Architect, Tech Lead. "
            "Tools: draw.io, Lucidchart, Enterprise Architect."
        ),
        "metadata": {"source": "qode_pillars", "pillar": "2", "diagram_type": "people"},
    },
    {
        "id": "pillar_3",
        "text": (
            "QODE Pillar 3 — Development & Code Quality: Covers coding standards, "
            "peer review, static analysis, and unit testing. "
            "Key roles: Developer, QA. "
            "Tools: SonarQube, GitHub, GitLab, Bitbucket."
        ),
        "metadata": {"source": "qode_pillars", "pillar": "3", "diagram_type": "technology"},
    },
    {
        "id": "pillar_4",
        "text": (
            "QODE Pillar 4 — Continuous Integration: Covers build automation, "
            "automated unit/integration tests, and artefact management. "
            "Key roles: DevOps Lead, Developer. "
            "Tools: Jenkins, GitHub Actions, CircleCI, Nexus, JFrog."
        ),
        "metadata": {"source": "qode_pillars", "pillar": "4", "diagram_type": "technology"},
    },
    {
        "id": "pillar_5",
        "text": (
            "QODE Pillar 5 — Security & Compliance (DevSecOps): Covers SAST, DAST, "
            "SCA, secrets scanning, container scanning, and compliance gates. "
            "Key roles: Security Engineer, Ops-Rel. "
            "Tools: Snyk, Checkmarx, OWASP ZAP, Twistlock."
        ),
        "metadata": {"source": "qode_pillars", "pillar": "5", "diagram_type": "process"},
    },
    {
        "id": "pillar_6",
        "text": (
            "QODE Pillar 6 — Continuous Delivery & Deployment: Covers release "
            "pipeline, environment promotion, blue-green / canary deployments, "
            "and rollback mechanisms. "
            "Key roles: DevOps Lead, Release Manager. "
            "Tools: ArgoCD, Spinnaker, Harness, Helm."
        ),
        "metadata": {"source": "qode_pillars", "pillar": "6", "diagram_type": "process"},
    },
    {
        "id": "pillar_7",
        "text": (
            "QODE Pillar 7 — Infrastructure & Configuration Management: Covers "
            "IaC, environment provisioning, configuration drift detection, and "
            "secrets management. "
            "Key roles: Ops-Infra, Cloud Engineer. "
            "Tools: Terraform, Ansible, Puppet, HashiCorp Vault."
        ),
        "metadata": {"source": "qode_pillars", "pillar": "7", "diagram_type": "technology"},
    },
    {
        "id": "pillar_8",
        "text": (
            "QODE Pillar 8 — Monitoring & Observability: Covers application "
            "performance monitoring, log aggregation, distributed tracing, "
            "alerting, and SLO tracking. "
            "Key roles: Ops-Rel, SRE. "
            "Tools: Prometheus, Grafana, ELK Stack, Datadog, Dynatrace."
        ),
        "metadata": {"source": "qode_pillars", "pillar": "8", "diagram_type": "process"},
    },
    {
        "id": "pillar_9",
        "text": (
            "QODE Pillar 9 — Feedback & Continuous Improvement: Covers retrospectives, "
            "lead-time/cycle-time metrics, DORA metrics collection, and improvement "
            "backlog management. "
            "Key roles: DevOps Lead, IT Lead, Scrum Master. "
            "Tools: Jira, PowerBI, Tableau."
        ),
        "metadata": {"source": "qode_pillars", "pillar": "9", "diagram_type": "process"},
    },
]

# ---------------------------------------------------------------------------
# Embedding function
# ---------------------------------------------------------------------------
# Override via EMBED_MODEL in .env to switch models without code changes.
# NOTE: changing the model invalidates any existing ChromaDB collection —
#       delete ./chroma_db and re-ingest to rebuild with the new embeddings.
import os as _os
_EMBED_MODEL: str = _os.environ.get("EMBED_MODEL", "google/embeddinggemma-300m")


def _get_embedding_function() -> embedding_functions.SentenceTransformerEmbeddingFunction:
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=_EMBED_MODEL
    )


# ---------------------------------------------------------------------------
# ChromaDB helpers
# ---------------------------------------------------------------------------
COLLECTION_NAME = "qode_knowledge"


def _get_collection(chroma_path: str) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=chroma_path)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Text chunking helper
# ---------------------------------------------------------------------------
def _chunk_text(text: str, max_chars: int = 500, overlap: int = 50) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


# ---------------------------------------------------------------------------
# Format-specific readers
# ---------------------------------------------------------------------------

def _read_docx(file_path: Path) -> str:
    """Extract plain text from a .docx file."""
    try:
        from docx import Document  # type: ignore[import]
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        raise RuntimeError(
            "python-docx is required for .docx ingestion. "
            "Install with: pip install python-docx"
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to read DOCX '{file_path}': {exc}") from exc


def _read_pdf(file_path: Path) -> str:
    """Extract plain text from a .pdf file."""
    try:
        from pypdf import PdfReader  # type: ignore[import]
        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except ImportError:
        raise RuntimeError(
            "pypdf is required for .pdf ingestion. "
            "Install with: pip install pypdf"
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to read PDF '{file_path}': {exc}") from exc


def _read_txt(file_path: Path) -> str:
    """Read plain text file."""
    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(f"Failed to read TXT '{file_path}': {exc}") from exc


def _read_file(file_path: Path) -> str:
    """Dispatch to the correct reader based on file extension."""
    ext = file_path.suffix.lower()
    readers = {
        ".docx": _read_docx,
        ".pdf": _read_pdf,
        ".txt": _read_txt,
        ".py": _read_txt,
        ".md": _read_txt,
    }
    reader = readers.get(ext)
    if reader is None:
        raise ValueError(f"Unsupported file type: {ext}")
    return reader(file_path)


# ---------------------------------------------------------------------------
# Source-specific ingestion helpers
# ---------------------------------------------------------------------------

def _docs_from_file(
    file_path: str | Path,
    source_label: str,
    diagram_type: str,
) -> list[dict[str, Any]]:
    """Read any supported file, chunk it, and return document dicts."""
    path = Path(file_path)
    if not path.exists():
        logger.warning("File not found, skipping: %s", path)
        return []
    try:
        content = _read_file(path)
    except Exception as exc:
        logger.error("Could not read %s: %s", path, exc)
        return []

    chunks = _chunk_text(content)
    return [
        {
            "id": f"{source_label}_chunk_{idx}_{uuid.uuid4().hex[:6]}",
            "text": chunk,
            "metadata": {
                "source": source_label,
                "chunk_index": str(idx),
                "diagram_type": diagram_type,
                "filename": path.name,
            },
        }
        for idx, chunk in enumerate(chunks)
    ]


def _docs_from_excel(excel_path: str | Path) -> list[dict[str, Any]]:
    """Convert Q_Stories rows from the Excel workbook into document dicts."""
    import pandas as pd

    try:
        df_raw = pd.read_excel(
            str(excel_path), sheet_name="Q_Stories", header=3
        ).iloc[2:]
    except Exception as exc:
        raise RuntimeError(
            f"Could not read Q_Stories from '{excel_path}': {exc}"
        ) from exc

    yes_df = df_raw[df_raw.get("Yes / No", df_raw.iloc[:, 1]) == "Yes"]

    docs: list[dict[str, Any]] = []
    for _, row in yes_df.iterrows():
        s_num = str(row.get("S#", ""))
        total_time = row.get("Total time taken", "")
        manual_time = row.get("Manual time spent", "")
        team = str(row.get("Team / owner role", ""))
        inp = str(row.get("Input", ""))
        out = str(row.get("Output", ""))
        out_type = str(row.get("Output type", ""))
        tool = str(row.get("Automation tool", ""))
        criticality = str(row.get("Criticality", ""))
        pred1 = str(row.get("Predecessor 1 (incl. INIT)", ""))

        text = (
            f"SDLC Activity S{s_num}: Input='{inp}', Output='{out}', "
            f"OutputType='{out_type}', TotalTime={total_time}, "
            f"ManualTime={manual_time}, Team='{team}', "
            f"AutomationTool='{tool}', Criticality='{criticality}', "
            f"Predecessor='{pred1}'."
        )
        docs.append(
            {
                "id": f"qstory_{s_num}_{uuid.uuid4().hex[:6]}",
                "text": text,
                "metadata": {
                    "source": "questionnaire",
                    "s_num": s_num,
                    "team": team,
                    "tool": tool,
                    "output_type": out_type,
                    "criticality": criticality,
                    "diagram_type": "process",
                },
            }
        )
    return docs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_documents(
    docs: list[dict[str, Any]], chroma_path: str = "./chroma_db"
) -> None:
    """Upsert a list of document dicts into ChromaDB.

    Each dict must have keys: ``id`` (str), ``text`` (str), ``metadata`` (dict).
    """
    if not docs:
        return
    collection = _get_collection(chroma_path)
    collection.upsert(
        ids=[d["id"] for d in docs],
        documents=[d["text"] for d in docs],
        metadatas=[d["metadata"] for d in docs],
    )


def ingest_all(
    excel_path: str | Path | None = None,
    chroma_path: str = "./chroma_db",
    repo_root: str | Path | None = None,
    graph_path: str | None = None,
    extra_file_paths: list[str] | None = None,
) -> int:
    """Full re-ingest from all QODE knowledge sources.

    Args:
        excel_path:        Path to the QODE questionnaire .xlsm/.xlsx file.
        chroma_path:       ChromaDB persistence directory.
        repo_root:         Repo root directory (defaults to parent of this file).
        graph_path:        Destination for the QODE knowledge graph JSON.
        extra_file_paths:  Additional files to ingest (.docx / .pdf / .txt).

    Returns:
        Total number of documents upserted.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    repo_root = Path(repo_root)

    all_docs: list[dict[str, Any]] = []

    # 1. QODE pillar knowledge
    all_docs.extend(_QODE_PILLARS)

    # 2. README.md
    all_docs.extend(_docs_from_file(repo_root / "README.md", "readme", "general"))

    # 3. Core diagram generator scripts
    script_map = {
        "script_process": ("Generate_Process_Network_Diagram.py", "process"),
        "script_people": ("Generate_People_Diagram.py", "people"),
        "script_technology": ("Generate_Technology_Diagram.py", "technology"),
    }
    for label, (filename, dtype) in script_map.items():
        all_docs.extend(_docs_from_file(repo_root / filename, label, dtype))

    # 4. Excel questionnaire
    if excel_path is not None:
        try:
            all_docs.extend(_docs_from_excel(excel_path))
        except Exception as exc:
            logger.warning("Excel ingestion skipped: %s", exc)

    # 5. Extra files (.docx / .pdf / .txt)
    for fpath in (extra_file_paths or []):
        path = Path(fpath)
        ext = path.suffix.lower().lstrip(".")
        label = f"extra_{path.stem}_{uuid.uuid4().hex[:4]}"
        docs = _docs_from_file(path, label, "general")
        if docs:
            logger.info("Ingested %d chunks from %s", len(docs), path.name)
        all_docs.extend(docs)

    ingest_documents(all_docs, chroma_path=chroma_path)

    # 6. Build and persist the QODE knowledge graph (non-fatal)
    _resolved_graph_path = (
        graph_path
        if graph_path is not None
        else str(Path(chroma_path).parent / "graph_db" / "qode_graph.json")
    )
    try:
        from .graph_builder import build_graph, save_graph

        graph = build_graph(excel_path=excel_path)
        save_graph(graph, graph_path=_resolved_graph_path)
        logger.info("Knowledge graph saved to %s", _resolved_graph_path)
    except Exception as exc:
        logger.warning(
            "Knowledge graph build failed (non-fatal, vector-only mode active): %s", exc
        )

    return len(all_docs)

"""
ingest.py — ChromaDB document ingestion for advanced-QODE.

Ingests the following knowledge sources into a persistent ChromaDB collection:
  1. Q_Stories rows from the QODE Excel questionnaire (one doc per Yes-row).
  2. The project README.md, chunked into ~500-character segments.
  3. The three diagram Python scripts (as domain knowledge).
  4. Hardcoded descriptions of the 9 SDLC pillars assessed by QODE.

Public API
----------
    ingest_all(excel_path: str | Path, chroma_path: str = "./chroma_db") -> None
        Full re-ingest from an Excel questionnaire + static sources.

    ingest_documents(docs: list[dict], chroma_path: str = "./chroma_db") -> None
        Ingest an arbitrary list of {"id", "text", "metadata"} dicts.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

# ---------------------------------------------------------------------------
# Hardcoded QODE domain knowledge: the 9 SDLC pillars
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
_EMBED_MODEL = "all-MiniLM-L6-v2"


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
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )
    return collection


# ---------------------------------------------------------------------------
# Text chunking helper
# ---------------------------------------------------------------------------
def _chunk_text(text: str, max_chars: int = 500, overlap: int = 50) -> list[str]:
    """Split *text* into overlapping chunks of at most *max_chars* characters."""
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
# Source-specific ingestion helpers
# ---------------------------------------------------------------------------
def _docs_from_excel(excel_path: str | Path) -> list[dict[str, Any]]:
    """Convert Q_Stories rows from the Excel workbook into document dicts."""
    import pandas as pd

    try:
        df_raw = pd.read_excel(
            str(excel_path), sheet_name="Q_Stories", header=3
            # The Q_Stories sheet has a 3-row header (header=3) plus two extra
            # decorative/instruction rows before the actual data starts; iloc[2:]
            # skips those two non-data rows.
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


def _docs_from_file(
    file_path: str | Path, source_label: str, diagram_type: str
) -> list[dict[str, Any]]:
    """Read a text file, chunk it, and return document dicts."""
    path = Path(file_path)
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8", errors="replace")
    chunks = _chunk_text(content)
    docs: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        docs.append(
            {
                "id": f"{source_label}_chunk_{idx}_{uuid.uuid4().hex[:6]}",
                "text": chunk,
                "metadata": {
                    "source": source_label,
                    "chunk_index": str(idx),
                    "diagram_type": diagram_type,
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

    Each dict must have keys: ``id`` (str), ``text`` (str),
    ``metadata`` (dict[str, str]).

    Args:
        docs:        List of document dictionaries.
        chroma_path: Path to the ChromaDB persistence directory.
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
) -> int:
    """Full re-ingest from all QODE knowledge sources.

    Sources:
    - Hardcoded QODE pillar descriptions (always ingested).
    - README.md from the repo root (if found).
    - The three diagram generator scripts (if found).
    - Q_Stories rows from *excel_path* (if provided).

    Args:
        excel_path:  Path to the QODE questionnaire ``.xlsm`` file.
                     Pass ``None`` to skip Excel ingestion.
        chroma_path: Path to ChromaDB persistence directory.
        repo_root:   Root directory of the repo.  Defaults to the parent
                     of this file's directory.

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
    all_docs.extend(
        _docs_from_file(repo_root / "README.md", "readme", "general")
    )

    # 3. Diagram scripts
    script_map = {
        "script_process": ("Generate_Process_Network_Diagram.py", "process"),
        "script_people": ("Generate_People_Diagram.py", "people"),
        "script_technology": ("Generate_Technology_Diagram.py", "technology"),
    }
    for label, (filename, dtype) in script_map.items():
        all_docs.extend(
            _docs_from_file(repo_root / filename, label, dtype)
        )

    # 4. Excel questionnaire
    if excel_path is not None:
        all_docs.extend(_docs_from_excel(excel_path))

    ingest_documents(all_docs, chroma_path=chroma_path)
    return len(all_docs)

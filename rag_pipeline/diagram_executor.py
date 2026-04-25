"""
diagram_executor.py — Bridge between the RAG chain and the QODE diagram generators.

Output formats supported
------------------------
  1. PNG   — rendered via pydot / Graphviz (preferred when Graphviz is installed).
  2. Mermaid (.mmd)  — converted from DOT graph using the dot→flowchart translator;
                       renderable in-browser via mermaid.js (no install needed).
  3. PlantUML (.puml) — converted from DOT graph; renderable via PlantUML server.

The executor tries formats in priority order: PNG → Mermaid → PlantUML → raw DOT.
The first successful output path is returned.

Public API
----------
    run(diagram_type, excel_path, output_format) -> str | None
        Returns absolute path to the generated file, or None on failure.

    dot_to_mermaid(dot_text, diagram_type) -> str
        Convert a Graphviz DOT string to Mermaid flowchart syntax.

    dot_to_plantuml(dot_text, diagram_type) -> str
        Convert a Graphviz DOT string to PlantUML activity/component syntax.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Diagram type → (module, class, method, dot_output_stem)
# ---------------------------------------------------------------------------
_DIAGRAM_MAP: dict[str, tuple[str, str, str, str]] = {
    "process": (
        "Generate_Process_Network_Diagram",
        "Process_Diagram",
        "create_network_diagram",
        "Diagram_Network",
    ),
    "people": (
        "Generate_People_Diagram",
        "People_Diagram",
        "create_people_diagram",
        "Diagram_People",
    ),
    "technology": (
        "Generate_Technology_Diagram",
        "Technology_Diagram",
        "create_technology_diagram",
        "Diagram_Technology",
    ),
}

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# DOT → Mermaid converter
# ---------------------------------------------------------------------------

def dot_to_mermaid(dot_text: str, diagram_type: str = "process") -> str:
    """Convert a Graphviz DOT string to Mermaid flowchart syntax.

    Handles:
      - Directed (digraph) and undirected (graph) graphs
      - Node labels (quoted strings)
      - Edge labels
      - Node fill-colour → Mermaid style classes
      - Basic subgraph blocks (flattened)
    """
    lines: list[str] = ["flowchart TD"]
    style_lines: list[str] = []

    # Strip comments
    dot = re.sub(r"//[^\n]*", "", dot_text)
    dot = re.sub(r"/\*.*?\*/", "", dot, flags=re.DOTALL)

    # Determine direction
    if "rankdir=LR" in dot or "rankdir = LR" in dot:
        lines[0] = "flowchart LR"

    node_ids: dict[str, str] = {}   # raw_id → safe_id
    node_labels: dict[str, str] = {}
    node_colors: dict[str, str] = {}
    edge_count = 0

    def _safe_id(raw: str) -> str:
        """Convert a DOT node id to a Mermaid-safe alphanumeric id."""
        s = re.sub(r"[^a-zA-Z0-9_]", "_", raw.strip('"'))
        if s and s[0].isdigit():
            s = "N" + s
        return s or "NODE"

    def _safe_label(lbl: str) -> str:
        lbl = lbl.strip('"').strip("'")
        # Escape Mermaid special chars
        lbl = lbl.replace("[", "(").replace("]", ")").replace("{", "(").replace("}", ")")
        return lbl

    is_directed = "digraph" in dot.lower()
    arrow = "-->" if is_directed else "---"

    # ── Parse node statements ──────────────────────────────────────────────
    # Pattern: id [label="...", fillcolor="...", ...]
    node_pattern = re.compile(
        r'^\s*"?([^"\s\[{};]+)"?\s*\[([^\]]*)\]', re.MULTILINE
    )
    for m in node_pattern.finditer(dot):
        raw_id = m.group(1)
        attrs_str = m.group(2)
        safe = _safe_id(raw_id)
        node_ids[raw_id] = safe

        # Extract label
        lbl_m = re.search(r'label\s*=\s*"([^"]*)"', attrs_str)
        label = _safe_label(lbl_m.group(1)) if lbl_m else _safe_label(raw_id)
        node_labels[raw_id] = label

        # Extract fillcolor for style
        col_m = re.search(r'fillcolor\s*=\s*"?([^",\]]+)"?', attrs_str)
        if col_m:
            node_colors[raw_id] = col_m.group(1).strip()

    # ── Parse edge statements ──────────────────────────────────────────────
    # Pattern: id1 -> id2 [label="..."]  or  id1 -- id2
    edge_sep = r"->" if is_directed else r"--"
    edge_pattern = re.compile(
        r'"?([^"\s\[{};>-]+)"?\s*' + re.escape(edge_sep) + r'\s*"?([^"\s\[{};>-]+)"?'
        r'(?:\s*\[([^\]]*)\])?',
        re.MULTILINE,
    )
    for m in edge_pattern.finditer(dot):
        src_raw = m.group(1).strip()
        dst_raw = m.group(2).strip()
        attrs_str = m.group(3) or ""

        src = node_ids.get(src_raw, _safe_id(src_raw))
        dst = node_ids.get(dst_raw, _safe_id(dst_raw))

        # Ensure nodes are declared
        if src_raw not in node_labels:
            node_labels[src_raw] = _safe_label(src_raw)
            node_ids[src_raw] = src
        if dst_raw not in node_labels:
            node_labels[dst_raw] = _safe_label(dst_raw)
            node_ids[dst_raw] = dst

        lbl_m = re.search(r'label\s*=\s*"([^"]*)"', attrs_str)
        edge_label = _safe_label(lbl_m.group(1)) if lbl_m else ""

        if edge_label:
            lines.append(f'    {src}["{node_labels[src_raw]}"] {arrow}|"{edge_label}"| {dst}["{node_labels[dst_raw]}"]')
        else:
            lines.append(f'    {src}["{node_labels[src_raw]}"] {arrow} {dst}["{node_labels[dst_raw]}"]')
        edge_count += 1

    # ── Emit isolated nodes (no edges) ────────────────────────────────────
    for raw_id, safe in node_ids.items():
        label = node_labels.get(raw_id, raw_id)
        # Only add if not already in an edge line
        node_ref = f'{safe}['
        if not any(node_ref in l for l in lines[1:]):
            lines.append(f'    {safe}["{label}"]')

    # ── Style classes from fillcolors ──────────────────────────────────────
    color_classes: dict[str, list[str]] = {}
    for raw_id, color in node_colors.items():
        safe = node_ids.get(raw_id, _safe_id(raw_id))
        color_classes.setdefault(color, []).append(safe)

    for color, ids in color_classes.items():
        cls_name = "cls_" + re.sub(r"[^a-zA-Z0-9]", "_", color)
        lines.append(f'    classDef {cls_name} fill:{color},stroke:#333,color:#fff')
        lines.append(f'    class {",".join(ids)} {cls_name}')

    if edge_count == 0 and not node_ids:
        # Fallback: no parseable structure
        lines.append('    A["Diagram data not parsed — see DOT source below"]')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DOT → PlantUML converter
# ---------------------------------------------------------------------------

def dot_to_plantuml(dot_text: str, diagram_type: str = "process") -> str:
    """Convert a Graphviz DOT string to PlantUML component/activity syntax."""
    is_directed = "digraph" in dot_text.lower()

    # Strip comments
    dot = re.sub(r"//[^\n]*", "", dot_text)
    dot = re.sub(r"/\*.*?\*/", "", dot, flags=re.DOTALL)

    puml_type = "component" if diagram_type == "technology" else "activity" if diagram_type == "process" else "usecase"

    lines = ["@startuml", f"' {diagram_type.title()} Architecture Diagram", ""]

    if diagram_type == "people":
        lines += ["left to right direction", ""]

    node_labels: dict[str, str] = {}
    edges: list[tuple[str, str, str]] = []

    def _label(raw: str) -> str:
        return raw.strip('"').strip("'").replace("<", "").replace(">", "")

    # Parse nodes
    node_pat = re.compile(r'"?([^"\s\[{};]+)"?\s*\[([^\]]*)\]', re.MULTILINE)
    for m in node_pat.finditer(dot):
        raw_id = m.group(1)
        attrs = m.group(2)
        lbl_m = re.search(r'label\s*=\s*"([^"]*)"', attrs)
        label = _label(lbl_m.group(1)) if lbl_m else _label(raw_id)
        node_labels[raw_id] = label

    # Parse edges
    edge_sep = "->" if is_directed else "--"
    edge_pat = re.compile(
        r'"?([^"\s\[{};>-]+)"?\s*' + re.escape(edge_sep) + r'\s*"?([^"\s\[{};>-]+)"?'
        r'(?:\s*\[([^\]]*)\])?',
        re.MULTILINE,
    )
    for m in edge_pat.finditer(dot):
        src = m.group(1).strip()
        dst = m.group(2).strip()
        attrs = m.group(3) or ""
        lbl_m = re.search(r'label\s*=\s*"([^"]*)"', attrs)
        elabel = _label(lbl_m.group(1)) if lbl_m else ""
        edges.append((src, dst, elabel))
        if src not in node_labels:
            node_labels[src] = _label(src)
        if dst not in node_labels:
            node_labels[dst] = _label(dst)

    arrow = "-->" if is_directed else "--"

    for raw_id, label in node_labels.items():
        if diagram_type == "technology":
            lines.append(f'component "{label}" as {re.sub(r"[^a-zA-Z0-9]", "_", raw_id)}')
        elif diagram_type == "people":
            lines.append(f'actor "{label}" as {re.sub(r"[^a-zA-Z0-9]", "_", raw_id)}')
        else:
            lines.append(f':{label}:')

    lines.append("")

    for src, dst, elabel in edges:
        s = re.sub(r"[^a-zA-Z0-9]", "_", src)
        d = re.sub(r"[^a-zA-Z0-9]", "_", dst)
        if diagram_type in ("technology", "people"):
            lbl_part = f' : {elabel}' if elabel else ""
            lines.append(f"{s} {arrow} {d}{lbl_part}")
        else:
            lbl_part = f"\nnote right: {elabel}" if elabel else ""
            lines.append(f"{arrow} :{node_labels.get(dst, dst)}:{lbl_part}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

def run(
    diagram_type: str,
    excel_path: str | None = None,
    output_format: str = "auto",   # "auto" | "png" | "mermaid" | "plantuml" | "dot"
) -> str | None:
    """Generate a QODE diagram and return the path to the output file.

    Priority order (when output_format="auto"):
      1. PNG  (requires Graphviz installed)
      2. Mermaid .mmd  (always available — rendered inline by the UI)
      3. PlantUML .puml (always available — rendered inline by the UI)
      4. Raw DOT .dot  (final fallback)

    Args:
        diagram_type:   "process" | "people" | "technology"
        excel_path:     Path to the QODE questionnaire. Defaults to repo root default.
        output_format:  Override the output format explicitly, or "auto".

    Returns:
        Absolute path to the generated file, or None on failure.
    """
    if diagram_type not in _DIAGRAM_MAP:
        logger.error("Unknown diagram_type '%s'", diagram_type)
        return None

    module_name, class_name, method_name, dot_filename = _DIAGRAM_MAP[diagram_type]

    if excel_path is None:
        excel_path = str(_REPO_ROOT / "QODE-Questionnaire.xlsm")

    excel_abs = str(Path(excel_path).resolve())
    original_cwd = os.getcwd()
    os.chdir(str(_REPO_ROOT))

    expected_name = "QODE-Questionnaire.xlsm"
    if Path(excel_abs).name != expected_name and Path(excel_abs).exists():
        import shutil
        shutil.copy(excel_abs, str(_REPO_ROOT / expected_name))

    try:
        repo_str = str(_REPO_ROOT)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)

        if module_name in sys.modules:
            del sys.modules[module_name]

        import importlib
        module = importlib.import_module(module_name)
        instance = getattr(module, class_name)()
        getattr(instance, method_name)()

        dot_path = _REPO_ROOT / dot_filename
        if not dot_path.exists():
            logger.warning("DOT file '%s' was not created.", dot_path)
            return None

        dot_text = dot_path.read_text(encoding="utf-8", errors="replace")

        # ── 1. Try PNG (Graphviz) ──────────────────────────────────────────
        if output_format in ("auto", "png"):
            png_path = dot_path.with_suffix(".png")
            try:
                import pydot
                graphs = pydot.graph_from_dot_file(str(dot_path))
                if graphs:
                    graphs[0].write_png(str(png_path))
                    logger.info("Rendered PNG: %s", png_path)
                    return str(png_path)
            except Exception as png_err:
                logger.info("PNG render skipped (%s) — falling back to Mermaid.", png_err)
            if output_format == "png":
                return None  # explicit PNG requested but failed

        # ── 2. Mermaid (.mmd) ─────────────────────────────────────────────
        if output_format in ("auto", "mermaid"):
            mmd_path = dot_path.with_suffix(".mmd")
            try:
                mmd_text = dot_to_mermaid(dot_text, diagram_type)
                mmd_path.write_text(mmd_text, encoding="utf-8")
                logger.info("Mermaid diagram saved: %s", mmd_path)
                return str(mmd_path)
            except Exception as mmd_err:
                logger.warning("Mermaid conversion failed: %s", mmd_err)
            if output_format == "mermaid":
                return None

        # ── 3. PlantUML (.puml) ───────────────────────────────────────────
        if output_format in ("auto", "plantuml"):
            puml_path = dot_path.with_suffix(".puml")
            try:
                puml_text = dot_to_plantuml(dot_text, diagram_type)
                puml_path.write_text(puml_text, encoding="utf-8")
                logger.info("PlantUML diagram saved: %s", puml_path)
                return str(puml_path)
            except Exception as puml_err:
                logger.warning("PlantUML conversion failed: %s", puml_err)
            if output_format == "plantuml":
                return None

        # ── 4. Raw DOT fallback ───────────────────────────────────────────
        return str(dot_path)

    except Exception as exc:
        logger.error("Diagram generation failed for '%s': %s", diagram_type, exc)
        return None

    finally:
        os.chdir(original_cwd)

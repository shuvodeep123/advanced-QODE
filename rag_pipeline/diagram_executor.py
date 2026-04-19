"""
diagram_executor.py — Bridge between the RAG chain and the QODE diagram generators.

Public API
----------
    run(
        diagram_type : str,
        excel_path   : str | None = None,
    ) -> str | None

Calls the appropriate diagram generator class, attempts to render the DOT
file to PNG using pydot / Graphviz, and returns the path to the PNG (or the
DOT file path if Graphviz is not available).  Returns None when generation
fails.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Map diagram type → (module file, class name, method name, dot output name)
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

# Directory where diagram output files are written (same as repo root)
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _patch_excel_path(module, excel_path: str) -> None:
    """Hot-patch the module-level ``df`` read so it uses *excel_path*.

    The three generator scripts each do a bare ``pd.read_excel(...)`` at
    module level.  We monkey-patch the path constant they reference so the
    in-process import reads the correct file.
    """
    # The scripts store the path as the first argument to pd.read_excel;
    # they reference the literal string 'QODE-Questionnaire.xlsm'.
    # We patch os.getcwd indirectly by temporarily changing the working dir.
    pass  # handled via cwd change in run()


def run(
    diagram_type: str,
    excel_path: str | None = None,
) -> str | None:
    """Generate a QODE diagram and return the path to the output file.

    Args:
        diagram_type: One of ``"process"``, ``"people"``, ``"technology"``.
        excel_path:   Path to the uploaded QODE questionnaire ``.xlsm``.
                      Defaults to ``QODE-Questionnaire.xlsm`` in the repo root.

    Returns:
        Absolute path to the generated PNG (preferred) or DOT file, or
        ``None`` if generation failed.
    """
    if diagram_type not in _DIAGRAM_MAP:
        logger.error("Unknown diagram_type '%s'", diagram_type)
        return None

    module_name, class_name, method_name, dot_filename = _DIAGRAM_MAP[diagram_type]

    # Resolve the Excel path
    if excel_path is None:
        excel_path = str(_REPO_ROOT / "QODE-Questionnaire.xlsm")

    excel_abs = str(Path(excel_path).resolve())

    # Change working directory to the repo root so the scripts can find the
    # questionnaire via its relative-path default.
    original_cwd = os.getcwd()
    os.chdir(str(_REPO_ROOT))

    # Copy the Excel file to the expected filename if it differs
    expected_name = "QODE-Questionnaire.xlsm"
    excel_basename = Path(excel_abs).name
    if excel_basename != expected_name and Path(excel_abs).exists():
        import shutil
        shutil.copy(excel_abs, str(_REPO_ROOT / expected_name))

    try:
        # Ensure the repo root is on sys.path so imports work
        repo_str = str(_REPO_ROOT)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)

        # Force re-import each time so class-level mutable defaults are reset
        if module_name in sys.modules:
            del sys.modules[module_name]

        import importlib
        module = importlib.import_module(module_name)

        diagram_class = getattr(module, class_name)
        instance = diagram_class()
        getattr(instance, method_name)()

        dot_path = _REPO_ROOT / dot_filename
        if not dot_path.exists():
            logger.warning("DOT file '%s' was not created.", dot_path)
            return None

        # Attempt to render to PNG using pydot
        png_path = dot_path.with_suffix(".png")
        try:
            import pydot
            graphs = pydot.graph_from_dot_file(str(dot_path))
            if graphs:
                graphs[0].write_png(str(png_path))
                return str(png_path)
        except Exception as render_exc:
            logger.warning(
                "Could not render DOT → PNG (%s); returning DOT path.", render_exc
            )

        return str(dot_path)

    except Exception as exc:
        logger.error("Diagram generation failed for '%s': %s", diagram_type, exc)
        return None

    finally:
        os.chdir(original_cwd)

#!/usr/bin/env bash
# ============================================================
# run.sh — One-command launcher for advanced-QODE
# ============================================================
set -euo pipefail

# ── Colours for pretty output ────────────────────────────────
RED='\033[0;31m'; YEL='\033[1;33m'; GRN='\033[0;32m'
CYN='\033[0;36m'; BLD='\033[1m'; RST='\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo -e "${CYN}${BLD}"
echo "  ██████╗  ██████╗  ██████╗ ██████╗ ███████╗"
echo "  ██╔══██╗██╔═══██╗██╔══██╗██╔═══╝ ██╔════╝"
echo "  ██║  ██║██║   ██║██║  ██║█████╗  ███████╗"
echo "  ██║  ██║██║▄▄ ██║██║  ██║██╔══╝  ╚════██║"
echo "  ██████╔╝╚██████╔╝██████╔╝███████╗███████║"
echo "  ╚═════╝  ╚══▀▀═╝ ╚═════╝ ╚══════╝╚══════╝"
echo -e "  advanced-QODE — GenAI Diagram Assistant${RST}"
echo ""

# ── Check Python ─────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}✗ python3 not found. Install Python 3.11+.${RST}" && exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "  ${GRN}✓${RST} Python ${PY_VER} detected"

# ── Activate venv if present ──────────────────────────────────
if [[ -f "${REPO_ROOT}/venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "${REPO_ROOT}/venv/bin/activate"
  echo -e "  ${GRN}✓${RST} Virtual environment activated"
elif [[ -f "${REPO_ROOT}/.venv/bin/activate" ]]; then
  source "${REPO_ROOT}/.venv/bin/activate"
  echo -e "  ${GRN}✓${RST} Virtual environment (.venv) activated"
else
  echo -e "  ${YEL}⚠${RST}  No venv found — using system Python"
fi

# ── Load .env if present ─────────────────────────────────────
if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${REPO_ROOT}/.env"
  set +a
  echo -e "  ${GRN}✓${RST} .env loaded"
else
  echo -e "  ${YEL}⚠${RST}  No .env file found — using existing environment"
fi

# ── Check critical env vars ───────────────────────────────────
if [[ -z "${HF_TOKEN:-}" ]]; then
  echo -e "  ${YEL}⚠${RST}  HF_TOKEN not set — LLM calls will fail"
  echo -e "     Set it in .env or export HF_TOKEN=<your-token>"
else
  echo -e "  ${GRN}✓${RST} HF_TOKEN detected"
fi

if [[ -n "${LANGFUSE_SECRET_KEY:-}" ]] && [[ -n "${LANGFUSE_PUBLIC_KEY:-}" ]]; then
  echo -e "  ${GRN}✓${RST} Langfuse tracing enabled"
else
  echo -e "  ${CYN}ℹ${RST}  Langfuse keys not set — using no-op tracer (optional)"
fi

# ── Check streamlit installed ─────────────────────────────────
if ! python3 -c "import streamlit" &>/dev/null; then
  echo -e "\n  ${YEL}Installing dependencies …${RST}"
  pip install -r requirements_rag.txt --quiet
fi

# ── Launch ────────────────────────────────────────────────────
PORT="${STREAMLIT_PORT:-8501}"
echo ""
echo -e "  ${BLD}Starting advanced-QODE on http://localhost:${PORT}${RST}"
echo -e "  ${CYN}Press Ctrl+C to stop.${RST}"
echo ""

exec streamlit run app.py \
  --server.port "${PORT}" \
  --server.headless true \
  --browser.gatherUsageStats false \
  --theme.base dark \
  --theme.backgroundColor "#0d1117" \
  --theme.secondaryBackgroundColor "#161b22" \
  --theme.primaryColor "#3b82f6" \
  --theme.textColor "#f0f6fc" \
  --theme.font "sans serif"

#!/usr/bin/env bash
#
# Create a Python venv with everything the smoke tests (steps 6-8) need, so the
# `python tests/test_*.py` commands work directly with no extra dep hunting.
#
# mmore's `[qdrant]` extra alone is NOT enough:
#   - test_qdrant_server.py goes through mmore.index.indexer, which eagerly
#     imports mmore.rag.llm and therefore the LangChain provider packages.
#   - test_colpali_real.py needs the ColPali process/index/query stack
#     (colpali-engine, pymupdf, pyarrow) and a GPU.
# This script installs all of it.
#
# Usage:
#   scripts/setup_test_env.sh /path/to/mmore [venv_dir]
#
# Then, from the repo root:
#   source <venv_dir>/bin/activate
#   export MMORE_SRC=/path/to/mmore/src
#   export PYTHONPATH=$MMORE_SRC
#   python tests/test_qdrant_server.py        # step 6
#   python tests/test_qdrant_colpali.py       # step 7
#   python tests/test_colpali_real.py         # step 8 (needs a GPU)
#
set -euo pipefail

MMORE_PATH="${1:?usage: scripts/setup_test_env.sh /path/to/mmore [venv_dir]}"
VENV="${2:-.venv}"

MMORE_PATH="$(cd "$MMORE_PATH" && pwd)"
[ -f "$MMORE_PATH/pyproject.toml" ] || {
    echo "ERROR: $MMORE_PATH does not look like an mmore checkout (no pyproject.toml)." >&2
    exit 1
}

echo "==> mmore:   $MMORE_PATH"
echo "==> venv:    $VENV"

# ---------------------------------------------------------------------------
# 1. Create the venv (prefer uv; fall back to stdlib venv)
# ---------------------------------------------------------------------------
if command -v uv >/dev/null 2>&1; then
    PY="${PYTHON:-3.11}"
    uv venv "$VENV" --python "$PY"
    PIP_INSTALL=(uv pip install --python "$VENV/bin/python")
else
    PY="${PYTHON:-python3}"
    "$PY" -m venv "$VENV"
    PIP_INSTALL=("$VENV/bin/python" -m pip install)
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
fi

# ---------------------------------------------------------------------------
# 2. Install mmore[qdrant] + the deps its code paths actually import
# ---------------------------------------------------------------------------
echo "==> Installing mmore[qdrant] (this also pulls torch — a few minutes)"
"${PIP_INSTALL[@]}" -e "${MMORE_PATH}[qdrant]"

echo "==> Installing LangChain providers (mmore.rag.llm imports these eagerly)"
"${PIP_INSTALL[@]}" \
    langchain-anthropic langchain-cohere langchain-huggingface \
    langchain-mistralai langchain-openai

echo "==> Installing the ColPali process/index/query stack"
"${PIP_INSTALL[@]}" colpali-engine pymupdf pyarrow

echo
echo "Done. To run the smoke tests:"
echo "  source ${VENV}/bin/activate"
echo "  export MMORE_SRC=${MMORE_PATH}/src"
echo "  export PYTHONPATH=\$MMORE_SRC"
echo "  python tests/test_qdrant_server.py"
echo "  python tests/test_qdrant_colpali.py"
echo "  python tests/test_colpali_real.py    # needs a GPU; auto-builds its corpus on first run"

#!/usr/bin/env bash
set -euo pipefail

# Change to the directory of this script (the pipeline folder)
cd "$(dirname "$0")"

PYTHON_BIN="python3.11"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

echo "Using Python interpreter: $(command -v "$PYTHON_BIN")"

# Create venv if missing
if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi

# Activate
source .venv/bin/activate

# Upgrade pip and install deps
python -m pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Done. Activate the environment with:"
echo "  source $(pwd)/.venv/bin/activate"
echo
echo "To launch the GUI:"
echo "  streamlit run eduasr/ui_app.py"
echo

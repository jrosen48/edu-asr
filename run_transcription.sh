#!/bin/bash
# Script to run transcription with proper HF_TOKEN setup and virtual environment

# Activate virtual environment
source .venv/bin/activate

# Source the HF token
source hf

# Check if HF_TOKEN is set
if [ -z "$HF_TOKEN" ]; then
    echo "Error: HF_TOKEN not set. Please check the 'hf' file."
    exit 1
fi

echo "HF_TOKEN is set: ${HF_TOKEN:0:10}..."
echo "Using virtual environment: $(which python)"

# Run the transcription with all arguments passed through
python -m eduasr.cli transcribe "$@"

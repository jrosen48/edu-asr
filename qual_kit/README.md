# EDU ASR Qual Kit (local, lightweight)

A tiny, local-first toolkit to qualitatively explore transcripts produced by the pipeline.

## What it does
- Imports `*.json` outputs into **SQLite**
- Builds an **FTS5** index over text
- CLI for **KWIC**, **hit counts**, and **segment export**
- Optional **Streamlit** UI for browsing (local only)

## Install
```bash
pip install streamlit pandas
```

## Import transcripts
```bash
python import_transcripts.py --transcripts-dir "/path/to/out" --db "/path/to/edu_asr.sqlite"
```

## CLI examples
```bash
python query_cli.py --db "/path/to/edu_asr.sqlite" kwic --query "formative assessment" --window 40 --limit 50
python query_cli.py --db "/path/to/edu_asr.sqlite" hits --query rubric --group-by file
python query_cli.py --db "/path/to/edu_asr.sqlite" segments --query "exit ticket" --limit 100 --csv matches.csv
```

## UI
```bash
streamlit run ui_app.py -- --db "/path/to/edu_asr.sqlite"
```

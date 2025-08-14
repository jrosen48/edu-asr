"""EDU ASR unified module.

Submodules:
- eduasr.transcribe: Batch transcription pipeline
- eduasr.stats: Transcript statistics utilities
- eduasr.db: SQLite import + FTS5 utilities
- eduasr.query: CLI-friendly querying helpers (kwic, hits, segments)
- eduasr.ui_app: Streamlit UI
- eduasr.cli: Unified command-line interface
"""

__all__ = [
  "transcribe",
  "stats",
  "db",
  "query",
]




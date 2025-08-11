#!/usr/bin/env python3
import argparse, json, os, sqlite3
from pathlib import Path

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS segments (
  id INTEGER PRIMARY KEY,
  file TEXT NOT NULL,
  speaker TEXT,
  start_s REAL,
  end_s REAL,
  text TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
  text, content='segments', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
  INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
  INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
  INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.id, old.text);
  INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;
"""

def open_db(path):
  conn = sqlite3.connect(path)
  conn.execute("PRAGMA journal_mode=WAL;")
  conn.execute("PRAGMA synchronous=NORMAL;")
  for stmt in SCHEMA.strip().split(";\n"):
    if stmt.strip():
      conn.execute(stmt)
  return conn

def import_json(conn, json_path):
  data = json.loads(Path(json_path).read_text())
  file_path = data.get("file") or Path(json_path).name
  segs = data.get("segments", [])
  cur = conn.cursor()
  for seg in segs:
    text = (seg.get("text") or "").strip()
    if not text:
      continue
    speaker = seg.get("speaker")
    start_s = float(seg.get("start", 0.0))
    end_s = float(seg.get("end", 0.0))
    cur.execute(
      "INSERT INTO segments(file, speaker, start_s, end_s, text) VALUES (?,?,?,?,?)",
      (file_path, speaker, start_s, end_s, text)
    )
  conn.commit()

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--transcripts-dir", required=True, help="Folder containing *.json outputs from the ASR pipeline")
  ap.add_argument("--db", required=True, help="SQLite file to write to")
  args = ap.parse_args()

  conn = open_db(args.db)
  json_files = [p for p in Path(args.transcripts_dir).glob("*.json")]
  if not json_files:
    print("No JSON transcripts found.")
    return

  for jf in sorted(json_files):
    print(f"[import] {jf.name}")
    import_json(conn, jf)

  print("[done] Imported", len(json_files), "files into", args.db)

if __name__ == "__main__":
  main()

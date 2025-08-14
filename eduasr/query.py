#!/usr/bin/env python3
import csv, sqlite3

def open_db(path):
  conn = sqlite3.connect(path)
  conn.row_factory = sqlite3.Row
  return conn

def kwic(conn, query, window=40, limit=100):
  sql = "SELECT s.id, s.file, s.speaker, s.start_s, s.end_s, s.text FROM segments s JOIN segments_fts f ON s.id=f.rowid WHERE segments_fts MATCH ? LIMIT ?"
  rows = conn.execute(sql, (query, limit)).fetchall()
  out = []
  for r in rows:
    text = r["text"]
    q = query.strip('"').lower()
    idx = text.lower().find(q)
    if idx >= 0:
      left = max(0, idx-window); right = min(len(text), idx+len(q)+window)
      snippet = text[left:right]
      out.append(f"{r['file']} [{r['start_s']:.1f}-{r['end_s']:.1f}] {r['speaker'] or 'UNK'} :: …{snippet}…")
    else:
      out.append(f"{r['file']} [{r['start_s']:.1f}-{r['end_s']:.1f}] {r['speaker'] or 'UNK'} :: {text[:2*window]}…")
  return out

def hits(conn, query, group_by="file"):
  group_col = "file" if group_by=="file" else "speaker"
  sql = f"SELECT s.{group_col} as grp, COUNT(*) as cnt FROM segments s JOIN segments_fts f ON s.id=f.rowid WHERE segments_fts MATCH ? GROUP BY s.{group_col} ORDER BY cnt DESC"
  return [(r["grp"], r["cnt"]) for r in conn.execute(sql, (query,))]

def segments(conn, query, limit=200):
  sql = "SELECT s.file, s.speaker, s.start_s, s.end_s, s.text FROM segments s JOIN segments_fts f ON s.id=f.rowid WHERE segments_fts MATCH ? ORDER BY s.file, s.start_s LIMIT ?"
  rows = conn.execute(sql, (query, limit)).fetchall()
  return rows

def write_segments_csv(rows, csv_path):
  with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["file","speaker","start_s","end_s","text"])
    for r in rows:
      w.writerow([r["file"], r["speaker"], f"{r['start_s']:.3f}", f"{r['end_s']:.3f}", r["text"]])




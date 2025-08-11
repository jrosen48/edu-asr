#!/usr/bin/env python3
import argparse, csv, sqlite3, sys
from pathlib import Path

def open_db(path):
  conn = sqlite3.connect(path)
  conn.row_factory = sqlite3.Row
  return conn

def kwic(conn, query, window=40, limit=100):
  sql = "SELECT s.id, s.file, s.speaker, s.start_s, s.end_s, s.text FROM segments s JOIN segments_fts f ON s.id=f.rowid WHERE segments_fts MATCH ? LIMIT ?"
  rows = conn.execute(sql, (query, limit)).fetchall()
  for r in rows:
    text = r["text"]
    q = query.strip('"').lower()
    idx = text.lower().find(q)
    if idx >= 0:
      left = max(0, idx-window); right = min(len(text), idx+len(q)+window)
      snippet = text[left:right]
      print(f"{r['file']} [{r['start_s']:.1f}-{r['end_s']:.1f}] {r['speaker'] or 'UNK'} :: …{snippet}…")
    else:
      print(f"{r['file']} [{r['start_s']:.1f}-{r['end_s']:.1f}] {r['speaker'] or 'UNK'} :: {text[:2*window]}…")

def hits(conn, query, group_by="file"):
  group_col = "file" if group_by=="file" else "speaker"
  sql = f"SELECT s.{group_col} as grp, COUNT(*) as cnt FROM segments s JOIN segments_fts f ON s.id=f.rowid WHERE segments_fts MATCH ? GROUP BY s.{group_col} ORDER BY cnt DESC"
  for r in conn.execute(sql, (query,)):
    print(f"{r['grp'] or '(None)'}\t{r['cnt']}")

def segments(conn, query, limit=200, csv_path=None):
  sql = "SELECT s.file, s.speaker, s.start_s, s.end_s, s.text FROM segments s JOIN segments_fts f ON s.id=f.rowid WHERE segments_fts MATCH ? ORDER BY s.file, s.start_s LIMIT ?"
  rows = conn.execute(sql, (query, limit)).fetchall()
  if csv_path:
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
      w = csv.writer(f); w.writerow(["file","speaker","start_s","end_s","text"])
      for r in rows:
        w.writerow([r["file"], r["speaker"], f"{r['start_s']:.3f}", f"{r['end_s']:.3f}", r["text"]])
    print("Wrote", csv_path)
  else:
    for r in rows:
      print(f"{r['file']} [{r['start_s']:.1f}-{r['end_s']:.1f}] {r['speaker'] or 'UNK'} :: {r['text']}")

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--db", required=True)
  sub = ap.add_subparsers(dest="cmd", required=True)

  p_kwic = sub.add_parser("kwic")
  p_kwic.add_argument("--query", required=True, help='FTS query; use quotes for exact phrase (e.g., "exit ticket")')
  p_kwic.add_argument("--window", type=int, default=40)
  p_kwic.add_argument("--limit", type=int, default=100)

  p_hits = sub.add_parser("hits")
  p_hits.add_argument("--query", required=True)
  p_hits.add_argument("--group-by", choices=["file","speaker"], default="file")

  p_seg = sub.add_parser("segments")
  p_seg.add_argument("--query", required=True)
  p_seg.add_argument("--limit", type=int, default=200)
  p_seg.add_argument("--csv", help="Write results to CSV")

  args = ap.parse_args()
  conn = open_db(args.db)

  if args.cmd == "kwic":
    kwic(conn, args.query, window=args.window, limit=args.limit)
  elif args.cmd == "hits":
    hits(conn, args.query, group_by=args.group_by)
  else:
    segments(conn, args.query, limit=args.limit, csv_path=args.csv)

if __name__ == "__main__":
  main()

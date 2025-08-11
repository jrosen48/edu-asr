#!/usr/bin/env python3
import argparse, sqlite3, pandas as pd, streamlit as st

def open_db(path):
  conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row; return conn

def search(conn, q, file_filter=None, speaker_filter=None, limit=500):
  params = []; where = "WHERE segments_fts MATCH ?"; params.append(q)
  if file_filter: where += " AND s.file = ?"; params.append(file_filter)
  if speaker_filter: where += " AND s.speaker = ?"; params.append(speaker_filter)
  sql = f"""
    SELECT s.file, s.speaker, s.start_s, s.end_s, s.text
    FROM segments s JOIN segments_fts f ON s.id=f.rowid
    {where}
    ORDER BY s.file, s.start_s
    LIMIT {int(limit)}
  """
  cur = conn.execute(sql, params)
  return pd.DataFrame([dict(r) for r in cur.fetchall()])

def main():
  parser = argparse.ArgumentParser(add_help=False); parser.add_argument("--db", required=True)
  args, _ = parser.parse_known_args()

  st.set_page_config(page_title="EDU ASR Qual Browser", layout="wide")
  st.title("EDU ASR Qual Browser")
  conn = open_db(args.db)

  st.sidebar.header("Filters")
  q = st.sidebar.text_input("Query (FTS5)", '"exit ticket"')
  limit = st.sidebar.number_input("Result limit", min_value=50, max_value=5000, value=500, step=50)

  files = [r[0] for r in conn.execute("SELECT DISTINCT file FROM segments ORDER BY file").fetchall()]
  speakers = [r[0] for r in conn.execute("SELECT DISTINCT speaker FROM segments WHERE speaker IS NOT NULL ORDER BY speaker").fetchall()]
  file_filter = st.sidebar.selectbox("File", ["(Any)"] + files)
  spk_filter = st.sidebar.selectbox("Speaker", ["(Any)"] + speakers)

  if st.sidebar.button("Search") and q.strip():
    df = search(conn, q.strip(), None if file_filter=="(Any)" else file_filter, None if spk_filter=="(Any)" else spk_filter, limit=limit)
    st.write(f"Matches: {len(df)}")
    if not df.empty:
      st.dataframe(df, use_container_width=True)
      st.markdown("---")
      st.subheader("Selected row details")
      idx = st.number_input("Row index", min_value=0, max_value=max(0, len(df)-1), value=0, step=1)
      row = df.iloc[int(idx)]
      st.write(f"**File**: {row['file']}")
      st.write(f"**Speaker**: {row['speaker']}")
      st.write(f"**Time**: {row['start_s']:.1f}–{row['end_s']:.1f} s")
      st.text_area("Text", row["text"], height=200)

  st.sidebar.markdown("---")
  st.sidebar.caption("Tip: Use quotes for exact phrases.")

if __name__ == "__main__":
  main()

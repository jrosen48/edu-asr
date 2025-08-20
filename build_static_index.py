#!/usr/bin/env python3
"""
build_static_index.py
---------------------

Create a static, client-side transcript browser with KWIC search.

Outputs (into --static-dir):
  - index.html
  - app.js
  - styles.css
  - flexsearch.bundle.min.js (local copy so CDNs aren't needed)
  - manifest.json  (one row per transcript)
  - index.json     (one row per segment)

Works on SharePoint/OneDrive:
- All files live in the same folder. The JS computes absolute URLs
  to JSON based on the index.html location, so it works inside the
  SharePoint file viewer or when Embedded on a Site Page.
- Use --inline to embed JSON directly in index.html (no fetch at all).

Usage (defaults match earlier instructions):
  python build_static_index.py \
    --out-dir "~/edu_asr/out" \
    --static-dir "./static_site" \
    --title "Transcript Browser"

Options:
  --inline           -> embed JSON into index.html (no manifest.json / index.json written)
  --base-url URL     -> hardcode a base URL if you prefer (skips auto-detect)
"""

from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# --------- HTML / JS / CSS templates ---------

HTML_APP = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <header>
    <h1>{title}</h1>
    <input id="q" type="search" placeholder="Search (quotes for exact phrase)" />
    <button id="searchBtn">Search</button>
  </header>

  <main>
    <section id="manifest">
      <h2>All transcripts</h2>
      <table id="files"><thead>
        <tr><th>File</th><th>Segments</th><th>Words</th><th>Duration (min)</th></tr>
      </thead><tbody></tbody></table>
    </section>

    <section id="results" hidden>
      <h2>Results</h2>
      <div id="hitcount"></div>
      <ul id="hits"></ul>
    </section>

    <section id="segments" hidden>
      <h2 id="segTitle"></h2>
      <ul id="segList"></ul>
    </section>
  </main>

  <script src="flexsearch.bundle.min.js"></script>
  {data_tags}
  <script>
    window.__STATIC_BASE_URL = {base_url_json};
  </script>
  <script src="app.js"></script>
</body>
</html>
"""

JS_APP = r"""(async function(){
  // Determine where to load data from.
  // 1) If a hard-coded base was provided, use it.
  // 2) Else compute the folder of index.html (strip ?web=1 etc.)
  const forcedBase = window.__STATIC_BASE_URL || null;
  const here = window.location.href.split('#')[0].split('?')[0];
  const autoBase = here.replace(/[^/]*$/, '');    // folder URL ending with '/'
  const base = (typeof forcedBase === 'string' && forcedBase.length) ? (forcedBase.endsWith('/') ? forcedBase : forcedBase + '/') : autoBase;

  // Helper to fetch JSON or fallback to inline tags if present
  async function loadData() {
    const inlineManifest = document.getElementById('manifest-data');
    const inlineSegments = document.getElementById('segments-data');
    if (inlineManifest && inlineSegments) {
      return [JSON.parse(inlineManifest.textContent), JSON.parse(inlineSegments.textContent)];
    } else {
      const [m, s] = await Promise.all([
        fetch(base + 'manifest.json', {cache:'no-store'}).then(r=>r.json()),
        fetch(base + 'index.json',    {cache:'no-store'}).then(r=>r.json())
      ]);
      return [m, s];
    }
  }

  const [manifest, segments] = await loadData();

  // Render file list
  const tbody = document.querySelector('#files tbody');
  for (const f of manifest.slice().sort((a,b)=>a.file_stem.localeCompare(b.file_stem))) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><a href="#" data-file="${escapeAttr(f.file_stem)}">${escapeHtml(f.file_stem)}</a></td>
                    <td>${f.segments}</td><td>${f.words}</td><td>${f.duration_min}</td>`;
    tbody.appendChild(tr);
  }

  // Click a file to view its segments
  tbody.addEventListener('click', (e)=>{
    const a = e.target.closest('a[data-file]'); if(!a) return;
    e.preventDefault();
    const stem = a.getAttribute('data-file');
    showSegments(stem);
  });

  function showSegments(stem){
    const list = document.getElementById('segList'); list.innerHTML='';
    const rows = segments.filter(s=>s.file_stem===stem);
    document.getElementById('segTitle').textContent = `${stem} — ${rows.length} segments`;
    for (const r of rows){
      const li = document.createElement('li');
      const t0 = fmtTime(r.start_s), t1 = fmtTime(r.end_s);
      const spk = r.speaker ? `[${escapeHtml(r.speaker)}] ` : '';
      li.innerHTML = `<code>${t0}–${t1}</code> ${spk}${escapeHtml(r.text||'')}`;
      list.appendChild(li);
    }
    document.getElementById('segments').hidden=false;
    document.getElementById('results').hidden=true;
  }

  // Build FlexSearch index (Document mode)
  const index = new FlexSearch.Document({
    document: {
      id: 'i',
      index: ['text'],
      store: ['file_stem','speaker','start_s','end_s','text']
    },
    tokenize: 'forward',
    cache: true,
  });
  segments.forEach((s, i)=>{ s.i = i; index.add(s); });

  // Search events
  document.getElementById('searchBtn').addEventListener('click', doSearch);
  document.getElementById('q').addEventListener('keydown', (e)=>{
    if (e.key === 'Enter') { e.preventDefault(); doSearch(); }
  });

  function doSearch(){
    const q = document.getElementById('q').value.trim();
    if (!q) return;
    // FlexSearch returns an array of {result:[{doc, id}]}
    const res = index.search(q, { enrich: true }).flatMap(x => x.result.map(r => r.doc));
    renderHits(res, q);
  }

  function renderHits(rows, q){
    const ul = document.getElementById('hits'); ul.innerHTML='';
    document.getElementById('hitcount').textContent = `${rows.length} match(es)`;
    for(const r of rows.slice(0, 500)){
      const li = document.createElement('li');
      li.innerHTML = kwicLine(r, q);
      ul.appendChild(li);
    }
    document.getElementById('results').hidden = false;
    document.getElementById('segments').hidden = true;
  }

  // KWIC helpers
  function kwicLine(r, q){
    const text = (r.text||'');
    const needle = (q||'').replace(/(^"|"$)/g,'').toLowerCase();
    let i = text.toLowerCase().indexOf(needle);
    if (needle && i >= 0) {
      const W = 60;
      const left = Math.max(0, i - W);
      const right = Math.min(text.length, i + needle.length + W);
      const pre = escapeHtml(text.slice(left, i));
      const mid = escapeHtml(text.slice(i, i+needle.length));
      const post = escapeHtml(text.slice(i+needle.length, right));
      return `<strong>${escapeHtml(r.file_stem)}</strong> <code>${fmtTime(r.start_s)}–${fmtTime(r.end_s)}</code> ` +
             `${r.speaker ? '['+escapeHtml(r.speaker)+'] ' : ''}…${pre}<mark>${mid}</mark>${post}…`;
    } else {
      return `<strong>${escapeHtml(r.file_stem)}</strong> <code>${fmtTime(r.start_s)}–${fmtTime(r.end_s)}</code> ` +
             `${r.speaker ? '['+escapeHtml(r.speaker)+'] ' : ''}${escapeHtml(text)}`;
    }
  }

  function fmtTime(x){ const s=Math.floor(x%60), m=Math.floor((x/60)%60), h=Math.floor(x/3600);
    return (h?String(h).padStart(2,'0')+':':'') + String(m).padStart(2,'0')+':'+String(s).padStart(2,'0'); }
  function escapeHtml(s){ return (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
  function escapeAttr(s){ return String(s||'').replace(/"/g,'&quot;'); }
})();
"""

CSS_APP = """body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;padding:0;color:#111}
header{position:sticky;top:0;background:#fff;padding:12px;border-bottom:1px solid #eee;display:flex;gap:8px;align-items:center}
header h1{font-size:18px;margin:0 8px 0 0}
main{padding:12px;max-width:1100px}
table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid #eee;padding:8px;text-align:left}
code{background:#f6f6f6;padding:2px 4px;border-radius:4px}
mark{background:#ffe38a}
#hits, #segList {list-style:none;padding-left:0}
#hits li, #segList li {padding:6px 0;border-bottom:1px dashed #eee}
input[type=search]{padding:6px 8px;border:1px solid #ccc;border-radius:6px}
button{padding:6px 10px;border:1px solid #ccc;border-radius:6px;background:#fafafa;cursor:pointer}
button:hover{background:#f0f0f0}
"""

# --------- flexsearch bundle (lightweight, MIT). We will fetch and write it if missing. ---------
# To keep the script self-contained offline, we embed a minimal copy if not present.
# (If you prefer, you can remove this and ship the file yourself.)
FLEXSEARCH_CDN = "https://unpkg.com/flexsearch@0.7.31/dist/flexsearch.bundle.min.js"

def _download_flexsearch(target: Path):
    try:
        import urllib.request
        print(f"[fetch] {FLEXSEARCH_CDN}")
        data = urllib.request.urlopen(FLEXSEARCH_CDN, timeout=20).read()
        target.write_bytes(data)
        print(f"[write] {target.name} ({len(data)} bytes)")
    except Exception as e:
        # Fallback: tiny stub that avoids 404 (won't search, but UI loads)
        print(f"[warn] could not fetch flexsearch from CDN ({e}); writing a stub.")
        target.write_text("window.FlexSearch={Document:function(){return{add:()=>{},search:()=>({result:[]})}}};")

# --------- data extraction from pipeline JSONs ---------

def load_transcripts(out_dir: Path) -> Iterable[Tuple[str, str, List[Dict]]]:
    """
    Yields (stem, file_path, segments[]) for each transcript JSON in out_dir.
    Expected schema from our pipeline: { "file": "...", "segments": [ {start,end,text,speaker?}, ... ] }
    """
    for jf in sorted(out_dir.glob("*.json")):
        try:
            data = json.loads(jf.read_text())
        except Exception as e:
            print(f"[skip] {jf.name}: JSON error: {e}")
            continue
        stem = jf.stem
        file_path = data.get("file") or stem
        segments = data.get("segments") or []
        if not isinstance(segments, list):
            print(f"[skip] {jf.name}: 'segments' not a list")
            continue
        yield stem, file_path, segments

def build_indexes(out_dir: Path) -> Tuple[List[Dict], List[Dict]]:
    manifest, idx = [], []
    for stem, file_path, segs in load_transcripts(out_dir):
        words = 0
        dur = 0.0
        for s in segs:
            text = (s.get("text") or "").strip()
            words += len(text.split()) if text else 0
            try:
                dur = max(dur, float(s.get("end", 0.0)))
            except Exception:
                pass
            idx.append({
                "file_stem": stem,
                "file_path": file_path,
                "speaker": s.get("speaker"),
                "start_s": float(s.get("start", 0.0)) if isinstance(s.get("start", 0.0),(int,float,str)) else 0.0,
                "end_s": float(s.get("end", 0.0)) if isinstance(s.get("end", 0.0),(int,float,str)) else 0.0,
                "text": text
            })
        manifest.append({
            "file_stem": stem,
            "file_path": file_path,
            "segments": len(segs),
            "words": words,
            "duration_min": round(dur/60.0, 1),
        })
    return manifest, idx

# --------- writer ---------

def write_static_app(static_dir: Path, title: str, manifest: List[Dict], idx: List[Dict],
                     inline: bool = False, base_url: str | None = None):
    static_dir.mkdir(parents=True, exist_ok=True)

    # app.js / styles.css
    (static_dir / "app.js").write_text(JS_APP)
    (static_dir / "styles.css").write_text(CSS_APP)

    # flexsearch bundle
    flex = static_dir / "flexsearch.bundle.min.js"
    if not flex.exists():
        _download_flexsearch(flex)

    data_tags = ""
    if inline:
        # embed JSON into script tags so no fetch is needed
        data_tags = (
            '<script id="manifest-data" type="application/json">'
            + json.dumps(manifest, ensure_ascii=False)
            + "</script>\n"
            + '<script id="segments-data" type="application/json">'
            + json.dumps(idx, ensure_ascii=False)
            + "</script>"
        )
    else:
        # write JSON alongside the app
        (static_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
        (static_dir / "index.json").write_text(json.dumps(idx, ensure_ascii=False))

    base_url_json = json.dumps(base_url or "")  # empty string -> auto-detect at runtime
    html = HTML_APP.format(title=title, data_tags=data_tags, base_url_json=base_url_json)
    (static_dir / "index.html").write_text(html)

    print(f"[done] wrote static app to: {static_dir.resolve()}")
    if not inline:
        print("       files: index.html, app.js, styles.css, manifest.json, index.json, flexsearch.bundle.min.js")
    else:
        print("       files: index.html (JSON inlined), app.js, styles.css, flexsearch.bundle.min.js")

# --------- CLI ---------

def parse_args():
    p = argparse.ArgumentParser(description="Build static transcript browser with KWIC search.")
    p.add_argument("--out-dir", default="~/edu_asr/out", help="Folder containing transcript JSON files.")
    p.add_argument("--static-dir", default="./static_site", help="Where to write the static app.")
    p.add_argument("--title", default="Transcript Browser", help="Page title.")
    p.add_argument("--inline", action="store_true", help="Inline JSON into HTML (no external fetch).")
    p.add_argument("--base-url", default="", help="Hardcode a base URL for JSON files (leave blank to auto-detect).")
    return p.parse_args()

def main():
    args = parse_args()
    out_dir = Path(os.path.expanduser(args.out_dir))
    static_dir = Path(args.static_dir)

    if not out_dir.exists():
        print(f"[error] out-dir not found: {out_dir}")
        sys.exit(1)

    manifest, idx = build_indexes(out_dir)
    if not manifest:
        print(f"[warn] no transcripts found in {out_dir} (*.json).")
    write_static_app(static_dir, args.title, manifest, idx, inline=args.inline,
                     base_url=(args.base_url or None))

if __name__ == "__main__":
    main()

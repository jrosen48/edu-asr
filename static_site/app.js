(async function(){
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

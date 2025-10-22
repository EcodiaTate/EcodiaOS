'use client';

import { useState } from 'react';

type SearchResult = {
  id: string;          // internal Neo id or event_id/uuid
  labels: string[];
  title?: string;
  summary?: string;
  score?: number;
};

type EdgeDraft = {
  toId: string;
  label: string;
  note?: string;
};

const ADMIN_TOKEN_HEADER = 'X-Admin-Token';
const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000/api';

export default function OriginAdminPage() {
  const [adminToken, setAdminToken] = useState('');
  const [tab, setTab] = useState<'single'|'batch'>('single');

  // Single
  const [title, setTitle] = useState('');
  const [summary, setSummary] = useState('');
  const [what, setWhat] = useState('');
  const [where, setWhere] = useState('');
  const [when, setWhen] = useState(''); // ISO (YYYY-MM-DD or full)
  const [tags, setTags] = useState(''); // comma/semicolon or #tags
  const [alias, setAlias] = useState(''); // optional alias for this node

  // Search & edges
  const [query, setQuery] = useState('');
  const [k, setK] = useState(10);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [picks, setPicks] = useState<Record<string, EdgeDraft>>({});
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');

  const setToastTemp = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3500);
  };

  function parseTags(input: string): string[] {
    if (!input) return [];
    const sep = input.includes(';') ? ';' : ',';
    const parts = input.split(sep)
      .map(s => s.trim().replace(/^#/, ''))
      .filter(Boolean);
    return Array.from(new Set(parts));
  }

  function normalizeISO(s: string): string | null {
    const t = s.trim();
    if (!t) return null;
    const re = /^\d{4}-\d{2}-\d{2}(T[\d:.\-+Z]*)?$/;
    return re.test(t) ? t : null;
  }

  async function callAPI(path: string, init?: RequestInit) {
    if (!adminToken) throw new Error('Admin token required');
    const r = await fetch(`${API_BASE}${path}`, {
      ...(init || {}),
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers || {}),
        [ADMIN_TOKEN_HEADER]: adminToken,
      },
    });
    if (!r.ok) {
      const text = await r.text().catch(()=> '');
      throw new Error(`${r.status} ${r.statusText}${text ? ` - ${text}` : ''}`);
    }
    return r.json();
  }

  async function onSearch() {
    try {
      setBusy(true);
      const data = await callAPI('/origin/search', {
        method: 'POST',
        body: JSON.stringify({ query, k }),
      });
      setResults(data.results || []);
      setToastTemp(`Found ${data.results?.length ?? 0} candidates`);
    } catch (e: any) {
      setToastTemp(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  function togglePick(r: SearchResult) {
    setPicks(prev => {
      const next = { ...prev };
      if (next[r.id]) delete next[r.id];
      else next[r.id] = { toId: r.id, label: '', note: '' };
      return next;
    });
  }

  async function onCreateSingle() {
    try {
      setBusy(true);
      // Create node
      const node = await callAPI('/origin/node', {
        method: 'POST',
        body: JSON.stringify({
          title,
          summary,
          what,
          where: where || null,
          when: normalizeISO(when),
          tags: parseTags(tags),
          alias: alias || null,
        }),
      });

      // Optional edges
      const edges = Object.values(picks).filter(e => e.label?.trim());
      if (edges.length) {
        await callAPI('/origin/edges', {
          method: 'POST',
          body: JSON.stringify({
            from_id: node.event_id,
            edges: edges.map(e => ({
              to_id: e.toId,
              label: e.label.trim(),
              note: e.note || '',
            })),
          }),
        });
      }

      setToastTemp(`Created Origin ${node.event_id} with ${edges.length} edges`);
      setTitle(''); setSummary(''); setWhat(''); setWhere(''); setWhen('');
      setTags(''); setAlias(''); setPicks({});
    } catch (e: any) {
      setToastTemp(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function onBatchUpload(csvText: string) {
    try {
      setBusy(true);
      const res = await callAPI('/origin/batch_csv', {
        method: 'POST',
        body: JSON.stringify({ csv: csvText }),
      });
      setToastTemp(`Batch ok: ${res.created} created, ${res.edges_created} edges${res.errors?.length ? `, ${res.errors.length} row errors` : ''}`);
    } catch (e: any) {
      setToastTemp(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
      <link rel="preconnect" href="https://fonts.googleapis.com"/>
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      <link href="https://fonts.googleapis.com/css2?family=Comfortaa:wght@400;600&family=Fjalla+One&display=swap" rel="stylesheet"/>
      <style>{`.fjalla{font-family:'Fjalla One',sans-serif}.comfortaa{font-family:'Comfortaa',system-ui,sans-serif}`}</style>

      <div className="max-w-6xl mx-auto">
        <header className="mb-6">
          <h1 className="fjalla text-3xl tracking-wide">Origin Injection</h1>
          <p className="comfortaa text-neutral-300 mt-1">
            Admin-only. Nodes are hard-labeled <span className="underline">Origin</span> server-side.
          </p>
        </header>

        {/* Token */}
        <div className="rounded-xl bg-neutral-900 border border-neutral-800 p-4 mb-6">
          <label className="comfortaa text-sm">Admin API Token</label>
          <input
            type="password"
            className="mt-2 w-full rounded-lg bg-neutral-950 border border-neutral-800 px-3 py-2"
            placeholder="Paste admin token..."
            value={adminToken}
            onChange={(e)=>setAdminToken(e.target.value)}
          />
          <p className="comfortaa text-xs text-neutral-400 mt-2">Sent as <code>{ADMIN_TOKEN_HEADER}</code>.</p>
        </div>

        {/* Tabs */}
        <nav className="mb-6 flex gap-3">
          <button onClick={()=>setTab('single')}
                  className={`px-4 py-2 rounded-lg border ${tab==='single'?'bg-neutral-200 text-neutral-900':'bg-neutral-900 text-neutral-100 border-neutral-800'}`}>
            Single Node
          </button>
          <button onClick={()=>setTab('batch')}
                  className={`px-4 py-2 rounded-lg border ${tab==='batch'?'bg-neutral-200 text-neutral-900':'bg-neutral-900 text-neutral-100 border-neutral-800'}`}>
            Batch (CSV)
          </button>
        </nav>

        {tab==='single' ? (
          <div className="grid md:grid-cols-5 gap-6">
            {/* Form */}
            <div className="md:col-span-2 rounded-xl bg-neutral-900 border border-neutral-800 p-4">
              <h2 className="fjalla text-xl mb-3">New Origin Node</h2>
              <div className="space-y-3">
                <TextInput label="Title" value={title} onChange={setTitle}/>
                <TextArea label="Summary" value={summary} onChange={setSummary}/>
                <TextArea label="What (long body)" value={what} onChange={setWhat}/>
                <TextInput label="Where" value={where} onChange={setWhere} placeholder="Sunshine Coast"/>
                <TextInput label="When (ISO8601)" value={when} onChange={setWhen} placeholder="2025-08-01T12:00:00Z"/>
                <TextInput label="Tags (comma/semicolon; #ok)" value={tags} onChange={setTags}/>
                <TextInput label="Alias (optional, use in edges as @alias:foo)" value={alias} onChange={setAlias}/>
                <button disabled={busy} onClick={onCreateSingle}
                        className="mt-2 w-full px-4 py-2 rounded-lg bg-neutral-200 text-neutral-900 hover:opacity-90">
                  {busy ? 'Working…' : 'Create Node (and edges below)'}
                </button>
              </div>
            </div>

            {/* Search & connect */}
            <div className="md:col-span-3 rounded-xl bg-neutral-900 border border-neutral-800 p-4">
              <h2 className="fjalla text-xl mb-3">Search & Connect</h2>
              <div className="flex gap-2 mb-3">
                <input className="flex-1 rounded-lg bg-neutral-950 border border-neutral-800 px-3 py-2"
                       placeholder="keyword or semantic query…" value={query}
                       onChange={(e)=>setQuery(e.target.value)}/>
                <input type="number" min={1} max={50}
                       className="w-20 rounded-lg bg-neutral-950 border border-neutral-800 px-3 py-2"
                       value={k} onChange={(e)=>setK(parseInt(e.target.value||'10',10))}/>
                <button disabled={busy} onClick={onSearch}
                        className="px-4 py-2 rounded-lg bg-neutral-200 text-neutral-900 hover:opacity-90">
                  {busy ? 'Searching…' : 'Search'}
                </button>
              </div>

              <div className="space-y-2">
                {results.map(r => {
                  const picked = !!picks[r.id];
                  return (
                    <div key={r.id} className={`rounded-lg border ${picked?'border-neutral-600 bg-neutral-800':'border-neutral-800'} p-3`}>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="fjalla text-sm">{r.title || '(untitled)'}</div>
                          <div className="comfortaa text-xs text-neutral-400">
                            {(r.labels||[]).join(', ')}{typeof r.score==='number' ? ` • score ${r.score.toFixed(3)}`: ''}
                          </div>
                          {r.summary && <div className="comfortaa text-sm text-neutral-200 mt-1 line-clamp-2">{r.summary}</div>}
                        </div>
                        <button onClick={()=>togglePick(r)}
                                className={`px-3 py-1 rounded-md border ${picked?'bg-neutral-200 text-neutral-900':'bg-neutral-950 text-neutral-100 border-neutral-700'}`}>
                          {picked ? 'Remove' : 'Pick'}
                        </button>
                      </div>

                      {picked && (
                        <div className="mt-3 grid sm:grid-cols-3 gap-2">
                          <input className="rounded-md bg-neutral-950 border border-neutral-800 px-2 py-1"
                                 placeholder="Edge label (e.g. REFERENCES, DERIVES_FROM)"
                                 value={picks[r.id]?.label || ''}
                                 onChange={(e)=>setPicks(prev=>({...prev,[r.id]:{...prev[r.id], label:e.target.value}}))}/>
                          <input className="rounded-md bg-neutral-950 border border-neutral-800 px-2 py-1 sm:col-span-2"
                                 placeholder="Optional note (used in edge embedding)"
                                 value={picks[r.id]?.note || ''}
                                 onChange={(e)=>setPicks(prev=>({...prev,[r.id]:{...prev[r.id], note:e.target.value}}))}/>
                        </div>
                      )}
                    </div>
                  );
                })}
                {!results.length && <div className="comfortaa text-sm text-neutral-400">No results yet. Try a search.</div>}
              </div>
            </div>
          </div>
        ) : (
          <BatchCsvPanel busy={busy} onUpload={onBatchUpload}/>
        )}

        {toast && (
          <div className="fixed bottom-6 right-6 bg-neutral-100 text-neutral-900 px-4 py-2 rounded-lg shadow-lg">
            {toast}
          </div>
        )}
      </div>
    </div>
  );
}

function TextInput({label, value, onChange, placeholder}:{label:string; value:string; onChange:(v:string)=>void; placeholder?:string}) {
  return (
    <div>
      <label className="comfortaa text-sm">{label}</label>
      <input className="mt-1 w-full rounded-lg bg-neutral-950 border border-neutral-800 px-3 py-2"
             value={value} onChange={(e)=>onChange(e.target.value)} placeholder={placeholder}/>
    </div>
  );
}
function TextArea({label, value, onChange}:{label:string; value:string; onChange:(v:string)=>void}) {
  return (
    <div>
      <label className="comfortaa text-sm">{label}</label>
      <textarea rows={4} className="mt-1 w-full rounded-lg bg-neutral-950 border border-neutral-800 px-3 py-2"
                value={value} onChange={(e)=>onChange(e.target.value)}/>
    </div>
  );
}

function BatchCsvPanel({busy, onUpload}:{busy:boolean; onUpload:(csv:string)=>void}) {
  const [csvText, setCsvText] = useState(`title,summary,what,where,when,tags,edges,alias
"Physical Manifestation","A pivotal low point marked by a car crash that sparked Tate Donohoe's philosophical transformation.","Tate's car crash incident represented his physical rock bottom moment - a tangible manifestation of his internal chaos that would later serve as the catalyst for his philosophical transformation and commitment to creating a better world","Sunshine Coast","2023-06-01","founder-origin;rock-bottom;transformation","[]","tate-rock-bottom"
"Ecodia Founded","Formal launch of Ecodia as a vehicle for youth-led impact.","Incorporation and public announcement.","Sunshine Coast","2023-07-15","ecodia;founding","[{\\"to_id\\":\\"@alias:tate-rock-bottom\\",\\"label\\":\\"DERIVES_FROM\\"}]","ecodia-founding"
`);

  return (
    <div className="rounded-xl bg-neutral-900 border border-neutral-800 p-4">
      <h2 className="fjalla text-xl mb-3">Batch Upload (CSV)</h2>
      <p className="comfortaa text-sm text-neutral-300 mb-2">
        Headers: <code>title,summary,what,where,when,tags,edges,alias</code> (alias optional).<br/>
        Use <code>@alias:name</code> inside <code>edges</code> to link rows created in the same file.
      </p>
      <textarea rows={14}
        className="w-full rounded-lg bg-neutral-950 border border-neutral-800 px-3 py-2 font-mono text-sm"
        value={csvText} onChange={e=>setCsvText(e.target.value)} />
      <div className="mt-3">
        <button disabled={busy} onClick={()=>onUpload(csvText)}
                className="px-4 py-2 rounded-lg bg-neutral-200 text-neutral-900 hover:opacity-90">
          {busy ? 'Uploading…' : 'Upload CSV'}
        </button>
      </div>
    </div>
  );
}

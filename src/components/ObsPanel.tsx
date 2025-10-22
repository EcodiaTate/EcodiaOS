import React, { useEffect, useState } from "react";

type AgentRow = { agent: string; calls: number; p50_ms: number; p95_ms: number; success_rate: number };
type Series = { name: string; points: { ts: number; value: number }[] };

export default function ObsPanel() {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [llm, setLlm] = useState<Series | null>(null);
  const [nova, setNova] = useState<Series | null>(null);

  useEffect(() => {
    fetch("/obs/metrics/agents?days=7").then(r => r.json()).then(d => setAgents(d.agents || []));
    fetch("/obs/metrics/series?name=llm_llm_latency_ms&days=7").then(r => r.json()).then(setLlm);
    fetch("/obs/metrics/series?name=nova_propose_ms&days=7").then(r => r.json()).then(setNova);
  }, []);

  return (
    <div className="grid grid-cols-3 gap-4 p-4">
      <div className="col-span-1">
        <h2 className="text-lg font-semibold mb-2">Agents</h2>
        <ul className="space-y-2">
          {agents.map((a) => (
            <li key={a.agent} className="p-3 rounded-xl shadow">
              <div className="font-mono text-sm">{a.agent}</div>
              <div className="text-xs opacity-80">calls: {a.calls} • p50: {Math.round(a.p50_ms)}ms • p95: {Math.round(a.p95_ms)}ms • ok: {Math.round(a.success_rate*100)}%</div>
            </li>
          ))}
        </ul>
      </div>

      <div className="col-span-2">
        <h2 className="text-lg font-semibold mb-2">Latency</h2>
        <div className="grid grid-cols-1 gap-4">
          <LineChart series={llm} title="LLM latency (ms)" />
          <LineChart series={nova} title="Nova propose (ms)" />
        </div>
      </div>
    </div>
  );
}

function LineChart({ series, title }: { series: Series | null; title: string }) {
  if (!series) return <div className="p-4 rounded-xl border">Loading…</div>;
  const width = 640, height = 120, pad = 24;
  const xs = series.points.map(p => p.ts);
  const ys = series.points.map(p => p.value);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const path = series.points.map((p, i) => {
    const x = pad + (width - 2*pad) * ((p.ts - minX) / Math.max(1, (maxX - minX)));
    const y = height - pad - (height - 2*pad) * ((p.value - minY) / Math.max(1, (maxY - minY)));
    return `${i ? "L" : "M"}${x},${y}`;
  }).join(" ");

  return (
    <div className="p-4 rounded-xl border">
      <div className="mb-2">{title}</div>
      <svg width={width} height={height}>
        <path d={path} fill="none" strokeWidth={2}/>
      </svg>
    </div>
  );
}

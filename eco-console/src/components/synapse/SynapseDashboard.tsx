// src/components/synapse/SynapseDashboard.tsx
import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Brush } from 'recharts';
import Card from '../common/Card';
import { theme } from '../../theme';
import bffClient from '../../api/bffClient';
import toast from 'react-hot-toast';
import { LoadingSpinner } from '../ui/LoadingSpinner';
import { ErrorDisplay } from '../ui/ErrorDisplay';
import { DataTable } from '../ui/DataTable';
import { useQuery } from '@tanstack/react-query';
import type { Outcome } from '../../types/synapse';
import { OutcomeGraph } from './OutcomeGraph';
import { OutcomeHeatmap } from './OutcomeHeatmap';
import { OutcomeLeaderboard } from './OutcomeLeaderboard';
import { OutcomeTable } from './OutcomeTable';
import { DownloadCSV } from './DownloadCSV';

type GroupKey = 'strategy' | 'model' | 'tokenizer';

// Local style because theme.styles has no `input`
const selectStyle: CSSProperties = {
  padding: '8px 12px',
  background: (theme as any).colors?.card || 'transparent',
  color: (theme as any).colors?.ink || 'inherit',
  border: `1px solid ${(theme as any).colors?.edge || '#444'}`,
  borderRadius: '8px',
};

// ===== Types =====
interface LeaderboardRow { arm_id: string; score: number; mode?: string; tasks?: number }
interface ToolsListResp {
  status: string;
  count: number;
  tools?: { name: string; spec?: Record<string, any> }[];
  names?: string[];
}

// ===== API map (ONLY routes that actually exist/mounted) =====
const API = {
  leaderboard: (days = 7, top_k = 12) => `/synapse/metrics/leaderboard?days=${days}&top_k=${top_k}`,
  reloadRegistry: `/synapse/registry/reload`,
  toolsList: `/synapse/tools?names_only=false`,
  submitArmPreference: `/synapse/ingest/preference`, // { winner, loser, source? }
};

const SynapseDashboard = () => {
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [tools, setTools] = useState<ToolsListResp | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [pickA, setPickA] = useState<string>('');
  const [pickB, setPickB] = useState<string>('');

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const [lbResp, toolsResp] = await Promise.all([
          bffClient.get(API.leaderboard()) as Promise<any>,
          bffClient.get(API.toolsList) as Promise<ToolsListResp>,
        ]);
        setLeaderboard(normalizeLeaderboard(lbResp));
        setTools(toolsResp);
      } catch (err: any) {
        setError(err?.message || String(err));
        console.error('Failed to fetch Synapse data', err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, []);

  const { data: outcomes } = useQuery<Outcome[]>({
    queryKey: ['synapse-outcomes'],
    queryFn: async () => {
      const res = await fetch('/api/obs/outcomes');
      if (!res.ok) throw new Error('Failed to load outcomes');
      return res.json();
    },
  });

  const [groupBy, setGroupBy] = useState<GroupKey>('strategy');

  const armOptions = useMemo(() => {
    const ids = Array.from(new Set(leaderboard.map((r) => r.arm_id))).sort();
    return ids;
  }, [leaderboard]);

  const handleSubmitPref = async () => {
    if (!pickA || !pickB || pickA === pickB) {
      toast.error('Pick two different arms.');
      return;
    }
    setSubmitting(true);
    const toastId = toast.loading('Submitting preference...');
    try {
      await bffClient.post(API.submitArmPreference, { winner: pickA, loser: pickB, source: 'ui' });
      toast.success('Preference recorded', { id: toastId });
    } catch (err: any) {
      toast.error(`Failed to submit preference: ${err?.message || err}`, { id: toastId });
    } finally {
      setSubmitting(false);
    }
  };

  const handleReload = async () => {
    const toastId = toast.loading('Triggering registry reload...');
    try {
      await bffClient.post(API.reloadRegistry, {});
      toast.success('Synapse registry reload triggered!', { id: toastId });
    } catch (err: any) {
      toast.error(`Failed to reload registry: ${err.message || err}`, { id: toastId });
    }
  };

  if (isLoading) return <LoadingSpinner text="Loading Synapse Data..." />;
  if (error) return <ErrorDisplay error={error} context="Synapse Dashboard" />;

  return (
    <div style={{ display: 'grid', gap: '24px', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))' }}>
      {/* Preference voting (Arm vs Arm) using the mounted ingest endpoint */}
      <Card title="Alignment Preference Voting (Arm vs Arm)">
        <p style={{ margin: '0 0 12px', color: theme.colors.muted }}>Record which arm you prefer overall right now.</p>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <select value={pickA} onChange={(e) => setPickA(e.target.value)} style={{ ...selectStyle, minWidth: 220 }}>
            <option value="">Pick winner arm…</option>
            {armOptions.map((id) => (
              <option key={`a-${id}`} value={id}>
                {id}
              </option>
            ))}
          </select>
          <span style={{ color: theme.colors.muted }}>over</span>
          <select value={pickB} onChange={(e) => setPickB(e.target.value)} style={{ ...selectStyle, minWidth: 220 }}>
            <option value="">Pick loser arm…</option>
            {armOptions.map((id) => (
              <option key={`b-${id}`} value={id}>
                {id}
              </option>
            ))}
          </select>
          <button disabled={submitting} style={theme.styles.button} onClick={handleSubmitPref}>
            {submitting ? 'Submitting…' : 'Submit Preference'}
          </button>
        </div>
      </Card>

      <Card title="Controls">
        <p style={{ margin: '0 0 16px', color: theme.colors.muted }}>
          Trigger a hot-reload of the Arm Registry from the Neo4j graph.
        </p>
        <button onClick={handleReload} style={theme.styles.button}>
          Reload Arm Registry
        </button>
      </Card>

      <Card title="Tools Registry Explorer" style={{ gridColumn: '1 / -1' }}>
        <DataTable
          headers={[
            { key: 'name', label: 'Tool' },
            { key: 'desc', label: 'Description' },
          ]}
          rows={(tools?.tools ?? []).map((t) => ({
            name: <span style={{ fontFamily: 'monospace' }}>{t.name}</span>,
            desc: (t.spec && (t.spec.description || t.spec.desc)) || '—',
          }))}
        />
      </Card>

      <Card title="Policy Arm Leaderboard" style={{ gridColumn: '1 / -1' }}>
        <>
          <div style={{ height: '400px', marginBottom: '24px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={leaderboard} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.colors.edge} />
                <XAxis
                  dataKey="arm_id"
                  stroke={theme.colors.muted}
                  fontSize={12}
                  interval={0}
                  angle={-30}
                  textAnchor="end"
                  height={80}
                />
                <YAxis stroke={theme.colors.muted} fontSize={12} />
                <Tooltip
                  contentStyle={{
                    background: theme.colors.card,
                    borderColor: theme.colors.edge,
                    color: theme.colors.ink,
                  }}
                  cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                />
                <Legend wrapperStyle={{ fontSize: 14 }} />
                <Bar dataKey="score" fill={theme.colors.g3} />
                <Brush dataKey="arm_id" height={30} stroke={theme.colors.g2} fill="rgba(0,0,0,0.2)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <DataTable
            headers={[
              { key: 'arm_id', label: 'Arm ID' },
              { key: 'mode', label: 'Mode', style: { textAlign: 'center' } },
              { key: 'score', label: 'Score', style: { textAlign: 'center' } },
              { key: 'tasks', label: 'Tasks', style: { textAlign: 'center' } },
            ]}
            rows={leaderboard.map((arm) => ({
              arm_id: <span style={{ fontFamily: 'monospace' }}>{arm.arm_id}</span>,
              mode: arm.mode ?? '—',
              score: Number.isFinite(arm.score) ? arm.score.toFixed(2) : 'N/A',
              tasks: arm.tasks ?? '—',
            }))}
          />
        </>
      </Card>

      {outcomes && (
        <Card title="Outcomes Explorer" style={{ gridColumn: '1 / -1' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <label>Group by:</label>
            <select value={groupBy} onChange={(e) => setGroupBy(e.target.value as GroupKey)} style={selectStyle}>
              <option value="strategy">Strategy</option>
              <option value="model">Model</option>
              <option value="tokenizer">Tokenizer</option>
            </select>
            <DownloadCSV data={outcomes} />
          </div>
          <OutcomeGraph data={outcomes} groupBy={groupBy} />
          <OutcomeHeatmap data={outcomes} groupBy={groupBy} />
          <OutcomeLeaderboard data={outcomes} groupBy={groupBy} />
          <OutcomeTable data={outcomes} />
        </Card>
      )}
    </div>
  );
};

export default SynapseDashboard;

// ===== helpers =====
function normalizeLeaderboard(raw: any): LeaderboardRow[] {
  if (raw && Array.isArray(raw.rows)) return raw.rows as LeaderboardRow[];
  if (raw && (Array.isArray(raw.top) || Array.isArray(raw.bottom))) {
    const pick = (arr: any[]) =>
      (arr || []).map(
        (r: any) =>
          ({
            arm_id: r.arm_id || r.id || r.name || 'unknown',
            score: toNum(r.score ?? r.avg_roi ?? r.roi ?? 0),
            mode: r.mode,
            tasks: toNum(r.tasks ?? r.count ?? r.n ?? 0),
          } as LeaderboardRow)
      );
    const rows = [...pick(raw.top || []), ...pick(raw.bottom || [])];
    const byId = new Map<string, LeaderboardRow>();
    for (const r of rows) {
      const prev = byId.get(r.arm_id);
      if (!prev || (Number.isFinite(r.score) && r.score > (prev.score ?? -Infinity))) byId.set(r.arm_id, r);
    }
    return Array.from(byId.values());
  }
  if (Array.isArray(raw)) {
    return raw.map(
      (r: any) =>
        ({
          arm_id: r.arm_id || r.id || 'unknown',
          score: toNum(r.score ?? 0),
          mode: r.mode,
          tasks: toNum(r.tasks ?? 0),
        } as LeaderboardRow)
    );
  }
  return [];
}

function toNum(x: any): number {
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}

// ===== FILE: src/components/unity/UnityDashboard.tsx =====
import { useState, useEffect, useCallback } from 'react';
import Card from '../common/Card';
import { theme } from '../../theme';
import bffClient from '../../api/bffClient';

// --- Type Definitions ---
interface DeliberationSummary {
  id: string;
  topic: string;
  status: string;
  created_at: string;
}

interface TranscriptTurn {
  turn: number;
  role: string;
  content: string;
}

interface Verdict {
  outcome: string;
  confidence: number;
  dissent: string | null;
}

interface FullDeliberation {
  session: { id: string; topic: string };
  transcript: TranscriptTurn[];
  verdict: Verdict | null;
}

const UnityDashboard = () => {
  const [deliberations, setDeliberations] = useState<DeliberationSummary[]>([]);
  const [selected, setSelected] = useState<FullDeliberation | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // fetch details for a given session id
  const handleSelect = useCallback(
    async (sessionId: string) => {
      if (selected?.session.id === sessionId) return; // avoid redundant fetch
      setIsLoadingDetails(true);
      try {
        const data: FullDeliberation = await bffClient.get(`/operations/unity/deliberation/${sessionId}`);
        setSelected(data);
      } catch (err: any) {
        alert(`Failed to fetch deliberation details: ${err.message || err}`);
      } finally {
        setIsLoadingDetails(false);
      }
    },
    [selected?.session.id]
  );

  // fetch list on mount, then auto-select the first item (if any)
  useEffect(() => {
    const fetchList = async () => {
      setIsLoadingList(true);
      setError(null);
      try {
        const data: DeliberationSummary[] = await bffClient.get('/operations/unity/deliberations');
        setDeliberations(data);
        if (data && data.length > 0) {
          // auto-select first item
          handleSelect(data[0].id);
        } else {
          setSelected(null);
        }
      } catch (err: any) {
        setError(err.message || 'Failed to fetch deliberation list.');
        console.error('Failed to fetch deliberation list', err);
      } finally {
        setIsLoadingList(false);
      }
    };
    fetchList();
  }, [handleSelect]);

  return (
    <Card title="Deliberation Room">
      <div style={{ display: 'flex', gap: '24px', minHeight: '60vh' }}>
        <div style={{ width: '30%', borderRight: `1px solid ${theme.colors.edge}`, paddingRight: '24px' }}>
          <h4 style={{ fontFamily: theme.fonts.heading, margin: '0 0 16px' }}>Recent Deliberations</h4>
          {isLoadingList ? (
            <p>Loading...</p>
          ) : error ? (
            <p style={{ color: '#ef4444' }}>{error}</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {deliberations.map((d) => {
                const isActive = selected?.session.id === d.id;
                return (
                  <li
                    key={d.id}
                    onClick={() => handleSelect(d.id)}
                    style={{
                      padding: '10px',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      marginBottom: '8px',
                      background: isActive ? 'rgba(244, 211, 94, .15)' : 'rgba(255,255,255,.05)',
                      border: `1px solid ${isActive ? theme.colors.g3 : 'transparent'}`,
                    }}
                  >
                    <strong style={{ color: theme.colors.ink }}>{d.topic}</strong>
                    <span style={{ display: 'block', fontSize: '12px', color: theme.colors.muted }}>{d.status}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div style={{ width: '70%' }}>
          {isLoadingDetails ? (
            <p>Loading details...</p>
          ) : !selected ? (
            <p style={{ color: theme.colors.muted }}>Select a deliberation to view its transcript.</p>
          ) : (
            <>
              <h4 style={{ fontFamily: theme.fonts.heading, margin: '0 0 16px' }}>{selected.session.topic}</h4>

              {selected.verdict ? (
                <div style={{ ...theme.styles.card, background: 'rgba(0,0,0,.2)', marginBottom: '16px' }}>
                  <strong>
                    Verdict: {selected.verdict.outcome}
                  </strong>{' '}
                  (Confidence: {(selected.verdict.confidence * 100).toFixed(1)}%)
                  {selected.verdict.dissent && (
                    <p
                      style={{
                        margin: '8px 0 0',
                        color: theme.colors.muted,
                        fontSize: '14px',
                        fontStyle: 'italic',
                      }}
                    >
                      {selected.verdict.dissent}
                    </p>
                  )}
                </div>
              ) : (
                <p style={{ color: theme.colors.muted, marginBottom: '16px' }}>Verdict not yet finalized.</p>
              )}

              <div style={{ maxHeight: '50vh', overflowY: 'auto', paddingRight: '10px' }}>
                {selected.transcript.map((turn) => (
                  <div key={turn.turn} style={{ marginBottom: '16px' }}>
                    <strong style={{ fontFamily: theme.fonts.heading, color: theme.colors.g3 }}>
                      {turn.role} (Turn {turn.turn}):
                    </strong>
                    <p
                      style={{
                        whiteSpace: 'pre-wrap',
                        fontFamily: 'monospace',
                        margin: '4px 0 0',
                        color: theme.colors.muted,
                        fontSize: '14px',
                      }}
                    >
                      {turn.content}
                    </p>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </Card>
  );
};

export default UnityDashboard;

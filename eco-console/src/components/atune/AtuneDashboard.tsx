/* D:\EcodiaOS\eco-console\src\components\atune\AtuneDashboard.tsx */
// ===== FILE: src/components/atune/AtuneDashboard.tsx =====
import React, { useState, useEffect } from 'react';
import Card from '../common/Card';
import { theme } from '../../theme';
import bffClient from '../../api/bffClient';
// Import the context hook to access global state
import { useAppContext } from '../../context/AppContext';

// --- Type Definitions ---
interface AtuneStatus {
  budget: { available_ms_now: number | null };
  focus: { leak_gamma: number |
 null };
}
interface AffectiveState {
  curiosity: number;
  caution: number;
  integrity_load: number;
  focus_fatigue: number;
}
interface WhyTraceData {
    // Define the shape of the trace data based on the backend response
    why_trace: any;
    replay_capsule: any;
}

const AtuneDashboard = () => {
  // Get the activeDecisionId and its setter from the global context
  const { activeDecisionId, setActiveDecisionId } = useAppContext();
  const [status, setStatus] = useState<AtuneStatus | null>(null);
  const [affect, setAffect] = useState({ curiosity: 0.6, caution: 0.3 });
  const [traceData, setTraceData] = useState<WhyTraceData | null>(null);
  const [isTraceLoading, setIsTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [isStatusLoading, setIsStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Effect for fetching the Atune system status (runs once on mount)
  useEffect(() => {
    const fetchStatus = async () => {
      setIsStatusLoading(true);
      setStatusError(null);
      try {
        const data: AtuneStatus = await bffClient.get('/observability/atune/status');
        setStatus(data);
      } catch (err: any) {
        const errorMsg = err.message || "Failed to fetch Atune status.";
        
        setStatusError(errorMsg);
        console.error("Failed to fetch Atune status", err);
      } finally {
        setIsStatusLoading(false);
      }
    };
    fetchStatus();
  }, []);

  // Effect for fetching the WhyTrace data whenever the activeDecisionId changes
  useEffect(() => {
    const fetchTrace = async () => {
      if (!activeDecisionId) {
        setTraceData(null);
        setTraceError(null);
        return;
      }
      setIsTraceLoading(true);
      setTraceError(null);
      setTraceData(null);
      try {
        const data: WhyTraceData = await 
        bffClient.get(`/atune/trace/${activeDecisionId}`);
        setTraceData(data);
      } catch (err: any) {
        const errorMsg = err.message || `Failed to fetch trace for ID: ${activeDecisionId}`;
        setTraceError(errorMsg);
        console.error("Failed to fetch WhyTrace", err);
      } finally {
        setIsTraceLoading(false);
      }
    };

    fetchTrace();
  }, [activeDecisionId]);

  const handleModulate = async () => {
    try {
      const payload: AffectiveState = { ...affect, integrity_load: 0.1, focus_fatigue: 0.0 };
      await bffClient.post('/observability/atune/modulate', payload);
      alert('Affective state modulated for the next cognitive cycle!');
    } catch (err: any) {
      alert(`Failed to modulate Atune: ${err.message || err}`);
    }
  };

  const renderStatusContent = () => {
    if (isStatusLoading) return <p>Loading live system data...</p>;
    if (statusError) return <p style={{ color: '#ef4444' }}>Error: {statusError}</p>;
    return (
      <>
        {status && (
            <div style={{ marginBottom: '24px', paddingBottom: '16px', borderBottom: `1px solid ${theme.colors.edge}` }}>
                <p style={{ margin: '0 0 8px', fontFamily: theme.fonts.heading }}>Live Metrics:</p>
                <span style={{ color: theme.colors.muted, fontSize: '14px' }}>Cognitive Budget: <strong>{status.budget.available_ms_now?.toFixed(0) ?? 'N/A'} 
ms</strong></span>
                <span style={{ color: theme.colors.muted, fontSize: '14px', marginLeft: '16px' }}>Salience Leak (Gamma): <strong>{status.focus.leak_gamma?.toFixed(4) ?? 'N/A'}</strong></span>
            </div>
        )}
        <div>
          <label>Curiosity: {affect.curiosity.toFixed(2)}</label>
          <input type="range" min="0" max="1" step="0.05" value={affect.curiosity}
            onChange={(e) => setAffect({ ...affect, curiosity: 
            parseFloat(e.target.value) })}
            style={{ width: '100%' }} />
        </div>
        <div style={{ marginTop: '16px' }}>
          <label>Caution: {affect.caution.toFixed(2)}</label>
          <input type="range" min="0" max="1" step="0.05" value={affect.caution}
            onChange={(e) => setAffect({ ...affect, caution: parseFloat(e.target.value) })}
            style={{ width: '100%' }} />
   
        </div>
        <button onClick={handleModulate} style={{...theme.styles.button, marginTop: '20px'}}>Apply Modulation</button>
      </>
    );
  };

  const renderTraceContent = () => {
    if (isTraceLoading) return <p>Loading trace...</p>;
    if (traceError) return <p style={{ color: '#ef4444' }}>Error: {traceError}</p>;
    if (traceData) {
        return (
            <pre style={{
                background: 'rgba(0,0,0,.2)',
                padding: '16px',
                borderRadius: '8px',
                
                fontSize: '12px',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                maxHeight: '400px',
                overflowY: 'auto',
                border: `1px solid ${theme.colors.edge}`,
            
            }}>
                {JSON.stringify(traceData, null, 2)}
            </pre>
        );
    }
    return <p style={{color: theme.colors.muted}}>Enter a Decision ID above, or click a conflict in the Evo dashboard to begin.</p>;
  };

  return (
    <div style={{ display: 'grid', gap: '24px', gridTemplateColumns: '1fr 1fr' }}>
      <Card title="Live System Affect">
        {renderStatusContent()}
      </Card>
      
      <Card title="WhyTrace Explorer">
        <input 
            type="text" 
            placeholder="e.g., auto-7cc0517a..." 
            
            value={activeDecisionId || ''}
            onChange={(e) => setActiveDecisionId(e.target.value)}
            style={{
                width: '100%',
                padding: '10px',
                background: 'rgba(0,0,0,.3)',
                border: `1px solid ${theme.colors.edge}`,
  
                borderRadius: '6px',
                color: theme.colors.ink,
                marginBottom: '16px'
            }}
        />
        {renderTraceContent()}
      </Card>
    </div>
  );
};

export default AtuneDashboard;
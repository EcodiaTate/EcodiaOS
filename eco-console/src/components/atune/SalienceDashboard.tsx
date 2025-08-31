/* D:\EcodiaOS\eco-console\src\components\atune\SalienceDashboard.tsx */
// src/components/atune/SalienceDashboard.tsx
import React, { useState, useEffect } from 'react';
import bffClient from '../../api/bffClient';

// --- FIX: Add full type definitions for the data contract ---
interface AtuneStatus {
  now_utc: string;
  budget: {
    pool_ms_per_tick: number;
    available_ms_now: number;
  };
  focus: {
    leak_gamma: number;
  };
  env_flags: Record<string, string>;
  secl: {
    counters: Record<string, number>;
    gauges: Record<string, number>;
    info: Record<string, any>;
  };
}

interface AffectiveState {
  curiosity: number;
  caution: number;
  integrity_load: number;
  focus_fatigue: number;
}

const SalienceDashboard = () => {
  const [status, setStatus] = useState<AtuneStatus | null>(null);
  const [affect, setAffect] = useState({ curiosity: 0.5, caution: 0.2 });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = async () => {
      setIsLoading(true);
      try {
        // --- FIX: Use async/await and explicitly type the response data ---
        const data: AtuneStatus = await bffClient.get('/observability/atune/status');
        setStatus(data);
      } catch (error) {
        console.error("Failed to fetch Atune status", error);
      } finally {
     
        setIsLoading(false);
      }
    };
    fetchStatus();
  }, []);

  const handleModulate = async () => {
    try {
      const payload: AffectiveState = { ...affect, integrity_load: 0.1, focus_fatigue: 0.0 };
      await bffClient.post('/observability/atune/modulate', payload);
      alert('Affective state modulated for the next cognitive cycle!');
    } catch (error) {
      alert(`Failed to modulate Atune: ${error}`);
    }
  };

  if (isLoading) {
    return <div>Loading Atune Dashboard...</div>;
  }

  return (
    <div>
      <h2>Atune Salience Dashboard</h2>
      {status ? (
        <div>
          <p>Available Budget: <strong>{status.budget.available_ms_now} ms</strong></p>
          <p>Salience Leak (Gamma): <strong>{status.focus.leak_gamma.toFixed(4)}</strong></p>
          {/* Add more status displays here */}
        </div>
      ) : <p>Could not load Atune status.</p>}

      <hr 
/>
      <h4>Modulate Affective State</h4>
      <div>
        <label>Curiosity: {affect.curiosity.toFixed(2)}</label>
        <input
          type="range" min="0" max="1" step="0.05"
          value={affect.curiosity}
          onChange={(e) => setAffect({ ...affect, curiosity: parseFloat(e.target.value) })}
        />
      </div>
      <div>
        <label>Caution: {affect.caution.toFixed(2)}</label>
 
        <input
          type="range" min="0" max="1" step="0.05"
          value={affect.caution}
          onChange={(e) => setAffect({ ...affect, caution: parseFloat(e.target.value) })}
        />
      </div>
      <button onClick={handleModulate}>Apply Modulation</button>
    </div>
  );
};

export default SalienceDashboard;
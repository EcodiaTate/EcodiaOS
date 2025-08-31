/* D:\EcodiaOS\eco-console\src\hooks\useSystemHealth.ts */
// ===== FILE: src/hooks/useSystemHealth.ts =====
import { useState, useEffect } from 'react';
import bffClient from '../api/bffClient';

interface HealthStatus {
  name: string;
  ok: boolean;
  status: string;
  via: string | null;
  latency_ms: number;
}

// Define the shape of the data returned by the BFF client after the interceptor
interface AppStatusResponse {
    overall: string;
    systems: HealthStatus[];
}

interface HealthEntry {
  ok: boolean;
  via: string | null;
}

const initialHealth: Record<string, HealthEntry> = {
  atune: { ok: false, via: null },
  synapse: { ok: false, via: null },
  unity: { ok: false, via: null },
  equor: { ok: false, via: null },
  qora: { ok: false, via: null },
  simula: { ok: false, via: null },
  evo: { ok: false, via: null },
};

export const useSystemHealth = (refreshIntervalMs: number = 5000) => {
  const [health, setHealth] = useState(initialHealth);
  const [allOk, setAllOk] = useState(false);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        // FIX: Assert the correct type for the response after the interceptor runs.
        const response = await bffClient.get('/app/status') as AppStatusResponse;
        
        // Now, TypeScript understands that response.systems is a valid property.
        const systems: HealthStatus[] = response.systems || [];
   
              
        const newHealth = { ...initialHealth };
        let overallOk = true;

        systems.forEach(system => {
          if (newHealth.hasOwnProperty(system.name)) {
            newHealth[system.name as keyof typeof newHealth] = { ok: system.ok, via: system.via };
            if (!system.ok) overallOk = false;
  
          }
        });

        setHealth(newHealth);
        setAllOk(overallOk);
      } catch (error) {
        console.error("Failed to fetch system health", error);
        // Set all to not-OK on any API failure
        const errorHealth = { ...initialHealth };
        Object.keys(errorHealth).forEach(key => {
            errorHealth[key as keyof typeof errorHealth] = { ok: false, via: 'Error fetching status' };
        });
        setHealth(errorHealth);
        setAllOk(false);
      }
    };

    fetchHealth();
    const intervalId = setInterval(fetchHealth, refreshIntervalMs);
    return () => clearInterval(intervalId);
  }, [refreshIntervalMs]);

  return { health, allOk };
};
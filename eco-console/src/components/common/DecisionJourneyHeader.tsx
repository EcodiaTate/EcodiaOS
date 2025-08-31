// src/components/common/DecisionJourneyHeader.tsx

import React, { useState, useEffect } from 'react';
import { useAppContext } from '../../context/AppContext';
import { theme } from '../../theme';
import bffClient from '../../api/bffClient';

const DecisionJourneyHeader = () => {
  const { activeDecisionId, clearDecisionId, navigateToTrace } = useAppContext();
  const [journeyInfo, setJourneyInfo] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!activeDecisionId) {
      setJourneyInfo(null);
      return;
    }

    const fetchJourneyInfo = async () => {
      setIsLoading(true);
      try {
        const data = await bffClient.get(`/decision_journey/${activeDecisionId}`);
        setJourneyInfo(data);
      } catch (error) {
        console.error("Failed to fetch journey info:", error);
        setJourneyInfo({ error: 'Could not load journey details.' });
      } finally {
        setIsLoading(false);
      }
    };

    fetchJourneyInfo();
  }, [activeDecisionId]);

  if (!activeDecisionId) {
    return null;
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '12px 24px',
      background: 'rgba(244, 211, 94, .15)',
      borderBottom: `1px solid ${theme.colors.g3}`,
      color: theme.colors.g3,
      fontFamily: theme.fonts.heading
    }}>
      <div>
        <span>DECISION JOURNEY: </span>
        <strong style={{ fontFamily: 'monospace', marginLeft: '8px' }}>{activeDecisionId}</strong>
        {isLoading && <span style={{ marginLeft: '16px' }}>Loading details...</span>}
        {journeyInfo?.conflict?.description && <span style={{ marginLeft: '16px', color: theme.colors.muted }}>Conflict: {journeyInfo.conflict.description}</span>}
      </div>
      <div>
        <button onClick={() => navigateToTrace(activeDecisionId)} style={{ ...theme.styles.button, padding: '4px 12px', fontSize: '12px', background: 'transparent', border: `1px solid ${theme.colors.g3}`, color: theme.colors.g3, marginRight: '16px' }}>
          View Trace
        </button>
        <button onClick={clearDecisionId} style={{ background: 'none', border: 'none', color: theme.colors.g3, cursor: 'pointer', fontSize: '18px', fontWeight: 'bold' }}>
          &times;
        </button>
      </div>
    </div>
  );
};

export default DecisionJourneyHeader;
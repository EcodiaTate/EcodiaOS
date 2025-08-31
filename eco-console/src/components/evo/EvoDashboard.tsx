// src/components/evo/EvoDashboard.tsx
import React from 'react';
import Card from '../common/Card';
import { theme } from '../../theme';
import { useAppContext } from '../../context/AppContext';
import { usePolling } from '../../hooks/usePolling'; // REFACTORED: Import usePolling
import { LoadingSpinner } from '../ui/LoadingSpinner';
import { ErrorDisplay } from '../ui/ErrorDisplay';

interface Conflict {
    id: string;
    severity: 'low' | 'medium' | 'high' | 'critical';
    description: string;
}

interface EvoResponse {
    conflicts: Conflict[];
}

const EvoDashboard = () => {
    const { navigateToTrace } = useAppContext();
    // REFACTORED: Use the polling hook for live data
    const { data: conflicts, isLoading, error } = usePolling<Conflict[]>('/governance/evo/conflicts');

    const renderContent = () => {
        if (isLoading) return <LoadingSpinner text="Loading open conflicts..." />;
        if (error) return <ErrorDisplay error={error} context="Evo Conflicts" />;
        if (!conflicts || conflicts.length === 0) return <p style={{ color: theme.colors.muted }}>No open conflicts found.</p>;

        const normalizedConflicts = conflicts.map(c => ({
            id: c.id,
            severity: c.severity || 'medium',
            description: c.description || 'No description available.'
        }));

        return normalizedConflicts.map(c => (
            <div 
                key={c.id} 
                onClick={() => navigateToTrace(c.id)}
                style={{ 
                    border: `1px solid ${theme.colors.edge}`, 
                    padding: '12px', 
                    borderRadius: '8px', 
                    marginBottom: '12px',
                    cursor: 'pointer',
                    transition: 'background-color 0.2s ease'
                }}
                onMouseOver={e => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)'}
                onMouseOut={e => e.currentTarget.style.backgroundColor = 'transparent'}
            >
                <strong style={{ color: theme.colors.ink }}>{c.description}</strong>
                <span style={{ display: 'block', fontSize: '12px', color: c.severity === 'high' || c.severity === 'critical' ? '#f87171' : '#facc15', fontFamily: theme.fonts.heading, marginTop: '4px' }}>
                    SEVERITY: {c.severity.toUpperCase()}
                </span>
                <span style={{ display: 'block', fontSize: '10px', color: theme.colors.muted, fontFamily: 'monospace', marginTop: '8px' }}>
                    Decision ID: {c.id}
                </span>
            </div>
        ));
    };

    return (
      <Card title="Conflict Center (Live)">
        <p style={{margin: '0 0 16px', color: theme.colors.muted}}>Live queue of open conflicts detected within the system. Click an item to trace its decision.</p>
        <div>
            {renderContent()}
        </div>
      </Card>
    );
};
export default EvoDashboard;
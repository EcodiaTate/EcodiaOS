/* D:\EcodiaOS\eco-console\src\components\equor\EquorDashboard.tsx */
// ===== FILE: src/components/equor/EquorDashboard.tsx =====
import React, { useState, useEffect } from 'react';
import Card from '../common/Card';
import { theme } from '../../theme';
import bffClient from '../../api/bffClient';

interface Rule {
    id: string;
    pattern: string;
    active: boolean;
}

const EquorDashboard = () => {
    const [rules, setRules] = useState<Rule[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchRules = async () => {
            setIsLoading(true);
            setError(null);
            try {
                const fetchedRules: Rule[] = await bffClient.get('/governance/equor/rules');
                setRules(fetchedRules);
          
            } catch (err: any) {
                setError(err.message || "Failed to fetch Equor rules.");
                console.error("Failed to fetch Equor rules.", err);
            } finally {
                setIsLoading(false);
            }
        };

 
        fetchRules();
    }, []);

    const renderContent = () => {
        if (isLoading) return <p>Loading constitution rules...</p>;
        if (error) return <p style={{ color: '#ef4444' }}>Error: {error}</p>;
        if (rules.length === 0) return <p style={{ color: theme.colors.muted }}>No constitution rules found.</p>;

        return (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
              <thead>
                <tr>
                  <th style={{...tableHeaderStyle, textAlign: 'left'}}>Rule ID</th>
                  <th style={{...tableHeaderStyle, textAlign: 'left'}}>Pattern</th>
      
                  <th style={tableHeaderStyle}>Status</th>
                </tr>
              </thead>
              <tbody>
                {rules.map(rule => (
                  <tr key={rule.id}>
      
                    <td style={{...tableCellStyle, textAlign: 'left', fontFamily: 'monospace'}}>{rule.id}</td>
                    <td style={{...tableCellStyle, textAlign: 'left', fontFamily: 'monospace', color: theme.colors.muted }}>{rule.pattern}</td>
                    <td style={{...tableCellStyle, color: rule.active ? theme.colors.g2 : '#ef4444' }}>
                      {rule.active ? 'ACTIVE' 
 : 'INACTIVE'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
        );
    };

    return (
      <Card title="Equor Constitution">
        <p style={{margin: '0 0 16px', color: theme.colors.muted}}>Core safety rules governing system behavior. Active rules are enforced by the Adjudicator and safety firewalls.</p>
        {renderContent()}
      </Card>
    );
};

const tableHeaderStyle: React.CSSProperties = { borderBottom: `1px solid ${theme.colors.edge}`, padding: '8px', fontFamily: theme.fonts.heading, color: theme.colors.muted };

const tableCellStyle: React.CSSProperties = { borderBottom: `1px solid ${theme.colors.edge}`, padding: '8px' };

export default EquorDashboard;
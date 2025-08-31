// src/components/qora/CodeIntelligenceDashboard.tsx

import React, { useState } from 'react';
import Card from '../common/Card';
import { theme } from '../../theme';
import bffClient from '../../api/bffClient';
// It's recommended to use a markdown renderer for the annotation report
// import ReactMarkdown from 'react-markdown'; 

// NEW: Define interfaces for the API responses
interface GoalContextResponse {
    relevant_dossiers: any[];
}

interface AnnotationResponse {
    markdown: string;
}

const CodeIntelligenceDashboard = () => {
    const [goal, setGoal] = useState('');
    const [isGoalLoading, setIsGoalLoading] = useState(false);
    const [goalResults, setGoalResults] = useState<any[] | null>(null);
    const [diff, setDiff] = useState('');
    const [isAnnotateLoading, setIsAnnotateLoading] = useState(false);
    const [annotation, setAnnotation] = useState<string | null>(null);

    const handleGoalSubmit = async () => {
        if (!goal) return;
        setIsGoalLoading(true);
        setGoalResults(null);
        try {
            // FIXED: Use a type assertion to inform TypeScript of the interceptor's behavior.
            const response = await bffClient.post('/qora/goal_context', { query_text: goal, top_k: 5 }) as GoalContextResponse;
            setGoalResults(response.relevant_dossiers || []);
        } catch (error) {
            console.error(error);
            setGoalResults([]);
        } finally {
            setIsGoalLoading(false);
        }
    };

    const handleAnnotateSubmit = async () => {
        if (!diff) return;
        setIsAnnotateLoading(true);
        setAnnotation(null);
        try {
            // FIXED: Use a type assertion to inform TypeScript of the interceptor's behavior.
            const response = await bffClient.post('/qora/annotate_diff', { diff }) as AnnotationResponse;
            setAnnotation(response.markdown || 'No report generated.');
        } catch (error) {
            console.error(error);
        } finally {
            setIsAnnotateLoading(false);
        }
    };

    return (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
            <Card title="Goal-Oriented Context Builder">
                <p style={{color: theme.colors.muted, margin: '0 0 16px'}}>Describe a high-level task to find relevant code.</p>
                <input
                    type="text"
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    placeholder="e.g., improve database query performance"
                    style={{ width: '100%', padding: '10px', background: 'rgba(0,0,0,.3)', border: `1px solid ${theme.colors.edge}`, borderRadius: '6px', color: theme.colors.ink, marginBottom: '16px' }}
                />
                <button onClick={handleGoalSubmit} disabled={isGoalLoading} style={theme.styles.button}>
                    {isGoalLoading ? 'Analyzing...' : 'Get Context'}
                </button>
                <div style={{marginTop: '20px', maxHeight: '50vh', overflowY: 'auto'}}>
                    {goalResults && goalResults.map((dossier, i) => (
                        <div key={i} style={{...theme.styles.card, background: 'rgba(0,0,0,.2)', marginBottom: '12px'}}>
                            <strong>{dossier.target.fqn}</strong>
                            <p style={{fontSize: '14px', color: theme.colors.muted}}>{dossier.summary.slice(0, 200)}...</p>
                        </div>
                    ))}
                </div>
            </Card>

            <Card title="Pull Request Annotator">
                <p style={{color: theme.colors.muted, margin: '0 0 16px'}}>Paste a PR diff to get an automated analysis.</p>
                <textarea
                    value={diff}
                    onChange={(e) => setDiff(e.target.value)}
                    placeholder="Paste unified diff here..."
                    style={{ width: '100%', minHeight: '200px', fontFamily: 'monospace', background: 'rgba(0,0,0,.3)', border: `1px solid ${theme.colors.edge}`, borderRadius: '6px', color: theme.colors.ink, marginBottom: '16px', padding: '10px' }}
                />
                <button onClick={handleAnnotateSubmit} disabled={isAnnotateLoading} style={theme.styles.button}>
                    {isAnnotateLoading ? 'Analyzing...' : 'Annotate Diff'}
                </button>
                {annotation && (
                    <div style={{marginTop: '20px', whiteSpace: 'pre-wrap', fontFamily: 'monospace', maxHeight: '40vh', overflowY: 'auto', background: 'rgba(0,0,0,.2)', padding: '16px', borderRadius: '8px'}}>
                        {/* Ideally, render this with a markdown component */}
                        {annotation}
                    </div>
                )}
            </Card>
        </div>
    );
};

export default CodeIntelligenceDashboard;
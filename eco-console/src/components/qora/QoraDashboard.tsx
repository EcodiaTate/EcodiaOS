/* D:\EcodiaOS\eco-console\src\components\qora\QoraDashboard.tsx */
// ===== FILE: src/components/qora/QoraDashboard.tsx =====
import React, { useState, useEffect } from 'react';
import Card from '../common/Card';
import { theme } from '../../theme';
import bffClient from '../../api/bffClient';

interface Tool {
    uid: string;
    tool_name: string;
    agent: string;
    safety_tier: number;
    description: string;
    inputs: Record<string, any>;
}

const QoraDashboard = () => {
    const [tools, setTools] = useState<Tool[]>([]);
    const [filteredTools, setFilteredTools] = useState<Tool[]>([]);
    const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchTools = async () => {
            setIsLoading(true);
            setError(null);
            try {
                // NOTE: Assuming a BFF endpoint /governance/qora/tools exists to fetch the tool list.
            
                const response: { tools: Tool[] } = await bffClient.get('/governance/qora/tools');
                const fetchedTools = response.tools || [];
                setTools(fetchedTools);
                setFilteredTools(fetchedTools);
                if (fetchedTools.length > 0) {
               
                    setSelectedTool(fetchedTools[0]);
                }
            } catch (err: any) {
                setError(err.message || 'Failed to fetch tool catalog.');
                console.error('Failed to fetch Qora tools', err);
            } finally {
      
                setIsLoading(false);
            }
        };
        fetchTools();
    }, []);

    useEffect(() => {
        const lowerCaseSearch = searchTerm.toLowerCase();
        const filtered = tools.filter(tool => 
            tool.tool_name.toLowerCase().includes(lowerCaseSearch) ||
            tool.description.toLowerCase().includes(lowerCaseSearch)
        );
        setFilteredTools(filtered);
    }, [searchTerm, tools]);

    const renderContent = () => {
        if (isLoading) return <p>Loading tool catalog...</p>;
        if (error) return <p style={{ color: '#ef4444' }}>Error: {error}</p>;
        return (
            <div style={{ display: 'flex', gap: '24px' }}>
                <div style={{width: '40%'}}>
                    <h4 style={{ fontFamily: theme.fonts.heading, margin: '0 0 16px' }}>Search Results</h4>
                    {filteredTools.length > 0 ? (
 
                        <ul style={{listStyle: 'none', margin: 0, padding: 0, maxHeight: '60vh', overflowY: 'auto'}}>
                            {filteredTools.map(tool => (
                                <li key={tool.uid} onClick={() => setSelectedTool(tool)} 
                                style={{
                                    padding: '10px', 
                                    background: selectedTool?.uid === tool.uid ? 'rgba(244, 211, 94, .15)' : 'rgba(255,255,255,.05)', 
               
                                    borderRadius: '6px', 
                                    cursor: 'pointer',
                                    border: `1px solid ${selectedTool?.uid 
 === tool.uid ? theme.colors.g3 : 'transparent'}`
                                }}>
                                    {tool.tool_name}
                           
                                </li>
                            ))}
                        </ul>
                    ) : <p style={{color: theme.colors.muted}}>No tools found.</p>}
                </div>
 
                <div style={{width: '60%', borderLeft: `1px solid ${theme.colors.edge}`, paddingLeft: '24px'}}>
                    <h4 style={{ fontFamily: theme.fonts.heading, margin: '0 0 16px' }}>Schema Viewer</h4>
                    {selectedTool ?
 (
                        <>
                            <strong>{selectedTool.tool_name}</strong>
                            <p style={{color: theme.colors.muted, fontSize: '14px'}}>{selectedTool.description}</p>
                
                            <pre style={{
                              background: 'rgba(0,0,0,.2)',
                              padding: '16px',
                         
                              borderRadius: '8px',
                              fontSize: '12px',
                              whiteSpace: 'pre-wrap',
                              border: `1px 
 solid ${theme.colors.edge}`,
                            }}>
                              {JSON.stringify(selectedTool.inputs, null, 2)}
                            </pre>
           
                        </>
                    ) : <p style={{color: theme.colors.muted}}>Select a tool to view its schema.</p>}
                </div>
            </div>
        );
    };

    return (
      <Card title="Qora Tool Catalog">
        <input type="text" placeholder="Search for tools (e.g., 'code search')..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} style={{
            width: '100%',
            padding: '12px',
            marginBottom: '20px',
            background: 'rgba(0,0,0,.3)',
            border: `1px solid ${theme.colors.edge}`,
  
            borderRadius: '6px',
            color: theme.colors.ink,
          }}/>
        {renderContent()}
      </Card>
    );
};
export default QoraDashboard;
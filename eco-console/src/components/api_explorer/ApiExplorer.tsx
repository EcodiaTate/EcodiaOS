// ===== FILE: src/components/api_explorer/ApiExplorer.tsx =====
import { useState, useEffect } from 'react';
import type { CSSProperties } from 'react';
import Card from '../common/Card';
import { theme } from '../../theme';
import bffClient from '../../api/bffClient';

// --- Type definitions for the OpenAPI Spec data ---
interface EndpointData {
  summary?: string;
  requestBody?: {
    content?: {
      'application/json'?: {
        schema?: any;
      };
    };
  };
}

interface EndpointInfo {
  path: string;
  method: string;
  summary: string;
  bodySchema?: any;
}

const ApiExplorer = () => {
  const [endpoints, setEndpoints] = useState<EndpointInfo[]>([]);
  const [selectedEndpoint, setSelectedEndpoint] = useState<EndpointInfo | null>(null);
  const [body, setBody] = useState('');
  const [response, setResponse] = useState('// Select an endpoint to begin');
  const [isLoading, setIsLoading] = useState(true);
  const [isExecuting, setIsExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchApiSpec = async () => {
      try {
        setIsLoading(true);
        const res = await fetch('http://127.0.0.1:8000/openapi.json');
        if (!res.ok) throw new Error(`Failed to fetch OpenAPI spec: ${res.statusText}`);
        const spec = await res.json();

        const parsedEndpoints: EndpointInfo[] = [];
        for (const path in spec.paths) {
          for (const method in spec.paths[path]) {
            const data: EndpointData = spec.paths[path][method];
            parsedEndpoints.push({
              path,
              method: method.toUpperCase(),
              summary: data.summary || 'No summary available.',
              bodySchema: data.requestBody?.content?.['application/json']?.schema,
            });
          }
        }
        setEndpoints(parsedEndpoints);
        setError(null);
      } catch (err: any) {
        setError(err.message || 'Could not connect to the backend API.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchApiSpec();
  }, []);

  // --- Helper to generate an example from a schema ---
  const generateExample = (schema: any): string => {
    if (!schema || !schema.properties) return '{}';
    const example: Record<string, any> = {};
    for (const key in schema.properties) {
      const prop = schema.properties[key];
      example[key] =
        prop.example ??
        prop.default ??
        (prop.type === 'string'
          ? 'string'
          : prop.type === 'integer'
          ? 0
          : prop.type === 'boolean'
          ? false
          : {});
    }
    return JSON.stringify(example, null, 2);
  };

  const handleSelect = (endpoint: EndpointInfo) => {
    setSelectedEndpoint(endpoint);
    setResponse(`// Click "Execute" to call ${endpoint.path}`);
    if (endpoint.bodySchema) {
      setBody(generateExample(endpoint.bodySchema));
    } else {
      setBody('');
    }
  };

  // --- Execute API Call ---
  const handleExecute = async () => {
    if (!selectedEndpoint) return;

    setIsExecuting(true);
    setResponse('// Executing...');
    try {
      let requestBody: Record<string, any> = {};
      if (selectedEndpoint.bodySchema && body) {
        try {
          requestBody = JSON.parse(body);
        } catch {
          throw new Error('Invalid JSON in request body.');
        }
      }

      // Using a generic proxy endpoint on the BFF
      const result = await bffClient.post('/proxy', {
        method: selectedEndpoint.method,
        path: selectedEndpoint.path,
        data: requestBody,
      });
      setResponse(JSON.stringify(result, null, 2));
    } catch (err: any) {
      setResponse(`// API Call Failed:\n${err.message || JSON.stringify(err, null, 2)}`);
    } finally {
      setIsExecuting(false);
    }
  };

  if (isLoading) {
    return (
      <Card title="API Explorer">
        <p>Loading API specification...</p>
      </Card>
    );
  }

  if (error) {
    return (
      <Card title="API Explorer">
        <p style={{ color: '#ef4444' }}>Error: {error}</p>
      </Card>
    );
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '350px 1fr',
        gap: '24px',
        height: 'calc(100vh - 120px)',
      }}
    >
      {/* Endpoint List */}
      <Card title="Endpoints" style={{ overflowY: 'auto' }}>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {endpoints.map((ep) => {
            const isActive =
              selectedEndpoint?.path === ep.path && selectedEndpoint?.method === ep.method;
            return (
              <li
                key={`${ep.method}-${ep.path}`}
                onClick={() => handleSelect(ep)}
                style={{
                  padding: '10px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  marginBottom: '8px',
                  border: `1px solid ${isActive ? theme.colors.g3 : 'transparent'}`,
                  background: isActive ? 'rgba(244, 211, 94, .15)' : 'rgba(255,255,255,.05)',
                }}
              >
                <span
                  style={{
                    fontFamily: theme.fonts.heading,
                    color: ep.method === 'POST' ? theme.colors.g2 : '#60a5fa',
                    marginRight: '8px',
                    width: '50px',
                    display: 'inline-block',
                  }}
                >
                  {ep.method}
                </span>
                <span style={{ fontFamily: 'monospace', fontSize: '14px' }}>{ep.path}</span>
              </li>
            );
          })}
        </ul>
      </Card>

      {/* Interaction Panel */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {selectedEndpoint ? (
          <>
            <Card title="Request">
              <h4 style={{ fontFamily: theme.fonts.heading, margin: 0 }}>
                {selectedEndpoint.method} {selectedEndpoint.path}
              </h4>
              <p style={{ margin: '4px 0 16px', color: theme.colors.muted }}>
                {selectedEndpoint.summary}
              </p>

              {selectedEndpoint.bodySchema && (
                <>
                  <label
                    style={{ fontFamily: theme.fonts.heading, display: 'block', marginBottom: 8 }}
                  >
                    Request Body
                  </label>
                  <textarea
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    style={textAreaStyle}
                  />
                </>
              )}

              <button
                onClick={handleExecute}
                style={{ ...theme.styles.button, marginTop: '16px' }}
                disabled={isExecuting}
              >
                {isExecuting ? 'Executing...' : 'Execute'}
              </button>
            </Card>

            <Card title="Response" style={{ flex: 1 }}>
              <pre style={preStyle}>{response}</pre>
            </Card>
          </>
        ) : (
          <Card title="API Explorer">
            <p>Select an endpoint from the list on the left to get started.</p>
          </Card>
        )}
      </div>
    </div>
  );
};

// --- Styles ---
const textAreaStyle: CSSProperties = {
  width: '100%',
  minHeight: '200px',
  fontFamily: 'monospace',
  background: 'rgba(0,0,0,.3)',
  border: `1px solid ${theme.colors.edge}`,
  borderRadius: '6px',
  color: theme.colors.ink,
  padding: '10px',
  fontSize: '14px',
};

const preStyle: CSSProperties = {
  height: '100%',
  margin: 0,
  background: 'rgba(0,0,0,.2)',
  padding: '16px',
  borderRadius: '8px',
  fontSize: '14px',
  whiteSpace: 'pre-wrap',
  fontFamily: 'monospace',
  overflowY: 'auto',
};

export default ApiExplorer;

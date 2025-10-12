import { useState, useCallback, type CSSProperties } from 'react';
import Card from '../common/Card';
import { theme } from '../../theme';
import bffClient from '../../api/bffClient';
import toast from 'react-hot-toast';
import { usePolling } from '../../hooks/usePolling';
import { LoadingSpinner } from '../ui/LoadingSpinner';
import { ErrorDisplay } from '../ui/ErrorDisplay';
import { DataTable } from '../ui/DataTable';

interface Driver {
  driver_name: string;
  status: 'testing' | 'shadow' | 'live' | 'deprecated';
  capability: string;
}

const AxonDashboard = () => {
  const { data: drivers, isLoading, error, refetch } = usePolling<Driver[]>('/axon/drivers');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newSpecUrl, setNewSpecUrl] = useState('');
  const [isSynthesizing, setIsSynthesizing] = useState(false);

  const handleSynthesize = useCallback(async () => {
    if (!newName || !newSpecUrl) {
      toast.error('Both driver name and spec URL are required.');
      return;
    }
    setIsSynthesizing(true);
    const toastId = toast.loading(`Synthesizing driver '${newName}'...`);
    try {
      await bffClient.post('/axon/synthesize', { driver_name: newName, api_spec_url: newSpecUrl });
      toast.success(`Synthesis for '${newName}' started successfully!`, { id: toastId });
      setIsModalOpen(false);
      setNewName('');
      setNewSpecUrl('');
      setTimeout(() => refetch(), 1500);
    } catch (err: any) {
      toast.error(`Synthesis failed: ${err.message || err}`, { id: toastId });
    } finally {
      setIsSynthesizing(false);
    }
  }, [newName, newSpecUrl, refetch]);

  const statusColor = (status: Driver['status']) => {
    if (status === 'live') return theme.colors.g2;
    if (status === 'shadow') return '#60a5fa';
    if (status === 'testing') return theme.colors.g3;
    return theme.colors.muted;
  };

  const renderContent = () => {
    if (isLoading && !drivers) return <LoadingSpinner text="Loading drivers..." />;
    if (error) return <ErrorDisplay error={error} context="Axon Drivers" />;
    if (!drivers || drivers.length === 0) return <p style={{ color: theme.colors.muted }}>No drivers found.</p>;

    const headers = [
      { key: 'driver_name', label: 'Driver Name' },
      { key: 'capability', label: 'Capability' },
      { key: 'status', label: 'Status' },
    ];

    const rows = drivers.map((driver) => ({
      driver_name: <span style={{ fontFamily: 'monospace' }}>{driver.driver_name}</span>,
      capability: <span style={{ fontFamily: 'monospace', color: theme.colors.muted }}>{driver.capability}</span>,
      status: (
        <span style={{ color: statusColor(driver.status), fontFamily: theme.fonts.heading }}>
          {driver.status.toUpperCase()}
        </span>
      ),
    }));

    return <DataTable headers={headers} rows={rows} />;
  };

  return (
    <>
      <Card title="Axon Driver & Capability Manager (Live)">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <p style={{ margin: 0, color: theme.colors.muted }}>
            Monitor and manage all autonomous capabilities (drivers) in the system. Refreshes automatically.
          </p>
          <button style={theme.styles.button} onClick={() => setIsModalOpen(true)}>
            Synthesize New Driver
          </button>
        </div>
        {renderContent()}
      </Card>

      {isModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <Card title="Synthesize New Driver" style={{ minWidth: 500 }}>
            <p style={{ color: theme.colors.muted, margin: '0 0 16px' }}>
              Provide an OpenAPI spec URL to automatically generate a new driver.
            </p>
            <input
              type="text"
              placeholder="Driver Name (e.g., weather_api_driver)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              style={inputStyle}
            />
            <input
              type="text"
              placeholder="OpenAPI/Swagger Spec URL"
              value={newSpecUrl}
              onChange={(e) => setNewSpecUrl(e.target.value)}
              style={inputStyle}
            />
            <div style={{ marginTop: 20, display: 'flex', gap: 12 }}>
              <button onClick={handleSynthesize} disabled={isSynthesizing} style={theme.styles.button}>
                {isSynthesizing ? 'Synthesizing...' : 'Start Synthesis'}
              </button>
              <button
                onClick={() => setIsModalOpen(false)}
                style={{ ...theme.styles.button, background: 'transparent', border: `1px solid ${theme.colors.edge}` }}
              >
                Cancel
              </button>
            </div>
          </Card>
        </div>
      )}
    </>
  );
};

const inputStyle: CSSProperties = {
  width: '100%',
  padding: 10,
  background: 'rgba(0,0,0,.3)',
  border: `1px solid ${theme.colors.edge}`,
  borderRadius: 6,
  color: theme.colors.ink,
  marginBottom: 16,
};

export default AxonDashboard;

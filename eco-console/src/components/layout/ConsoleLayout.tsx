// src/components/layout/ConsoleLayout.tsx
import type { ReactNode, CSSProperties } from 'react';
import StatusHeader from './Header';

type View = 'atune' | 'synapse' | 'unity' | 'qora';

type Props = {
  view: View;
  onNavigate: (v: View) => void;
  children: ReactNode;
};

export default function ConsoleLayout({ view, onNavigate, children }: Props) {
  const NavBtn = ({ id, label }: { id: View; label: string }) => (
    <button
      onClick={() => onNavigate(id)}
      style={{
        width: '100%',
        textAlign: 'left',
        padding: '10px 12px',
        borderRadius: 8,
        background: view === id ? '#eef2ff' : 'transparent',
        border: '1px solid #e5e7eb',
        marginBottom: 6,
        fontWeight: view === id ? 600 : 500,
      }}
    >
      {label}
    </button>
  );

  const layout: CSSProperties = { display: 'grid', gridTemplateColumns: '240px 1fr', height: '100vh' };

  return (
    <div style={layout}>
      <aside style={{ borderRight: '1px solid #e5e7eb', padding: 12, overflowY: 'auto' }}>
        <div style={{ fontWeight: 700, marginBottom: 10 }}>Navigation</div>
        <NavBtn id="atune" label="Atune (Salience)" />
        <NavBtn id="synapse" label="Synapse (Governance)" />
        <NavBtn id="unity" label="Unity (Deliberation)" />
        <NavBtn id="qora" label="Qora (Graph)" />
      </aside>

      <main style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <StatusHeader />
        <div style={{ padding: 16, overflow: 'auto' }}>{children}</div>
      </main>
    </div>
  );
}

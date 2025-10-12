// src/App.tsx
import { type CSSProperties } from 'react';
import { theme } from './theme';
import Sidebar from './components/layout/Sidebar';
import Header from './components/layout/Header';
import { AppProvider, useAppContext } from './context/AppContext';
import { Toaster } from 'react-hot-toast';

import SynapseDashboard from './components/synapse/SynapseDashboard';
import UnityDashboard from './components/unity/UnityDashboard';
import AtuneDashboard from './components/atune/AtuneDashboard';
import EvoDashboard from './components/evo/EvoDashboard';
import QoraDashboard from './components/qora/QoraDashboard';
import EquorDashboard from './components/equor/EquorDashboard';
import ApiExplorer from './components/api_explorer/ApiExplorer';
import CodeIntelligenceDashboard from './components/qora/CodeIntelligenceDashboard';
import AxonDashboard from './components/axon/AxonDashboard';
import DecisionJourneyHeader from './components/common/DecisionJourneyHeader';

export type Page =
  | 'Synapse'
  | 'Unity'
  | 'Atune'
  | 'Evo'
  | 'Qora'
  | 'Equor'
  | 'API Explorer'
  | 'Code Intelligence'
  | 'Axon Drivers';

const PageRenderer = () => {
  const { activePage } = useAppContext();

  switch (activePage) {
    case 'Synapse': return <SynapseDashboard />;
    case 'Unity': return <UnityDashboard />;
    case 'Atune': return <AtuneDashboard />;
    case 'Evo': return <EvoDashboard />;
    case 'Qora': return <QoraDashboard />;
    case 'Equor': return <EquorDashboard />;
    case 'API Explorer': return <ApiExplorer />;
    case 'Code Intelligence': return <CodeIntelligenceDashboard />;
    case 'Axon Drivers': return <AxonDashboard />;
    default: return <SynapseDashboard />;
  }
};

const gridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '240px 1fr',
  gridTemplateRows: 'auto auto 1fr',
  height: '100vh',
  fontFamily: theme.fonts.body,
  color: theme.colors.ink,
  background: `
    radial-gradient(80% 120% at 0% 0%, rgba(127,208,105,.10), transparent 50%),
    radial-gradient(110% 160% at 100% 0%, rgba(244,211,94,.10), transparent 55%),
    linear-gradient(${theme.colors.background}, ${theme.colors.background})
  `,
};

const App = () => {
  return (
    <AppProvider>
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: theme.colors.card,
            color: theme.colors.ink,
            border: `1px solid ${theme.colors.edge}`,
          },
        }}
      />
      <div style={gridStyle}>
        <div style={{ gridColumn: '1 / 2', gridRow: '1 / 4' }}>
          <Sidebar />
        </div>
        <div style={{ gridColumn: '2 / 3', gridRow: '1 / 2', position: 'sticky', top: 0, zIndex: 10 }}>
          <Header />
        </div>
        <div style={{ gridColumn: '2 / 3', gridRow: '2 / 3', zIndex: 9 }}>
          <DecisionJourneyHeader />
        </div>
        <main style={{ gridColumn: '2 / 3', gridRow: '3 / 4', overflowY: 'auto', padding: '24px' }}>
          <PageRenderer />
        </main>
      </div>
    </AppProvider>
  );
};

export default App;

// src/context/AppContext.tsx

import {
  createContext,
  useState,
  useContext,
  type ReactNode,
} from 'react';

// Import the Page union as a TYPE ONLY to avoid runtime circular deps
import type { Page } from '../App';

interface AppContextType {
  activePage: Page;
  setActivePage: (page: Page) => void;
  activeDecisionId: string | null;
  setActiveDecisionId: (id: string | null) => void;
  navigateToTrace: (id: string) => void;
  clearDecisionId: () => void;
}

const AppContext = createContext<AppContextType | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activePage, setActivePage] = useState<Page>('Synapse');
  const [activeDecisionId, setActiveDecisionId] = useState<string | null>(null);

  const navigateToTrace = (id: string) => {
    setActiveDecisionId(id);
    setActivePage('Atune');
  };

  const clearDecisionId = () => {
    setActiveDecisionId(null);
  };

  const value: AppContextType = {
    activePage,
    setActivePage,
    activeDecisionId,
    setActiveDecisionId,
    navigateToTrace,
    clearDecisionId,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext(): AppContextType {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used within an AppProvider');
  return ctx;
}

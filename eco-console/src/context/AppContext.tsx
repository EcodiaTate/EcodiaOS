// src/context/AppContext.tsx

import React, { createContext, useState, useContext, ReactNode } from 'react';
import { Page } from '../App';

interface AppContextType {
  activePage: Page;
  setActivePage: (page: Page) => void;
  activeDecisionId: string | null;
  setActiveDecisionId: (id: string | null) => void;
  navigateToTrace: (id: string) => void;
  // NEW: Add a function to clear the decision context
  clearDecisionId: () => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider = ({ children }: { children: ReactNode }) => {
  const [activePage, setActivePage] = useState<Page>('Synapse');
  const [activeDecisionId, setActiveDecisionId] = useState<string | null>(null);

  const navigateToTrace = (id: string) => {
    setActiveDecisionId(id);
    setActivePage('Atune');
  };

  // NEW: Implementation for the clear function
  const clearDecisionId = () => {
    setActiveDecisionId(null);
  };

  const value = { activePage, setActivePage, activeDecisionId, setActiveDecisionId, navigateToTrace, clearDecisionId };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

export const useAppContext = () => {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useAppContext must be used within an AppProvider');
  }
  return context;
};
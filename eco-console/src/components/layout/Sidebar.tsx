// src/components/layout/Sidebar.tsx

import React from 'react';
import { theme } from '../../theme';
import { Page } from '../../App';
import { useAppContext } from '../../context/AppContext';

const Sidebar = () => {
  const { activePage, setActivePage } = useAppContext();
  // NEW: Add the new pages to the navItems array
  const navItems: Page[] = ['Synapse', 'Unity', 'Atune', 'Evo', 'Qora', 'Equor', 'API Explorer', 'Code Intelligence', 'Axon Drivers'];

  return (
    <nav style={{
      height: '100%',
      backgroundColor: theme.colors.card,
      borderRight: `1px solid ${theme.colors.edge}`,
      padding: '20px',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <h1 style={{ fontFamily: theme.fonts.heading, color: theme.colors.g3, margin: '0 0 40px 0', fontSize: '24px' }}>
        ECO CONSOLE
      </h1>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {navItems.map(page => (
          <li key={page} style={{ marginBottom: '10px' }}>
            <button
              onClick={() => setActivePage(page)}
              style={{
                width: '100%',
                padding: '12px 16px',
                textAlign: 'left',
                fontFamily: theme.fonts.heading,
                fontSize: '16px',
                cursor: 'pointer',
                border: '1px solid transparent',
                borderRadius: '8px',
                transition: 'all 0.2s ease',
                ...(activePage === page
                  ? {
                      backgroundColor: 'rgba(244, 211, 94, .15)',
                      color: theme.colors.g3,
                      borderColor: theme.colors.g3,
                    }
                  : {
                      backgroundColor: 'transparent',
                      color: theme.colors.muted,
                      border: '1px solid transparent',
                  }),
              }}
              onMouseOver={e => (e.currentTarget.style.borderColor = activePage !== page ? theme.colors.edge : theme.colors.g3)}
              onMouseOut={e => (e.currentTarget.style.borderColor = activePage !== page ? 'transparent' : theme.colors.g3)}
            >
              {page}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
};

export default Sidebar;
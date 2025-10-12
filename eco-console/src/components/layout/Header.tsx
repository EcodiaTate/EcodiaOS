// src/components/layout/Header.tsx
import { useState, useEffect, useCallback, type CSSProperties } from 'react';
import { theme } from '../../theme';
import StatusPill from '../common/StatusPill';
import { useSystemHealth } from '../../hooks/useSystemHealth';
import bffClient from '../../api/bffClient';
import { useAppContext } from '../../context/AppContext';

// Debounce hook
function useDebounce(value: string, delay: number) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(h);
  }, [value, delay]);
  return debouncedValue;
}

const DISABLE_SEARCH = true; // flip to false after things load

interface SearchResult {
  id: string;
  type: string;
  label: string;
}

const Header = () => {
  const { health, allOk } = useSystemHealth(5000);
  const { navigateToTrace } = useAppContext();

  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const debouncedSearchTerm = useDebounce(searchTerm, 500);

  const handleSearch = useCallback(async (term: string) => {
    if (term.length < 3) {
      setSearchResults([]);
      return;
    }
    setIsSearching(true);
    try {
      const results = (await bffClient.get(
        `/search?q=${encodeURIComponent(term)}`
      )) as SearchResult[];
      setSearchResults(results || []);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Search failed:', err);
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  }, []);

  useEffect(() => {
    if (!DISABLE_SEARCH) {
      handleSearch(debouncedSearchTerm);
    }
  }, [debouncedSearchTerm, handleSearch]);

  const handleSelect = (item: SearchResult) => {
    if (item.type === 'Conflict') navigateToTrace(item.id);
    setSearchTerm('');
    setSearchResults([]);
  };

  const headerStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 24px',
    borderBottom: `1px solid ${theme.colors.edge}`,
    background: 'rgba(10, 15, 12, .8)',
    backdropFilter: 'blur(10px)',
  };

  return (
    <div style={headerStyle}>
      {/* Left side: Search (or disabled label) */}
      {DISABLE_SEARCH ? (
        <div style={{ opacity: 0.6 }}>Search disabled</div>
      ) : (
        <div style={{ position: 'relative', width: 400 }}>
          <input
            type="text"
            placeholder="Universal Search (e.g., conflict ID, code symbol)..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              padding: '8px 12px',
              background: 'rgba(0,0,0,.3)',
              border: `1px solid ${theme.colors.edge}`,
              borderRadius: '6px',
              color: theme.colors.ink,
            }}
          />
          {(isSearching || searchResults.length > 0) && (
            <div
              style={{
                position: 'absolute',
                top: '110%',
                left: 0,
                width: '100%',
                background: theme.colors.card,
                border: `1px solid ${theme.colors.edge}`,
                borderRadius: '8px',
                zIndex: 100,
                maxHeight: '50vh',
                overflowY: 'auto',
              }}
            >
              {isSearching ? (
                <div style={{ padding: 12, color: theme.colors.muted }}>Searching...</div>
              ) : (
                searchResults.map((item) => (
                  <div
                    key={item.id}
                    onClick={() => handleSelect(item)}
                    style={{
                      padding: 12,
                      borderBottom: `1px solid ${theme.colors.edge}`,
                      cursor: 'pointer',
                    }}
                  >
                    <strong style={{ color: theme.colors.g3 }}>{item.type}:</strong> {item.label}
                    <div
                      style={{
                        fontSize: 12,
                        color: theme.colors.muted,
                        fontFamily: 'monospace',
                      }}
                    >
                      {item.id}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* Right side: Health Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <div
          style={{
            fontFamily: theme.fonts.heading,
            fontSize: 14,
            color: allOk ? theme.colors.g2 : '#ef4444',
            letterSpacing: '1px',
          }}
        >
          {allOk ? 'ALL SYSTEMS NOMINAL' : 'ATTENTION REQUIRED'}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {Object.entries(health).map(([name, status]) => (
            <StatusPill
              key={name}
              label={name.toUpperCase()}
              ok={status.ok}
              title={status.via ?? undefined}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export default Header;

// src/components/ui/ErrorDisplay.tsx
import React from 'react';
import { theme } from '../../theme';

interface ErrorDisplayProps {
  error: string;
  context?: string;
}

export const ErrorDisplay = ({ error, context }: ErrorDisplayProps) => (
  <div style={{ padding: '20px', background: 'rgba(239, 68, 68, 0.1)', border: `1px solid #ef4444`, borderRadius: '8px' }}>
    <p style={{ margin: 0, fontFamily: theme.fonts.heading, color: '#f87171' }}>
      Error {context ? `in ${context}` : ''}
    </p>
    <p style={{ margin: '4px 0 0', color: theme.colors.muted, fontFamily: 'monospace' }}>
      {error}
    </p>
  </div>
);
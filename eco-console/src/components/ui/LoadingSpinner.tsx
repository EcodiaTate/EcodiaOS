// src/components/ui/LoadingSpinner.tsx
import React from 'react';
import { theme } from '../../theme';

export const LoadingSpinner = ({ text = 'Loading...' }: { text?: string }) => (
  <div style={{ padding: '20px', color: theme.colors.muted, textAlign: 'center' }}>
    {/* You can replace this with a more complex CSS spinner */}
    <p>{text}</p>
  </div>
);
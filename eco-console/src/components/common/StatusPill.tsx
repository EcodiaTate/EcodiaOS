// ===== FILE: src/components/common/StatusPill.tsx =====
import React from 'react';
import { theme } from '../../theme';

interface StatusPillProps {
  label: string;
  ok: boolean;
  title?: string;
}

const StatusPill = ({ label, ok, title }: StatusPillProps) => {
  const color = ok ? theme.colors.g2 : '#ef4444';
  return (
    <span title={title} style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: '4px 10px',
      borderRadius: 999,
      border: `1px solid ${theme.colors.edge}`,
      background: theme.colors.card,
      fontSize: 12,
      fontFamily: theme.fonts.heading,
      color: theme.colors.muted,
    }}>
      <span style={{ width: 8, height: 8, borderRadius: 10, background: color }} />
      <span>{label}</span>
    </span>
  );
};

export default StatusPill;
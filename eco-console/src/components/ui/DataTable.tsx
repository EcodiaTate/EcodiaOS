// src/components/ui/DataTable.tsx
import React from 'react';
import { theme } from '../../theme';

interface DataTableProps {
  headers: { key: string; label: string; style?: React.CSSProperties }[];
  rows: Record<string, any>[];
}

const tableHeaderStyle: React.CSSProperties = {
  borderBottom: `1px solid ${theme.colors.edge}`,
  padding: '12px',
  textAlign: 'left',
  fontFamily: theme.fonts.heading,
  color: theme.colors.muted,
};

const tableCellStyle: React.CSSProperties = {
  borderBottom: `1px solid ${theme.colors.edge}`,
  padding: '12px',
  textAlign: 'left',
};

export const DataTable = ({ headers, rows }: DataTableProps) => {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
        <thead>
          <tr>
            {headers.map(h => (
              <th key={h.key} style={{ ...tableHeaderStyle, ...h.style }}>
                {h.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {headers.map(h => (
                <td key={`${index}-${h.key}`} style={{ ...tableCellStyle, ...h.style }}>
                  {row[h.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
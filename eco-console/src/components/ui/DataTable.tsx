import type { CSSProperties } from 'react';
import { theme } from '../../theme';

interface HeaderDef {
  key: string;
  label: string;
  style?: CSSProperties;
}

interface DataTableProps {
  headers: HeaderDef[];
  rows: Record<string, any>[];
}

const tableHeaderStyle: CSSProperties = {
  borderBottom: `1px solid ${theme.colors.edge}`,
  padding: '12px',
  textAlign: 'left',
  fontFamily: theme.fonts.heading,
  color: theme.colors.muted,
};

const tableCellStyle: CSSProperties = {
  borderBottom: `1px solid ${theme.colors.edge}`,
  padding: '12px',
  textAlign: 'left',
};

export const DataTable = ({ headers, rows }: DataTableProps) => {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h.key} style={{ ...tableHeaderStyle, ...h.style }}>
                {h.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {headers.map((h) => (
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

// ===== FILE: src/components/common/Card.tsx =====

import type { ReactNode, CSSProperties } from 'react';
import { theme } from '../../theme';

interface CardProps {
  title: string;
  children: ReactNode;
  style?: CSSProperties;
}

const Card = ({ title, children, style }: CardProps) => {
  return (
    <div style={{ ...theme.styles.card, ...style }}>
      <h3
        style={{
          fontFamily: theme.fonts.heading,
          color: theme.colors.g3,
          margin: '0 0 16px 0',
          fontSize: '18px',
          borderBottom: `1px solid ${theme.colors.edge}`,
          paddingBottom: '8px',
        }}
      >
        {title}
      </h3>
      {children}
    </div>
  );
};

export default Card;

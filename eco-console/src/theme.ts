export const theme = {
  colors: {
    black: '#000',
    white: '#fff',
    g1: '#396041', // Dark Green
    g2: '#7FD069', // Light Green
    g3: '#F4D35E', // Yellow
    ink: '#e9f4ec',
    muted: 'rgba(255, 255, 255, .78)',
    edge: 'rgba(255, 255, 255, .10)',
    card: 'rgba(14, 20, 16, .92)',
    background: '#0a0f0c',
  },
  fonts: {
    heading: '"Fjalla One", "Comfortaa", sans-serif',
    body: '"Comfortaa", sans-serif',
  },
  styles: {
    card: {
      border: `1px solid rgba(255, 255, 255, .10)`,
      borderRadius: '16px',
      backgroundColor: 'rgba(14, 20, 16, .92)',
      color: '#e9f4ec',
      padding: '20px',
      boxShadow: 'inset 0 0 0 1px rgba(255, 255, 255, .03)',
    },
    button: {
      fontFamily: '"Fjalla One", "Comfortaa", sans-serif',
      letterSpacing: '.2px',
      display: 'inline-flex',
      alignItems: 'center',
      gap: '.6rem',
      padding: '.75rem 1.2rem',
      borderRadius: '999px',
      color: '#fff',
      textDecoration: 'none',
      background: 'linear-gradient(135deg, #396041 0%, #7FD069 60%, #F4D35E 100%)',
      border: '1px solid rgba(0,0,0,.4)',
      boxShadow: '0 10px 28px rgba(0,0,0,.45), inset 0 0 0 1px rgba(255,255,255,.06)',
      cursor: 'pointer',
    },
  },
};

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        primary: ['var(--font-primary)', 'sans-serif'],
        secondary: ['var(--font-secondary)', 'sans-serif'],
      },
      colors: {
        brand: '#396041',
        light: '#f4d35e',
      },
      backdropBlur: {
        sm: '4px',
        md: '8px',
      },
      opacity: {
        15: '0.15',
        85: '0.85',
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),('tailwind-scrollbar')({ nocompatible: true }),
  ],
  variants: {
    scrollbar: ['rounded'],
  },
}

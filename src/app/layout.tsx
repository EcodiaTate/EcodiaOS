import './globals.css'
import { Inter, Fjalla_One } from 'next/font/google'
import React from 'react'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-secondary',
  display: 'swap',
})

const fjalla = Fjalla_One({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-display',
  display: 'swap',
})

export const metadata = { title: 'EcodiaOS', description: 'Speak to the soul of Ecodia' }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const suppress =
    process.env.NODE_ENV !== 'production' ? { suppressHydrationWarning: true } : {}

  return (
    <html
      lang="en"
      className={`${inter.variable} ${fjalla.variable} antialiased h-dvh overscroll-none`}
      {...suppress}
    >
      <body
        className="h-dvh overflow-hidden bg-[var(--background)] text-[var(--foreground)] font-[var(--font-body)] touch-manipulation"
        {...suppress}
      >
        {children}
      </body>
    </html>
  )
}

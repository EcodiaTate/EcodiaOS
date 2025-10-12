// apps/eco-console/src/components/synapse/DownloadCSV.tsx
'use client'
import { Outcome } from '@/types/synapse'

export function DownloadCSV({ data }: { data: Outcome[] }) {
  const handleDownload = () => {
    const headers = Object.keys(data[0])
    const csvRows = [
      headers.join(','),
      ...data.map(row =>
        headers.map(h => JSON.stringify((row as any)[h] ?? '')).join(',')
      ),
    ]
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)

    const link = document.createElement('a')
    link.href = url
    link.download = 'synapse_outcomes.csv'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <button onClick={handleDownload} className="bg-blue-600 text-white px-4 py-1 rounded">
      Export CSV
    </button>
  )
}

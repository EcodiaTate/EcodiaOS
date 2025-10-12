// src/components/synapse/OutcomeHeatmap.tsx
'use client'
import React, { useMemo } from 'react'
import type { Outcome } from '../../types/synapse'
import type { GroupKey } from './types'

type Props = { data: Outcome[]; groupBy: GroupKey }

export function OutcomeHeatmap({ data, groupBy }: Props) {
  const rows = useMemo(() => {
    const grouped: Record<string, { total: number; count: number }> = {}

    for (const curr of data) {
      const key: string = (curr[groupBy] ?? 'unknown') as string
      if (!grouped[key]) grouped[key] = { total: 0, count: 0 }
      const val = Number(curr.utility_score) || 0
      grouped[key].total += val
      grouped[key].count += 1
    }

    return Object.entries(grouped)
      .map(([key, { total, count }]) => ({ key, avg: count ? total / count : 0, count }))
      .sort((a, b) => b.avg - a.avg)
  }, [data, groupBy])

  return (
    <div>
      <h2 className="text-lg font-semibold mb-2">Utility Heatmap by {groupBy}</h2>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
        {rows.map((entry) => {
          // simple intensity (0..1) from avg (assumes typical 0..1 utilities; clamp for safety)
          const intensity = Math.max(0, Math.min(1, entry.avg))
          const bg = `rgba(79, 70, 229, ${0.12 + intensity * 0.35})` // purple-ish
          return (
            <div key={entry.key} style={{ padding: 12, borderRadius: 8, background: bg }}>
              <div style={{ fontWeight: 600, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis' }}>{entry.key}</div>
              <div style={{ fontVariantNumeric: 'tabular-nums' }}>avg: {entry.avg.toFixed(3)}</div>
              <div style={{ color: '#888' }}>n={entry.count}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// src/components/synapse/OutcomeLeaderboard.tsx
'use client'
import React, { useMemo } from 'react'
import type { Outcome } from '../../types/synapse'
import type { GroupKey } from './types'

type Props = { data: Outcome[]; groupBy: GroupKey; topN?: number }

export function OutcomeLeaderboard({ data, groupBy, topN = 10 }: Props) {
  const ranked = useMemo(() => {
    const buf: Record<string, number[]> = {}
    for (const o of data) {
      const key: string = (o[groupBy] ?? 'unknown') as string
      if (!buf[key]) buf[key] = []
      buf[key].push(Number(o.utility_score) || 0)
    }
    return Object.entries(buf)
      .map(([k, scores]) => ({
        key: k,
        avg: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0,
        n: scores.length,
      }))
      .sort((a, b) => b.avg - a.avg)
      .slice(0, topN)
  }, [data, groupBy, topN])

  return (
    <div>
      <h2 className="text-lg font-semibold mb-2">Top {topN} {groupBy}s by Average Utility</h2>
      <ol className="list-decimal pl-5">
        {ranked.map((r, i) => (
          <li key={i} style={{ display: 'flex', gap: 8 }}>
            <strong style={{ minWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.key}</strong>
            <span style={{ fontVariantNumeric: 'tabular-nums' }}>{r.avg.toFixed(3)}</span>
            <span style={{ color: '#888' }}>n={r.n}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

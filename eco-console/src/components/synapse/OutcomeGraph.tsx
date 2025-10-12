// src/components/synapse/OutcomeGraph.tsx
'use client'
import React, { useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from 'recharts'
import type { Outcome } from '../../types/synapse'
import type { GroupKey } from './types'

type Props = {
  data: Outcome[]
  groupBy: GroupKey
}

export function OutcomeGraph({ data }: Props) {
  const chartData = useMemo(
    () =>
      data
        .slice()
        .sort((a, b) => +new Date(a.timestamp) - +new Date(b.timestamp))
        .map((d) => ({
          t: new Date(d.timestamp).toLocaleString(),
          scalar_reward: d.scalar_reward,
          utility_score: d.utility_score,
        })),
    [data]
  )

  return (
    <div style={{ width: '100%', height: 320 }}>
      <h2 className="text-lg font-semibold mb-2">Outcomes over Time</h2>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="t" tick={{ fontSize: 10 }} />
          <YAxis />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="scalar_reward" dot={false} />
          <Line type="monotone" dataKey="utility_score" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

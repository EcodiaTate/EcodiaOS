// apps/eco-console/src/components/synapse/OutcomeTable.tsx
'use client'
import { Outcome } from '@/types/synapse'

export function OutcomeTable({ data }: { data: Outcome[] }) {
  return (
    <div>
      <h2 className="text-lg font-semibold mb-2">Outcome Table</h2>
      <div className="overflow-x-auto max-h-[400px] overflow-y-scroll border rounded">
        <table className="min-w-full text-xs">
          <thead className="bg-gray-100 sticky top-0">
            <tr>
              <th className="text-left p-2">Timestamp</th>
              <th className="text-left p-2">Arm</th>
              <th className="text-left p-2">Reward</th>
              <th className="text-left p-2">Utility</th>
              <th className="text-left p-2">Reasoning</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(0, 100).map((o) => (
              <tr key={o.episode_id} className="border-t">
                <td className="p-2">{new Date(o.timestamp).toLocaleString()}</td>
                <td className="p-2">{o.arm_id}</td>
                <td className="p-2">{o.scalar_reward.toFixed(2)}</td>
                <td className="p-2">{o.utility_score?.toFixed(2)}</td>
                <td className="p-2">{o.reasoning}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// apps/eco-console/src/lib/api/synapse.ts
import { Outcome } from '@/types/synapse'
import { useQuery } from '@tanstack/react-query'

export function useOutcomes() {
  return useQuery<Outcome[]>({
    queryKey: ['outcomes'],
    queryFn: async () => {
      const res = await fetch('/api/obs/outcomes')
      if (!res.ok) throw new Error('Failed to load outcomes')
      return res.json()
    },
  })
}

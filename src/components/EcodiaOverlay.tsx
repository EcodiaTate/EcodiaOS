'use client'

import { useModeStore } from '@/stores/useModeStore'
import RootOverlay from '@/components/RootOverlay'
import ConstellationOverlay from '@/components/ConstellationOverlay'
import ReturnOverlay from '@/components/ReturnOverlay'
import TalkOverlay from '@/components/TalkOverlay'
import HubOverlay from '@/components/HubOverlay'
import GuideOverlay from '@/components/GuideOverlay'
import BootOverlay from '@/components/BootOverlay'
export default function EcodiaOverlay() {
  const mode = useModeStore((s) => s.mode)

  switch (mode) {
    case 'root':
      return <RootOverlay />
    case 'constellation':
      return <ConstellationOverlay />
    case 'guide':
      return <GuideOverlay />
    case 'boot':
      return <BootOverlay/>
    case 'return':
      return <ReturnOverlay />
    case 'talk':
      return <TalkOverlay />
    case 'hub':
      return <HubOverlay />
    default:
      return null
  }
}

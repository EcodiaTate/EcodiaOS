// stores/usePulseStore.ts
import { create } from 'zustand'

type PulseState = {
  triggerPulse: (index: number) => void
  registerTrigger: (fn: (index: number) => void) => void
}

export const usePulseStore = create<PulseState>((set) => {
  let triggerFn: (index: number) => void = () => {}

  return {
    triggerPulse: (index) => triggerFn(index),
    registerTrigger: (fn) => { triggerFn = fn }
  }
})

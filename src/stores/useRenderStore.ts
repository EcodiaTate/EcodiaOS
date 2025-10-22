import { create } from 'zustand'

export type OutputMode = 'typing' | 'voice'

interface RenderStore {
  outputMode: OutputMode
  setOutputMode: (mode: OutputMode) => void
}

export const useRenderStore = create<RenderStore>((set) => ({
  outputMode: 'typing' as OutputMode,
  setOutputMode: (mode) => set({ outputMode: mode }),
}))

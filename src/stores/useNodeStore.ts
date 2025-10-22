// stores/useNodeStore.ts
import { create } from 'zustand'
import * as THREE from 'three'

interface NodeStore {
  nodes: Record<string, THREE.Vector3> // or ref, if you prefer
  registerNode: (word: string, position: THREE.Vector3) => void
  clearNodes: () => void
}

export const useNodeStore = create<NodeStore>((set) => ({
  nodes: {},

  registerNode: (word, position) =>
    set((state) => ({
      nodes: { ...state.nodes, [word]: position },
    })),

  clearNodes: () => set({ nodes: {} }),
}))


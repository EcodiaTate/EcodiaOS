import { create } from 'zustand'

export type Mode = 'boot' | 'hub' | 'root' | 'constellation' | 'login' | 'talk' | 'guide'

export interface CameraTarget {
  position: [number, number, number]
  lookAt: [number, number, number]
  useOrbit?: boolean
  allowUserControl?: boolean
}

interface ModeStore {
  mode: Mode
  targetCamera: CameraTarget
  setMode: (mode: Mode) => void
  setCameraTarget: (target: CameraTarget) => void
  isAutoRotateEnabled: () => boolean
  isUserControlEnabled: () => boolean
}

const defaultCameraTargets: Record<Mode, CameraTarget> = {
  boot: { position: [0, 0, 500], lookAt: [0, 0, 0], useOrbit: true, allowUserControl: false },
  hub: { position: [0, 0, 6000], lookAt: [0, 0, 0], useOrbit: true, allowUserControl: false },
  root: { position: [0, 0, 7500], lookAt: [0, 0, 0], useOrbit: true, allowUserControl: false },
  constellation: { position: [0, 0, 4500], lookAt: [0, 0, 0], useOrbit: false, allowUserControl: true },
  login: { position: [0, 0, 7000], lookAt: [0, 0, 0], useOrbit: true, allowUserControl: false },
  talk: { position: [0, 0, 4900], lookAt: [0, 0, 0], useOrbit: true, allowUserControl: false },
  guide: { position: [600, 0, 6000], lookAt: [0, 0, 0], useOrbit: true, allowUserControl: false },
}

export const useModeStore = create<ModeStore>((set, get) => ({
  mode: 'boot',
  targetCamera: defaultCameraTargets.boot,

  setMode: (newMode: Mode) => {
    const target = defaultCameraTargets[newMode] || defaultCameraTargets.root
    set({
      mode: newMode,
      targetCamera: target,
    })
  },

  setCameraTarget: (target: CameraTarget) => {
    set({ targetCamera: target })
  },

  isAutoRotateEnabled: () => get().mode !== 'constellation',
  isUserControlEnabled: () => get().mode === 'constellation',
}))

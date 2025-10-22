import { create } from 'zustand';

interface VoiceStore {
  isPlaying: boolean;
  setIsPlaying: (isPlaying: boolean) => void;
}

export const useVoiceStore = create<VoiceStore>((set) => ({
  isPlaying: false,
  setIsPlaying: (isPlaying) => set({ isPlaying }),
}));
// stores/useSoulStore.ts
import { create } from 'zustand'

interface SoulStore {
  // For the final, matched soul
  soulId: string | null
  matchedWords: string[] | null

  // Persisted user id (UUID used by backend)
  userUuid: string | null
  setUserUuid: (uuid: string | null) => void

  // For the in-progress creation flow
  selectedWords: string[]
  toggleWordSelection: (word: string, maxWords: number) => void

  // General methods
  setMatchedSoul: (id: string, words: string[]) => void
  clearSoul: () => void
}

export const useSoulStore = create<SoulStore>((set) => ({
  soulId: null,
  matchedWords: null,

  userUuid: null,
  setUserUuid: (uuid) => set({ userUuid: uuid }),

  selectedWords: [],
  toggleWordSelection: (word, maxWords) =>
    set((state) => {
      const isSelected = state.selectedWords.includes(word)
      if (isSelected) return { selectedWords: state.selectedWords.filter((w) => w !== word) }
      if (state.selectedWords.length < maxWords) return { selectedWords: [...state.selectedWords, word] }
      return {}
    }),

  setMatchedSoul: (id, words) =>
    set({
      soulId: id,
      matchedWords: words,
      selectedWords: [],
    }),

  clearSoul: () =>
    set({
      soulId: null,
      matchedWords: null,
      userUuid: null,
      selectedWords: [],
    }),
}))

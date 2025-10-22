export type Role = 'user' | 'ecodia'

export interface Message {
  role: Role
  content: string

  // --- optional metadata we actually use in UI / pagination ---
  id?: string                // stable message key from backend (elementId)
  created_at?: string        // ISO timestamp (used for before-cursor)
  episode_id?: string        // for feedback
  arm_id?: string            // for feedback
  ttsPending?: boolean       // voice render placeholder
  emotionClass?: string      // typing renderer flair
}

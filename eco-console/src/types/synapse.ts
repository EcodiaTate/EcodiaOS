// apps/eco-console/src/types/synapse.ts
export type Outcome = {
  timestamp: string
  episode_id: string
  task_key: string
  arm_id: string
  strategy: string
  model: string
  tokenizer: string
  scalar_reward: number
  reward_vector: number[]
  success: number
  utility_score: number
  reasoning: string
}


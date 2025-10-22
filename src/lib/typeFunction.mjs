// Utility to pick 1 or more random elements from an array
export function pickRandom(arr, count = 1) {
  if (arr.length < 1) return []
  const shuffled = [...arr].sort(() => Math.random() - 0.5)
  return shuffled.slice(0, count)
}

// Core: Per-character typing with controlled speed/variance
export function type(text, speed = 50, variance = 5) {
  return text.split('').map(char => ({
    type: 'char',
    char,
    delay: speed + Math.floor(Math.random() * variance)
  }))
}

// Pause helper
export function pause(duration) {
  return [{ type: 'pause', duration }]
}

// Backspace then retype a new soul
export function backspace(original, replacement, speed = 30) {
  const erase = original.split('').map(() => ({
    type: 'backspace',
    delay: speed
  }))
  const typeNew = type(replacement, speed)
  return [...erase, ...pause(150), ...typeNew]
}

// Glitch: type > flicker > erase
export function glitch(text, flickerCount = 3, speed = 50) {
  const steps = []

  // Step 1: Type original
  steps.push(...type(text, speed, 3))
  steps.push(...pause(300))

  // Step 2: Glitch flickers
  for (let i = 0; i < flickerCount; i++) {
    steps.push({ type: 'glitch', text })
    steps.push({ type: 'pause', duration: 60 })
  }

  // Step 3: Erase
  steps.push({ type: 'backspace', count: text.length })
  steps.push(...pause(100))

  return steps
}

// Add a newline
export function linebreak() {
  return [{ type: 'linebreak' }]
}

// Emphasize text (e.g., render as bold or uppercase)
export function emphasize(text) {
  return [{ type: 'emphasize', text }]
}

// Join multiple step groups into one flattened array
export function sequence(...parts) {
  return parts.flat()
}

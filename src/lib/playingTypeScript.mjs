/**
 * Advanced Typing Script Player (ES Module)
 * Supports rich, probabilistic, expressive output for a living AI feel.
 */

export async function playTypingScript(script, targetEl) {
  let result = ''

  const render = (text) => {
    if (!targetEl) return
    targetEl.innerHTML = escapeHtml(text).replace(/\n/g, '<br>')
  }

  const append = (text) => {
    result += text
    render(result)
  }

  const replace = (newText) => {
    result = newText
    render(result)
  }

  const lineBreak = () => {
    result += '\n'
    render(result)
  }

  const typeWithHumanFeel = async (text) => {
    for (const char of text) {
      append(char)
      const base = Math.random() < 0.1 ? 10 : 15 + Math.random() * 10
      await wait(base)
    }
  }

  const backspaceByWord = async (count = 1) => {
    const words = result.split(/(\s+)/)
    let popped = ''
    for (let i = 0; i < count; i++) {
      popped = words.pop() + popped
      words.pop()
    }
    result = words.join('')
    render(result)
    await wait(30 * popped.length + 80)
  }

  for (const step of script) {
    switch (step.type) {
      case 'char':
        append(step.char)
        await wait(step.delay ?? 1)
        break

      case 'type':
        await typeWithHumanFeel(step.text)
        break

      case 'pause':
        await wait(step.duration ?? 0)
        break

      case 'backspace':
        if ('count' in step) {
          result = result.slice(0, -step.count)
          render(result)
          await wait(20 * step.count)
        } else {
          result = result.slice(0, -1)
          render(result)
          await wait(step.delay ?? 20)
        }
        break

      case 'linebreak':
        lineBreak()
        break

      case 'emphasize':
        append(step.text.toUpperCase())
        await wait(10 * step.text.length)
        break

      case 'glitch': {
        const GLITCH_GLYPHS = '█▓▒░#@$%&*+=<>?!/\\|'.split('')
        const original = result
        const rounds = 3 + Math.floor(Math.random() * 2)

        for (let i = 0; i < rounds; i++) {
          const glitchLength = Math.floor(step.text.length * (0.4 + Math.random() * 0.6))
          const glitched = Array.from({ length: glitchLength }, () =>
            GLITCH_GLYPHS[Math.floor(Math.random() * GLITCH_GLYPHS.length)]
          ).join('')
          if (targetEl) {
            targetEl.innerHTML = `<span class="glitch-flicker">${glitched}</span>`
          }
          await wait(50 + Math.random() * 40)
        }

        render(original)
        break
      }

      default:
        console.warn('Unknown step type:', step.type)
    }
  }

  return result.trim()
}

export function wait(ms) {
  const start = performance.now()
  return new Promise(resolve => {
    function check() {
      if (performance.now() - start >= ms) resolve()
      else requestAnimationFrame(check)
    }
    check()
  })
}

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

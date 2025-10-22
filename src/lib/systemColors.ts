export type System =
  | 'Qora' | 'Evo' | 'Atune' | 'Contra'
  | 'Thread' | 'Ember' | 'Nova' | 'Unity'

export const systemColorsLight: Record<System, string> = {
  Qora: '#e9c85f',     // golden sun
  Evo: '#a077ff',      // radiant violet
  Atune: '#4ddbd5',    // tropical aqua
  Contra: '#f47789',   // coral rose
  Thread: '#54e68b',   // jungle green
  Ember: '#ff5f40',    // molten clay
  Nova: '#ffb3f5',     // fuchsia bloom
  Unity: '#6ef0bb',    // mint vitality
}

export const systemColorsDark: Record<System, string> = {
  Qora: '#f4d35e',     // deeper gold
  Evo: '#b388eb',      // lavender glow
  Atune: '#5fdde5',    // aurora blue
  Contra: '#ff99a3',   // soft rose
  Thread: '#9df59f',   // leaf green
  Ember: '#ff744f',    // ember orange
  Nova: '#ffd6ff',     // pastel magenta
  Unity: '#78fcae',    // seafoam
}

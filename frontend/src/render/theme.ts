/**
 * Colour tokens. Shared contract for every UI
 * component: import `color` and pass the result to Ink's `color`/`backgroundColor`.
 * `color()` returns undefined under NO_COLOR so Ink renders plain text.
 */
export const tokens = {
  ink: '#131312', // app background
  graphite: '#23211F', // raised surfaces: user message, code blocks
  rule: '#2E2C29', // borders, table rules, composer top border
  paper: '#E7E4DC', // primary text
  dim: '#98948A', // secondary text, hints, hosts
  ledger: '#D4A55A', // accent: headings, selection, brand
  gain: '#86B98A', // success, positive
  loss: '#D9796B', // failure, negative
  warn: '#CFC66F', // warnings, notices, partial runs
  faint: '#837F75', // domains, URLs, as-of dates: still >= 4.5:1 on ink
} as const;

export type Token = keyof typeof tokens;

export const noColor = (): boolean => {
  const v = process.env.NO_COLOR;
  return v !== undefined && v !== '';
};

/** Truecolor when the terminal says so; otherwise tokens are mapped to the xterm 256-colour palette. */
export function truecolor(): boolean {
  const term = (process.env.COLORTERM ?? '').toLowerCase();
  return term === 'truecolor' || term === '24bit';
}

const CUBE_LEVELS = [0, 95, 135, 175, 215, 255] as const;

function rgbOf(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.replace('#', ''), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

/** Nearest xterm-256 palette index (6x6x6 cube or the grey ramp) to a `#rrggbb` colour. */
export function nearest256(hex: string): number {
  const [r, g, b] = rgbOf(hex);
  const nearestLevel = (v: number): number => {
    let best = 0;
    CUBE_LEVELS.forEach((level, index) => {
      if (Math.abs(level - v) < Math.abs((CUBE_LEVELS[best] ?? 0) - v)) best = index;
    });
    return best;
  };
  const ci = [nearestLevel(r), nearestLevel(g), nearestLevel(b)] as const;
  const cube = [CUBE_LEVELS[ci[0]] ?? 0, CUBE_LEVELS[ci[1]] ?? 0, CUBE_LEVELS[ci[2]] ?? 0] as const;
  const cubeIndex = 16 + 36 * ci[0] + 6 * ci[1] + ci[2];
  const average = Math.round((r + g + b) / 3);
  const greyStep = Math.min(23, Math.max(0, Math.round((average - 8) / 10)));
  const grey = 8 + 10 * greyStep;
  const distance = (x: readonly number[]): number =>
    (x[0]! - r) ** 2 + (x[1]! - g) ** 2 + (x[2]! - b) ** 2;
  return distance([grey, grey, grey]) < distance(cube) ? 232 + greyStep : cubeIndex;
}

export function color(token: Token): string | undefined {
  if (noColor()) return undefined;
  return truecolor() ? tokens[token] : `ansi256(${nearest256(tokens[token])})`;
}

export const glyphs = {
  prompt: '›',
  warn: '⚠',
  fail: '✕',
  ok: '✓',
  dot: '·',
} as const;

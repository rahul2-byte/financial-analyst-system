#!/usr/bin/env node
// Bundles the TS terminal UI into a single ESM file: dist/cli.js.
// Only Node builtins stay external; everything else is inlined.
import { build } from 'esbuild';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

await build({
  entryPoints: ['src/cli.tsx'],
  outfile: 'dist/cli.js',
  bundle: true,
  platform: 'node',
  format: 'esm',
  target: 'node20',
  mainFields: ['module', 'main'],
  conditions: ['node'],
  alias: {
    // Ink imports react-devtools-core, an optional peer that is not always
    // installed. Alias it to an empty stub so the bundle builds without it.
    'react-devtools-core': path.join(here, 'scripts', 'stubs', 'react-devtools-core.mjs'),
  },
  banner: {
    // Bundled CJS deps call require() (signal-exit → assert); in ESM output
    // that is a dynamic require, so provide a real one via createRequire.
    js: [
      '#!/usr/bin/env node',
      "import { createRequire } from 'node:module';",
      'const require = createRequire(import.meta.url);',
    ].join('\n'),
  },
  jsx: 'automatic',
  // Without this React ships its development build: per-render perf tracking and
  // ~5x the CPU while streaming (P7 §11 measurement).
  define: { 'process.env.NODE_ENV': '"production"' },
  sourcemap: false,
  minify: false,
  legalComments: 'none',
  logLevel: 'info',
});

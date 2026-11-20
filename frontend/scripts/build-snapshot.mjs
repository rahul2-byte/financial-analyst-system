// Bundles scripts/snapshot.tsx to dist/snapshot.mjs (same options as esbuild.config.mjs).
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import * as esbuild from 'esbuild';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

await esbuild.build({
  entryPoints: [path.join(root, 'scripts', 'snapshot.tsx')],
  outfile: path.join(root, 'dist', 'snapshot.mjs'),
  bundle: true,
  platform: 'node',
  format: 'esm',
  target: 'node20',
  jsx: 'automatic',
  alias: {
    'react-devtools-core': path.join(root, 'scripts', 'stubs', 'react-devtools-core.mjs'),
  },
  banner: {
    // The banner runs before the bundle, so chalk (inside Ink) sees FORCE_COLOR when it
    // loads. The harness stdout is a pipe, not a tty, so without this every colour is dropped.
    js: [
      "process.env.FORCE_COLOR ??= '3';",
      // Without COLORTERM, supports-color caps truecolor at 256 colours, and TERM=linux drops
      // to 16: the palette is then approximated (the gain tick came out as the dim grey).
      "process.env.COLORTERM ??= 'truecolor';",
      "import { createRequire as __finaiCreateRequire } from 'node:module'; const require = __finaiCreateRequire(import.meta.url);",
    ].join('\n'),
  },
  logLevel: 'warning',
});

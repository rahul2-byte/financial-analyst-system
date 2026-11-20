/** The shipped bundle is a production React build and stays under 3 MB. */
import { existsSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const bundle = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'cli.js');

describe.skipIf(!existsSync(bundle))('dist/cli.js', () => {
  it('is at most 3 MB', () => {
    expect(statSync(bundle).size).toBeLessThanOrEqual(3 * 1024 * 1024);
  });

  it('bundles the production React build, not the development one', () => {
    const text = readFileSync(bundle, 'utf8');
    expect(text).not.toContain('runWithFiberInDEV');
    expect(text).not.toContain('logComponentRender');
  });
});

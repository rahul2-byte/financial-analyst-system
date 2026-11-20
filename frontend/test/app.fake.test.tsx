import React from 'react';
import { render } from 'ink-testing-library';
import { describe, expect, it, vi } from 'vitest';

import { FakeBridge } from '../src/bridge/fake.js';
import { App } from '../src/ui/App.js';
import { PLACEHOLDER } from '../src/ui/Composer.js';
import type { BridgeLaunch } from '../src/ui/hooks/useBridge.js';

const launch: BridgeLaunch = {
  repoRoot: '/nonexistent-repo',
  cwd: '/nonexistent-repo',
  dataDir: '.finai',
  columns: 100,
  rows: 30,
};

const settle = (ms = 80): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

describe('App with the in-process fake bridge', () => {
  it('shows the header and an empty composer once connected', async () => {
    const bridge = new FakeBridge();
    const app = render(<App launch={launch} injected={bridge} />);
    try {
      await vi.waitFor(() => expect(app.lastFrame()).toContain('FIN-AI'));
      expect(app.lastFrame()).toContain(PLACEHOLDER);
    } finally {
      app.unmount();
      bridge.close();
    }
  });

  it('opens the help overlay for /help and closes it on escape', async () => {
    const bridge = new FakeBridge();
    const app = render(<App launch={launch} injected={bridge} />);
    try {
      await vi.waitFor(() => expect(app.lastFrame()).toContain('FIN-AI'));
      app.stdin.write('/help');
      await settle();
      app.stdin.write('\r');
      await vi.waitFor(() => expect(app.lastFrame()).toContain('Commands'));

      app.stdin.write('\u001b');
      await vi.waitFor(() => expect(app.lastFrame()).not.toContain('Commands'));
    } finally {
      app.unmount();
      bridge.close();
    }
  });
});

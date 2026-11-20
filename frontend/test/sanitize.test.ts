import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { sanitizeTerminalText } from '../src/render/sanitize.js';

interface SanitizeCase {
  input: string;
  output: string;
}

const cases = JSON.parse(
  readFileSync(new URL('./goldens/sanitize_cases.json', import.meta.url), 'utf8'),
) as SanitizeCase[];

describe('sanitizeTerminalText', () => {
  it('has cases to check', () => {
    expect(cases.length).toBeGreaterThan(0);
  });

  cases.forEach((testCase, index) => {
    it(`golden case ${index}`, () => {
      expect(sanitizeTerminalText(testCase.input)).toBe(testCase.output);
    });
  });

  it('keeps tabs, newlines and carriage returns', () => {
    expect(sanitizeTerminalText('a\tb\nc\r\nd')).toBe('a\tb\nc\r\nd');
  });

  it('removes DEL and a bare ESC that is not a sequence', () => {
    expect(sanitizeTerminalText('x\x7fy\x1bz')).toBe('xyz');
  });
});

/**
 * Exact port of `sanitize_terminal_text` (backend/finai/safety.py).
 *
 * Removes ANSI CSI and OSC escape sequences, then unsafe control characters.
 * Whitespace (\t, \n, \r, space) is preserved.
 */

// ESC ] ... (BEL | ESC \)  — OSC, e.g. hyperlinks; or ESC [ params intermediates final — CSI.
const ESCAPE_SEQUENCE = /\x1b(?:\][^\x07]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~])/g;
// C0 controls except \t (0x09), \n (0x0a) and \r (0x0d), plus DEL.
const CONTROL = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;

export function sanitizeTerminalText(value: string): string {
  return value.replace(ESCAPE_SEQUENCE, '').replace(CONTROL, '');
}

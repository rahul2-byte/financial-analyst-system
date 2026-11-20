/**
 * Wire protocol version spoken by this frontend.
 *
 * Must equal `PROTOCOL_VERSION` in `backend/finai/bridge/protocol.py`, which is
 * exported into `protocol/schema/protocol.schema.json` as the title
 * "FIN-AI bridge protocol v1". `test/version.test.ts` asserts both.
 */
export const PROTOCOL_VERSION = 1;

/** Message shown when the backend speaks a different protocol version. */
export const PROTOCOL_MISMATCH_MESSAGE =
  'Frontend and backend are out of sync. Run: uv sync && npm --prefix frontend run build';

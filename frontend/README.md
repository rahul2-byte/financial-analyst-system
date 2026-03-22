# Frontend (Next.js)

## Development

Run the app:

```bash
npm run dev
```

Open `http://localhost:3000`.

## Streaming Configuration

The chat client supports direct backend streaming in development to avoid proxy buffering.

- Optional env var: `NEXT_PUBLIC_API_BASE_URL`
- Example value: `http://127.0.0.1:8000`

Resolution order for chat endpoint:

1. `NEXT_PUBLIC_API_BASE_URL + /api/chat` (if set)
2. `http://127.0.0.1:8000/api/chat` in development
3. `/api/chat` in non-development environments

If streaming appears batched in UI, set:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Then restart `npm run dev`.

## Test Commands

- Unit/integration tests: `npm test`
- Coverage: `npm run test:coverage`
- End-to-end tests: `npm run test:e2e`
- Full suite: `npm run test:all`

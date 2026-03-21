# Design Spec: Frontend Performance & Architecture Optimization (Phase 1)

**Date:** 2026-03-20
**Topic:** Performance and architecture refactor for the FinAI Intelligence frontend.
**Status:** Draft

---

## 1. Problem Statement

The current frontend implementation of FinAI Intelligence faces several architectural and performance challenges that will hinder user experience as conversations grow longer or more complex:
- **Inefficient State Updates:** Chat streaming currently triggers $O(n^2)$ complexity updates by re-cloning the entire message history on every token.
- **Rendering Overhead:** All messages (including complex charts) are rendered simultaneously, which will lead to DOM bloat and scrolling lag.
- **Monolithic Components:** `MessageItem.tsx` is over-burdened with responsibilities (Markdown, Charts, Actions, Layout), making it fragile and hard to maintain.
- **Loose Type Safety:** Chart data types are too generic, leading to potential runtime failures.

---

## 2. Goals & Success Criteria

- **Zero-Stutter Streaming:** Maintain 60fps even during high-velocity text streaming.
- **Virtualization:** Only render visible messages, ensuring smooth scrolling for conversation of any length.
- **Modular Architecture:** Decompose monolithic components into single-responsibility units.
- **Hardened Types:** Strict TypeScript definitions for all data structures.

---

## 3. Technical Approach

### 3.1 Optimized Streaming Logic
- **Module:** `frontend/hooks/useChat.ts`
- **Change:** Transition from index-based mapping to a more efficient functional state update. We will ensure that the "last" message is updated in place via a shallow copy only, avoiding deep cloning of the entire message array.
- **Optimistic State:** Implement React 19's `useOptimistic` for user messages to provide instantaneous UI feedback before API round-trips.
- **Validation:** Monitor React DevTools for unnecessary re-renders in historical message items.

### 3.2 List Virtualization
- **Library:** `@tanstack/react-virtual` (already in `package.json`).
- **Module:** `frontend/components/chat/ChatWindow.tsx`
- **Change:** Wrap the `messages.map` logic in a `Virtualizer`. 
- **Sticky Handling:** Use the virtualizer's `scrollToIndex(messages.length - 1, { align: 'end' })` for auto-scrolling to ensure compatibility with dynamic row offsets.
- **Dynamic Height Measurement:** Attach `virtualizer.measureElement` to each message container to handle height changes from charts or streaming text blocks.

### 3.3 Component Decomposition & Memoization
- **MessageItem.tsx** will be split into:
    1.  `MarkdownRenderer.tsx`: Purely for rendering and styling Markdown content using `react-markdown` and `shiki`.
    2.  `MessageActions.tsx`: UI and logic for "Copy", "Regenerate", and "Feedback" buttons.
    3.  `MessageItem.tsx`: Simplified container that orchestrates the layout.
- **Memoization:** Wrap all message components in `React.memo` to ensure $O(1)$ re-render cost per token during streaming (only the streaming message re-renders).
- **Ref Handling:** Leverage React 19's native `ref` prop support (no `forwardRef` needed) for cleaner virtualizer integration.
- **Location:** `frontend/components/chat/`

### 3.4 Strict Chart Types
- **Module:** `frontend/types/index.ts`
- **Change:** Refine `ChartPayload` and `ChartDataPoint` to use more precise generics where possible, or at least define common financial data shapes (e.g., OHLC, TimeSeries).

---

## 4. Architecture Diagram (Conceptual)

```
[ChatWindow]
    └── [Virtualizer]
        └── [MessageItem]
            ├── [Avatar]
            ├── [MarkdownRenderer]
            │       └── [CodeBlock]
            ├── [MessageActions]
            └── [VizContainer]
                    └── [ChartWidget]
```

---

## 5. Implementation Sequence

1.  **Harden Types:** Update `types/index.ts`.
2.  **Refactor Hooks:** Implement efficient state updates in `useChat.ts`.
3.  **Decompose Components:** Extract `MarkdownRenderer` and `MessageActions`.
4.  **Implement Virtualization:** Integrate TanStack Virtual in `ChatWindow.tsx`.
5.  **Verify:** Run `npm run lint` and verify scrolling/streaming behavior.

---

## 6. Testing Plan

- **Manual Verification:** Test with 100+ messages and large streaming text blocks.
- **Performance Profiling:** Verify that frame drops do not occur during active streaming.
- **Regression:** Ensure chart rendering and copy-to-clipboard functionality remain intact.

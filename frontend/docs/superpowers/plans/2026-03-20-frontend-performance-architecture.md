# Frontend Performance & Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize frontend performance and architecture by implementing list virtualization, efficient state updates, and component decomposition.

**Architecture:** 
- Implement $O(1)$ state updates in `useChat` using functional updates and `useOptimistic`.
- Introduce `@tanstack/react-virtual` in `ChatWindow` for efficient rendering.
- Decompose `MessageItem` into `MarkdownRenderer`, `MessageActions`, and a simplified `MessageItem` container with `React.memo` for $O(1)$ re-renders.

**Tech Stack:** Next.js 16, React 19, Tailwind CSS 4, @tanstack/react-virtual, Framer Motion, Lucide React.

---

### Task 1: Harden Type Safety

**Files:**
- Modify: `frontend/types/index.ts`

- [ ] **Step 1: Update Chart and Message Types**
Refine types to support better inference and strictness.

```typescript
// frontend/types/index.ts
export interface ChartPayload {
  title: string;
  type: ChartType;
  data: Record<string, string | number>[]; // Strict data points
  xAxisKey: string;
  seriesKeys: string[]; 
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  charts?: ChartPayload[];
  timestamp: Date;
  isStreaming?: boolean;
}
```

- [ ] **Step 2: Verify Types**
Run `npm run lint` or `tsc` in frontend to ensure no regressions.

- [ ] **Step 3: Commit**
```bash
git add frontend/types/index.ts
git commit -m "chore: harden message and chart types"
```

---

### Task 2: Optimize useChat Hook

**Files:**
- Modify: `frontend/hooks/useChat.ts`

- [ ] **Step 1: Implement Efficient State Updates**
Update `sendMessage` to only modify the last message's content/charts without cloning the entire history.

```typescript
// In setMessages callback:
setMessages((prev) => {
  const lastMsg = prev[prev.length - 1];
  if (!lastMsg || lastMsg.id !== assistantMessageId) return prev;
  
  const updatedLastMsg = { ...lastMsg };
  if (event.type === "text_delta") {
    updatedLastMsg.content += event.content;
  }
  // ... handle other events
  
  return [...prev.slice(0, -1), updatedLastMsg];
});
```

- [ ] **Step 2: Add useOptimistic (React 19)**
Integrate `useOptimistic` for immediate user message display. Ensure `sendMessage` uses `React.useTransition` in the UI component to trigger the optimistic state.

- [ ] **Step 3: Commit**
```bash
git add frontend/hooks/useChat.ts
git commit -m "perf: optimize chat streaming state updates"
```

---

### Task 5: Implement List Virtualization

**Files:**
- Modify: `frontend/components/chat/ChatWindow.tsx`

- [ ] **Step 1: Integrate TanStack Virtual**
Initialize `useVirtualizer` with `scrollRef` and `messages.length`. Use `estimateSize` to provide a baseline for messages (e.g., 100px).

- [ ] **Step 2: Implement Virtual Row Rendering**
Map through `virtualizer.getVirtualItems()` and render absolute positioned containers.

- [ ] **Step 3: Implement Dynamic Height Measurement**
Attach `virtualizer.measureElement` to message containers in `MessageItem` (pass via ref). Use a `ResizeObserver` if necessary to re-measure when content (streaming text/charts) changes.

- [ ] **Step 4: Update Auto-scroll & Sticky Logic**
Use `virtualizer.scrollToIndex(messages.length - 1)` within a `useLayoutEffect` triggered by total content size changes to ensure "Sticky Scroll" behavior.

- [ ] **Step 5: Commit**
```bash
git add frontend/components/chat/ChatWindow.tsx
git commit -m "perf: implement list virtualization for chat window"
```

---

### Task 6: Verification & Cleanup

- [ ] **Step 1: Lint and Build**
Run `npm run lint && npm run build` in `frontend/`.

- [ ] **Step 2: Performance Profiling**
Use React DevTools Profiler to verify $O(1)$ re-renders during active streaming (only the streaming message should re-render).

- [ ] **Step 3: Final UX Check**
Ensure scrolling is fluid and "Sticky Scroll" works as expected with large amounts of data.


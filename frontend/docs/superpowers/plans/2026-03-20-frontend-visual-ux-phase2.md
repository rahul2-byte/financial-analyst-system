# Phase 2: "The Living Report" Visual & UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the platform into a high-fidelity document engine with a Minimalist/Swiss aesthetic, optimized for reading long-form reports and data analysis.

**Architecture:** 
- Implement a document-centric layout with a centered reading column (`max-w-3xl`).
- Update the design system with OLED black, blueprint borders, and IBM Plex Sans typography.
- Refactor components (MessageItem, MarkdownRenderer, Tables) to remove chat-centric elements and adopt a professional, structured report look.
- Add staggered Framer Motion animations for sequential data presentation.

**Tech Stack:** Next.js 16, Tailwind CSS 4, Google Fonts (IBM Plex Sans), Framer Motion, Lucide React.

---

### Task 1: Theme & Typography Hardening

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/app/layout.tsx`

- [ ] **Step 1: Update Google Fonts in layout**
Include IBM Plex Sans and set it as the primary sans font.

```typescript
// frontend/app/layout.tsx
import { IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-sans",
});
```

- [ ] **Step 2: Update Tailwind @theme**
Refine OLED palette and blueprint borders.

```css
/* frontend/app/globals.css */
@theme {
  --color-bg-primary: #020617; /* Slate-950 */
  --color-bg-secondary: #0f172a; /* Slate-900 */
  --color-border-blueprint: rgba(255, 255, 255, 0.08);
  --color-accent: #10b981; /* Emerald-500 */
}
```

- [ ] **Step 3: Commit**
```bash
git add frontend/app/layout.tsx frontend/app/globals.css
git commit -m "style: update theme to OLED black and IBM Plex Sans"
```

---

### Task 2: Layout & Reading Column Refactor

**Files:**
- Modify: `frontend/components/chat/ChatWindow.tsx`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Apply Reading Column Constraint**
Update the main content container to `max-w-3xl`.

```tsx
// frontend/components/chat/ChatWindow.tsx
<div className="chat-content mx-auto w-full max-w-3xl pb-[180px] pt-12 px-6">
```

- [ ] **Step 2: Refine Header Glassmorphism**
Update the header with `backdrop-blur-xl` and blueprint border.

- [ ] **Step 3: Commit**
```bash
git add frontend/components/chat/ChatWindow.tsx frontend/app/page.tsx
git commit -m "layout: center reading column and refine header glassmorphism"
```

---

### Task 3: Document-Centric MessageItem

**Files:**
- Modify: `frontend/components/chat/MessageItem.tsx`
- Modify: `frontend/components/chat/MessageActions.tsx`

- [ ] **Step 1: Remove Assistant "Bubbles"**
Refactor `MessageItem` so assistant responses appear as flat report sections without background fills or avatars in the flow.

- [ ] **Step 2: Refine User Queries**
User messages should appear as right-aligned annotations without heavy fills.

- [ ] **Step 3: Commit**
```bash
git add frontend/components/chat/MessageItem.tsx frontend/components/chat/MessageActions.tsx
git commit -m "style: refactor MessageItem for document-centric flow"
```

---

### Task 4: "Caged" Tables & Numerical Typography

**Files:**
- Modify: `frontend/components/chat/MarkdownRenderer.tsx`

- [ ] **Step 1: Implement "Caged" Table Styling**
Use `divide-y-[0.5px] divide-white/5` and ultra-thin `0.5px` internal borders. Apply `font-mono` and `tabular-nums` (JetBrains Mono) to numerical data points within table cells using a basic heuristic.

```tsx
// frontend/components/chat/MarkdownRenderer.tsx
td({ children }) {
  const isNumerical = typeof children === "string" && !isNaN(Number(children.replace(/[,%$]/g, "")));
  return (
    <td className={cn(
      "px-4 py-3 border-b-[0.5px] border-white/5",
      isNumerical ? "font-mono tabular-nums text-emerald-400/90" : "text-text-secondary"
    )}>
      {children}
    </td>
  );
},
```

- [ ] **Step 2: Commit**
```bash
git add frontend/components/chat/MarkdownRenderer.tsx
git commit -m "style: implement Swiss-style caged tables with mono numericals"
```

---

### Task 5: Staggered Entry Animations & A11y

**Files:**
- Modify: `frontend/components/chat/MessageItem.tsx`

- [ ] **Step 1: Add Staggered Framer Motion Transitions**
Implement `initial={{ opacity: 0, y: 10 }}` and `animate={{ opacity: 1, y: 0 }}` for report blocks with slight delays. Use `useReducedMotion` to disable animations if preferred.

- [ ] **Step 2: Commit**
```bash
git add frontend/components/chat/MessageItem.tsx
git commit -m "anim: add staggered entry transitions with A11y respect"
```

---

### Task 6: Header Polish & Live Pulse Indicator

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/app/page.tsx` (Header)
- Modify: `frontend/components/chat/ChatInput.tsx`

- [ ] **Step 1: Implement "LIVE ANALYSIS" Pulse Indicator**
Add `@keyframes pulse-emerald` to `globals.css` and apply the `animate-pulse-live` class to the emerald status badge in the header.

```css
/* frontend/app/globals.css */
@keyframes pulse-emerald {
  0%, 100% { opacity: 1; transform: scale(1); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
  50% { opacity: 0.7; transform: scale(1.1); box-shadow: 0 0 10px 4px rgba(16, 185, 129, 0.2); }
}
.animate-pulse-live {
  animation: pulse-emerald 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
```

- [ ] **Step 2: Refine Floating Command Bar**
Apply `glassmorphism`, `backdrop-blur`, and an Emerald accent for the input area.

- [ ] **Step 3: Verification**
Run `npm run lint && npm run build` and perform a visual check on mobile vs desktop.

- [ ] **Step 4: Commit**
```bash
git add frontend/app/page.tsx frontend/components/chat/ChatInput.tsx frontend/app/globals.css
git commit -m "style: implement live pulse indicator and final command bar polish"
```

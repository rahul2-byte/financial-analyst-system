# Design Spec: Frontend Visual & UX Polish (Phase 2) - "The Living Report"

**Date:** 2026-03-20
**Topic:** Visual identity and user experience refinements for the FinAI Intelligence frontend.
**Status:** Draft

---

## 1. Vision: "The Intelligence Terminal"

The platform will transition from a "chat application" to a **high-fidelity document engine**. The aesthetic is **Minimalist/Swiss**: precise, organized, and optimized for long-form reading and data analysis. It will feel like a professional analyst's report that "lives" and updates in real-time.

---

## 2. Design Foundations

### 2.1 Color Palette (OLED High-Contrast)
- **Background (Primary):** `#020617` (Tailwind Slate-950) for deep OLED black.
- **Background (Message):** `#0F172A` (Tailwind Slate-900) - used very sparingly.
- **Borders (Blueprint):** `rgba(255, 255, 255, 0.08)` for ultra-thin, "blueprint" style lines. Use `divide-y divide-white/10` for table row separators to ensure consistent thinness.
- **Accents:** 
  - Emerald-500 (`#10B981`) for positive growth, "Buy" indicators, and the primary "Analyze" action.
  - Slate-400 (`#94A3B8`) for body text and descriptive metadata.
  - Slate-100 (`#F1F5F9`) for primary headings and important data points.

### 2.2 Typography (Technical & Legible)
- **Primary Font:** `IBM Plex Sans` (via Google Fonts).
- **Mood:** Professional, institutional, technical.
- **Scale:**
  - **H1:** 28px / 1.2 line-height (Medium weight `500`, Tight tracking `-0.02em`)
  - **Body:** 15px / 1.7 line-height (Optimal for long-form report reading)
  - **Data/Mono:** `JetBrains Mono` for code and raw numerical values.

---

## 3. UI Components & Layout

### 3.1 The "Living Report" Layout
- **Reading Constraint:** Main content will be centered and constrained to a `max-w-3xl` (approx. 768px).
- **Asymmetric Grid:** User messages will be right-aligned but within the same central column, keeping the visual flow centered on the data.
- **Fixed Swiss Header:** A slim (56px) header with `backdrop-blur-xl` and a 1px bottom border. Includes a "LIVE ANALYSIS" pulse indicator.

### 3.2 Component Refinements
- **"Caged" Tables:** 
  - No alternating row colors.
  - Ultra-thin `0.5px` borders between rows and columns.
  - High-contrast headers (`Slate-100`) with uppercase, tracking-widest text.
- **Assistant Responses:** 
  - No bubble container.
  - Responses look like a page from a report.
  - No avatars inside the reading flow; identity is established via the fixed header.
- **Chat Input (Fixed Bar):**
  - Minimalist floating bar at the bottom.
  - Use `glassmorphism` effect (`bg-white/5` with `backdrop-blur`).
  - Subtle Emerald glow when focused.

---

## 4. Interaction & Motion

### 4.1 Entry Animations
- **Staggered Block Entry:** When a new report block (Text -> Table -> Chart) appears, it uses a 10px vertical slide and 150ms fade-in.
- **Spring Physics:** Stiffness: 400, Damping: 30 (Quick, firm, no "bounce").

### 4.2 Feedback Loops
- **The "Pulse":** The emerald "LIVE ANALYSIS" indicator pulses slowly (2s duration) when data is active.
- **Active State Shimmer:** While the AI is "Thinking," placeholders for tables and charts use a subtle `white/2` shimmer effect.

---

## 5. Implementation Plan (High-Level)

1. **Theme Update:** Integrate `IBM Plex Sans` and OLED colors in `globals.css` and `tailwind.config.ts`.
2. **Layout Refactor:** Center the chat window and apply the `max-w-3xl` constraint.
3. **Component Re-styling:** 
   - Refactor `MessageItem` to remove the assistant "bubble" and avatar.
   - Update `MarkdownRenderer` table styles.
4. **Header/Input Refine:** Apply glassmorphism and thin borders to the sticky elements.
5. **Animation Pass:** Add Framer Motion staggered transitions to message blocks.

---

## 6. Testing & Compliance

- **Legibility Check:** Ensure body text contrast is at least 7:1 against OLED black.
- **Responsiveness:** Verify the `max-w-3xl` constraint breaks gracefully on mobile devices.
- **A11y:** Ensure the pulse animation respects `prefers-reduced-motion`.

# Aurora Vision Agent — UI/UX Design Audit & Specification

> Comprehensive audit of the current desktop shell UI with target design specification.
> Scope: `desktop/src/main.tsx` (1002 lines) + `desktop/src/styles.css` (317 lines)
> Backend: FastAPI at `http://127.0.0.1:8765` with WebSocket at `/ws/state`
> Stack: Tauri 2.x + React 18.3 + TypeScript 5.5 + Vite 5.4 + Lucide icons

---

## Part 1: Current State Audit

### 1.1 Architecture Problems

| Problem | Severity | Detail |
|---------|----------|--------|
| **Monolithic single file** | Critical | All 10 pages, 15+ components, all state in one `main.tsx`. Impossible to maintain or test in isolation. |
| **No component library** | High | Every button, card, select built from scratch. Inconsistent padding (8px, 10px, 12px, 14px, 18px, 22px), border-radius (8px, 14px, 999px), and font sizes. |
| **No design tokens** | High | Colors hardcoded as `rgba(...)` literals in 50+ places. Changing the accent color requires editing 30+ CSS rules. |
| **No state management** | Medium | `useState` for everything. WebSocket reconnection, error boundaries, loading states all missing. |
| **No routing** | Medium | Page switching via `useState<Page>`. No URL sync, no browser back/forward, no deep links. |

### 1.2 Visual Design Problems

#### Color System (Current)

The current palette has **no design tokens**. Raw values scattered across both files:

```
Background:     #0c1020, #151a32, #101827, rgba(8,12,28,0.92), rgba(8,12,28,0.82)
Card BG:        rgba(17, 24, 48, 0.72), rgba(255,255,255,0.06), rgba(255,255,255,0.07), rgba(255,255,255,0.08)
Border:         rgba(255,255,255,0.09), rgba(255,255,255,0.12), rgba(255,255,255,0.13), rgba(255,255,255,0.14)
Text primary:   #f8fbff, white, #eff6ff, #edf6ff
Text secondary: #9fb4d8, #b9c9e9, #c8d7f3, #d8e6ff, #dce9ff, #dfeaff
Accent cyan:    #48e7ff, #4be7ff, #7ff0c3, #80f7c4
Accent pink:    #ff63cf, #ff66d1
Success:        #7ff0c3, #80f7c4
Warning:        #ffe082, #ff9bac
Error:          #ff8fa3, #ff5c7a, rgba(255, 69, 106, ...)
```

**Problems:**
- 6 different "secondary text" colors that are nearly identical (#9fb4d8, #b9c9e9, #c8d7f3, etc.)
- Cards blend into background — `rgba(17, 24, 48, 0.72)` on `#151a32` is almost invisible
- Accent gradient (cyan → pink) is attractive but overused — every hero element uses it

#### Typography (Current)

```
Font:    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
h1:      30px, no weight specified (inherited 400)
h2:      22px, no weight specified
Metric:  22px strong, 20px strong, 18px strong
Body:    inherited (16px default)
Small:   13px, 12px
```

**Problems:**
- h1/h2 have no font-weight — they look identical to regular text except size
- No line-height system (1.45, 1.55 used inconsistently)
- Metric values jump between 18px, 20px, 22px for no apparent reason

#### Spacing (Current)

```
Sidebar:   24px padding
Main:      28px padding
Cards:     18px padding (some 22px, some 12px)
Grid gaps: 8px, 10px, 12px, 14px, 16px, 26px
```

**Problem:** No spacing scale. 6 different gap values with no semantic meaning.

### 1.3 Page-by-Page Analysis

#### Dashboard (main page)

```
Current layout:
┌─────────────────────────────────────────────┐
│ [Avatar Ring]  Dry-run default              │
│                INIT                         │  ← heroPanel
│                No active skill              │
├──────────────┬──────────────────────────────┤
│ Start│Pause  │ Resume│Stop                  │  ← commandPanel #1
│      │Emergency Stop                        │
├──────────────┴──────────────────────────────┤
│ Start Local│Run Diag│Calibration│Skill Lib  │  ← commandPanel #2
│ [raw JSON diagnostics output]               │
├──────┬───────┬──────┬───────┤               │
│Focus │Input  │Tele- │Runtime│               │  ← 4 identical StatusCards
│  OK  │Release│metry │Health │               │
└──────┴───────┴──────┴───────┘               │
```

**Issues:**
1. Two command panels with duplicate "Start" button is confusing
2. Avatar ring + node name takes up 230px height but shows minimal info
3. Status cards are 4 identical small boxes — no visual distinction
4. Raw JSON diagnostics dump breaks the layout
5. No "at a glance" summary — user must scan 6+ elements to understand system state

#### Run Monitor

```
Current layout:
┌────────┬────────┬────────┬────────┐
│Progress│Frustr. │Target  │Interrupt│  ← 4 Metric boxes in a row
│  0%    │  0.0   │ NONE   │  None   │
├────────┴────────┴────────┴────────┤
│ Event Stream                      │
│ 12:00:00 STOPPED INIT NONE       │  ← plain text lines
│ 12:00:01 STOPPED INIT NONE       │
└───────────────────────────────────┘
```

**Issues:**
1. Progress 0% / Frustration 0.0 / Target NONE / Interrupt None — all zero-state with no visual differentiation
2. Event stream is plain monochrome text — no color coding by severity, no timestamps with millisecond precision
3. No charts — no progress trend, no frustration graph over time
4. Entire page is just 2 panels with minimal data

#### Reports

```
Current layout:
┌────────────────────────────────────────┐
│ Report Reader        [Kernel][Product] │
│ Latest Run              [Showcase]     │
├────────────────────────────────────────┤
│ {                                     │
│   "run_id": "2024...",               │  ← raw JSON in <pre>
│   "stages": [...]                    │
│ }                                     │
└────────────────────────────────────────┘
```

**Issues:**
1. Entire report is raw JSON — should be rendered markdown with syntax highlighting
2. No report list/history — can only see "latest"
3. No search, filter, or export functionality

#### Settings

```
Current layout:
┌──────────┬──────────┐
│Input Bknd│Real Input│
│ console  │Disabled  │
├──────────┼──────────┤
│Safe Windw│F9 Stop   │
│ Required │ Enabled  │
└──────────┴──────────┘
```

**Issues:**
1. Settings page is just 4 static status cards — no actual configuration
2. No config file editing, no preference toggles, no profile management
3. Page feels like a placeholder (it is)

#### Calibration Wizard

```
Current layout:
┌──────────────────────────────────────────────┐
│ First-run setup                              │
│ Calibration Wizard                           │
│ [message text]                               │
│ ████████████░░░░░░░░░░░░  (progress bar)     │
├────┬────┬────┬────┬────┬────┤                │
│ S1 │ S2 │ S3 │ S4 │ S5 │ S6 │  ← step tabs  │
├──────────────────────────────────────────────┤
│ [Step content — varies by step]              │
│                                              │
│                          [Back] [Next]       │
└──────────────────────────────────────────────┘
```

**Issues:**
1. Most polished page, but still basic
2. Step 2 (window selection): window list has no icons, no visual hierarchy
3. Step 3 (ROI drawing): no undo, no resize handles, no delete individual ROI
4. Step 4 (model check): raw JSON output for benchmark
5. Progress bar animation works but has no step labels

#### Skill Library

```
Current layout:
┌──────────┬──────────────────┬──────────┐
│Start Rec │ Timeline/Step Tr │Properties│
│Capture Ev│                  │ Validate │
│ Marker   │  [raw JSON]      │ Dry-run  │
│Stop Rec  │                  │ Replay   │
│Save Draft│                  │ [log]    │
│Save Demo │                  │          │
│──────────│                  │          │
│ skill 1  │                  │          │
│ skill 2  │                  │          │
└──────────┴──────────────────┴──────────┘
```

**Issues:**
1. No visual timeline — just raw JSON dump
2. No step tree visualization — should show connected nodes
3. No drag-and-drop reordering
4. Properties panel shows raw log text
5. Skill list has no thumbnails, no category grouping

#### Task Planner

```
Current layout:
┌────────────────────┬────────────────────┐
│ Natural Lang Goal  │ Sandbox Validation │
│ [textarea]         │ [raw JSON plan]    │
│ [provider] [person]│                    │
│ [Generate] [Explain├────────────────────┤
│ Failure]           │ Failure Explanation│
│                    │ [raw JSON failure] │
└────────────────────┴────────────────────┘
```

**Issues:**
1. All output is raw JSON — plan, validation, failure explanation
2. No visual task graph — should show DAG of planned steps
3. No streaming — user clicks and waits for full response
4. Provider/persona selectors are raw `<select>` elements with no styling

#### Companion

```
Current layout:
┌──────────┬──────────────────────────────────┐
│   [A]    │ 观察中                           │
│  (big    │ Aurora Companion                  │
│  circle) │ [normal modePill]                │
│          │ "我会把底层事件翻译成..."         │
│          │ [persona select]                  │
│          │ [event code select]               │
│          │ [Trigger] [Why Failed?]           │
│          │ [raw JSON failure output]         │
│          │                                   │
│          │ [Emergency Stop]                  │
└──────────┴──────────────────────────────────┘
```

**Issues:**
1. **Biggest missed opportunity** — this is supposed to be the star feature
2. Avatar is a single letter "A" in a gradient circle — no character art
3. No animation on emotion changes — static modePill
4. No chat history — only shows last triggered message
5. Bubble has no chat-like feel — just a form with selects and buttons
6. Emergency stop button at bottom feels orphaned
7. No voice/TTS indicator
8. No personality expression in the UI itself

#### Combat

```
Current layout:
┌──────────────────┬──────────────────┐
│ Combat Playbook  │ Reflex Evasion   │
│ [Graph][JSON]    │ [Trigger Danger] │
│ [Generate]       │ [Run Showcase]   │
│                  │ ████████░░ (meter│
│ [node grid or    │ DangerScore: 0.00│
│  raw JSON]       │ Current: ...     │
│                  │ Dodge: idle      │
│                  │ Cooldown: 0 ms   │
│                  │ [companion msg]  │
│                  │ [raw JSON danger] │
│                  │ [raw JSON show]  │
├──────────────────┴──────────────────┤
│ Reflex History                      │
│ 12:00:00 | score=0.00 | level=...  │
└─────────────────────────────────────┘
```

**Issues:**
1. Playbook node grid is 2xN flat cards — no graph visualization, no connections
2. Danger meter is just a thin bar — no dramatic visual impact
3. All data output is raw JSON again
4. History is plain text with no visual timeline
5. Combat graph/JSON toggle is a nice idea but both views are ugly

#### Product Demo (Checklist)

```
Current layout:
┌────────────────────┬────────────────────┐
│ Product Demo Check │ Run Result         │
│ ┌────────────────┐ │ [raw JSON or log]  │
│ │ OK · Health    │ │                    │
│ ├────────────────┤ │                    │
│ │ OK · Calibratn │ │                    │
│ ├────────────────┤ │                    │
│ │ OK · Skill Val │ │                    │
│ ├────────────────┤ │                    │
│ │WAIT· LLM Mock │ │                    │
│ └────────────────┘ │                    │
│ [Run E2E][Refresh] │                    │
│ [Latest Report]    │                    │
└────────────────────┴────────────────────┘
```

**Issues:**
1. Checklist items are text-only — no progress bar, no visual satisfaction
2. Pass/fail is just green/red border color
3. Run result is raw JSON
4. No animated run progress — just "Running dry-run E2E..." text

### 1.4 Interaction Problems

| Problem | Detail |
|---------|--------|
| **No loading states** | API calls show no spinner or skeleton. User sees stale data or empty states until response arrives. |
| **No error states** | `fetch(...).catch(() => undefined)` silently swallows errors. User never knows if the backend is down. |
| **No transitions** | Page switches are instant — no fade, no slide. Content appears/disappears abruptly. |
| **No hover feedback** | Only `.nav` buttons have hover state. Cards, commands, selects have no hover/focus/active states. |
| **No keyboard shortcuts** | No hotkeys for common actions (start/stop/emergency). |
| **No toasts/notifications** | Backend messages appear inline as text. No floating notification system. |
| **Sidebar has no collapse** | Fixed 260px sidebar on all screen sizes. |
| **Raw `<select>` elements** | Browser default dropdowns with custom background — ugly and inconsistent across browsers. |

---

## Part 2: Target Design System

### 2.1 Design Tokens

```
// Color primitives
--cyan-400:       #48e7ff
--cyan-500:       #22d3ee
--cyan-600:       #06b6d4
--pink-400:       #ff63cf
--pink-500:       #ec4899
--green-400:      #7ff0c3
--green-500:      #34d399
--yellow-400:     #ffe082
--yellow-500:     #fbbf24
--red-400:        #ff8fa3
--red-500:        #f87171

// Semantic colors
--bg-base:        #0c1020
--bg-surface:     rgba(17, 24, 48, 0.85)     // cards — 0.85 instead of 0.72 for more contrast
--bg-elevated:    rgba(25, 34, 62, 0.92)     // modals, dropdowns
--bg-hover:       rgba(93, 212, 255, 0.08)   // hover overlay
--bg-active:      rgba(93, 212, 255, 0.15)   // active/selected overlay

--border-default: rgba(255, 255, 255, 0.10)
--border-subtle:  rgba(255, 255, 255, 0.06)
--border-strong:  rgba(255, 255, 255, 0.18)

--text-primary:   #f0f6ff                      // single value instead of 6 near-identicals
--text-secondary: #8b9fc0                      // single value instead of 6 near-identicals
--text-muted:     #5a6f8f

--accent-primary: var(--cyan-400)              // main accent
--accent-gradient: linear-gradient(135deg, var(--cyan-400), var(--pink-400))

// Status
--status-ok:      var(--green-400)
--status-warn:    var(--yellow-400)
--status-error:   var(--red-400)
--status-running: var(--cyan-400)

// Spacing scale (4px base)
--sp-1: 4px
--sp-2: 8px
--sp-3: 12px
--sp-4: 16px
--sp-5: 20px
--sp-6: 24px
--sp-8: 32px
--sp-10: 40px
--sp-12: 48px

// Typography
--font-sans: 'Inter', system-ui, -apple-system, sans-serif
--font-mono: 'JetBrains Mono', 'Fira Code', monospace

--text-xs:   12px / 16px   (size / line-height)
--text-sm:   13px / 18px
--text-base: 14px / 20px   ← reduce from 16px for denser information
--text-lg:   18px / 24px
--text-xl:   22px / 28px
--text-2xl:  28px / 34px
--text-3xl:  36px / 42px

--weight-normal: 400
--weight-medium: 500
--weight-semibold: 600
--weight-bold: 700
--weight-black: 800

// Radius
--radius-sm: 6px
--radius-md: 8px
--radius-lg: 12px
--radius-xl: 16px
--radius-full: 9999px

// Shadows
--shadow-sm:   0 2px 8px rgba(0, 0, 0, 0.15)
--shadow-md:   0 4px 16px rgba(0, 0, 0, 0.2)
--shadow-lg:   0 8px 32px rgba(0, 0, 0, 0.3)
--shadow-glow: 0 0 20px rgba(72, 231, 255, 0.15)  // accent glow

// Transitions
--ease-out:    cubic-bezier(0.16, 1, 0.3, 1)
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1)
--duration-fast:   120ms
--duration-normal: 200ms
--duration-slow:   350ms
```

### 2.2 Component Inventory

Below is what should exist vs what exists today.

#### Buttons

**Current:** One `.cmd` class used everywhere. No size variants. No icon-only variant.

**Target:**

```
Button variants:
  primary   — accent gradient bg, dark text, glow shadow
  secondary — transparent bg, border, white text
  danger    — red bg, white text, pulse animation
  ghost     — no bg, no border, text only

Button sizes:
  sm  — 28px height, text-sm
  md  — 36px height, text-base
  lg  — 44px height, text-lg

Button states:
  default → hover (bg brighten) → active (scale 0.97) → disabled (opacity 0.4)
  loading — spinner replaces content
```

#### Cards / Panels

**Current:** One style for everything. `.heroPanel`, `.commandPanel`, `.statusCard`, `.eventStream`, `.reportPanel`, `.settingsPanel`, `.placeholder`, `.metricPanel` — all same border/bg.

**Target:**

```
Panel variants:
  surface   — default card: surface bg, subtle border, shadow-sm
  elevated  — modal/dropdown: elevated bg, stronger border, shadow-md
  outlined  — no bg fill, just border (for grouping)
  inset     — slightly darker bg (for code blocks, nested sections)

Panel sections:
  header    — title + eyebrow + optional actions
  body      — main content
  footer    — actions row
```

#### Status Indicators

**Current:** `.ok` / `.warn` classes that just change text color.

**Target:**

```
StatusDot:
  size: 8px circle
  colors: ok (green), warn (yellow), error (red), neutral (gray)
  animation: pulse on "running" state

StatusBadge:
  dot + label text
  variants: ok, warn, error, running, unknown

StatusCard (enhanced):
  icon (16px) + label + value + trend indicator (↑↓→)
  optional: mini sparkline
```

#### Input Elements

**Current:** Raw `<select>` and `<textarea>` with custom background only.

**Target:**

```
Select:
  Custom dropdown with consistent styling
  Chevron icon, hover highlight, focus ring

TextArea:
  Monospace font option for code/json
  Character count
  Auto-resize option

Input (text):
  Focus ring with accent color
  Label + placeholder pattern
  Validation states (ok/error)
```

#### Data Display

**Current:** Only `<pre>{JSON.stringify(...)}</pre>`.

**Target:**

```
JsonView:
  Collapsible tree with syntax highlighting
  Copy button
  Key-value pairs with color-coded types

DataGrid:
  Sortable columns
  Row highlighting
  Empty state illustration

Metric:
  Icon + label + large value
  Optional trend arrow + delta
  Optional mini chart (sparkline)

ProgressBar:
  Animated fill
  Label overlay
  Color transitions based on value (green → yellow → red)

Timeline:
  Vertical timeline for events
  Color-coded dots by severity
  Relative timestamps ("2s ago")
```

#### Layout Components

```
Sidebar:
  Collapsible (icon-only mode at 56px)
  Active item indicator (accent bar on left edge)
  Section dividers
  Bottom section (settings, profile)

PageHeader:
  Breadcrumb (optional)
  Title + subtitle
  Actions row (aligned right)

EmptyState:
  Illustration (SVG)
  Title + description
  Primary action button
```

### 2.3 Page Redesigns

#### Dashboard — Redesigned

```
┌─────────────────────────────────────────────────────────┐
│  ┌─────────────────────────────────────────────────────┐│
│  │  ● Connected           STOPPED                      ││  ← status bar
│  │  Agent is idle. All systems nominal.                ││
│  └─────────────────────────────────────────────────────┘│
│                                                         │
│  ┌──────────────────────┐  ┌──────────────────────────┐│
│  │ ▶ Start               │  │ System Health            ││
│  │    Begin dry-run task │  │ ● Focus: Dry-run mode    ││
│  ├──────────────────────┤  │ ● Input: Released        ││
│  │ ⏸ Pause   ↻ Resume   │  │ ● Telemetry: Streaming   ││
│  │ ■ Stop               │  │ ● Runtime: Healthy       ││
│  ├──────────────────────┤  └──────────────────────────┘│
│  │ ⚠ Emergency Stop     │                             │
│  └──────────────────────┘                             │
│                                                         │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐          │
│  │Open    │ │Open    │ │Run     │ │View    │          │  ← quick actions
│  │Calibrat│ │Skills  │ │Diagno. │ │Reports │          │
│  └────────┘ └────────┘ └────────┘ └────────┘          │
└─────────────────────────────────────────────────────────┘
```

Key changes:
- **Status bar** at top replaces scattered StatusCards — one glanceable bar
- **Command buttons** grouped in a single card, not two panels
- **Health indicators** as a compact list with dots, not separate cards
- **Quick actions** as compact icon buttons, not full command buttons
- **No raw JSON** — diagnostics get their own structured view

#### Run Monitor — Redesigned

```
┌─────────────────────────────────────────────────────────┐
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Progress │ │Frustratn │ │  Target  │ │Interrupt │  │
│  │          │ │          │ │          │ │          │  │
│  │   67%    │ │   0.3    │ │ TRACKED  │ │   None   │  │
│  │  ▲ +12%  │ │  ▼ -0.1  │ │          │ │          │  │  ← trend arrows
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                         │
│  ┌─────────────────────┐  ┌───────────────────────────┐│
│  │ Progress Trend       │  │ Frustration Trend         ││
│  │ ╱╲  ╱──╲            │  │     ╱╲                    ││  ← sparklines
│  │╱  ╲╱    ╲──╲         │  │    ╱  ╲──╲               ││
│  └─────────────────────┘  └───────────────────────────┘│
│                                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Event Stream                               [Clear]  ││
│  │ 12:00:03.142  ● RUNNING   skill_execution  TRACKED  ││  ← colored by type
│  │ 12:00:03.098  ● RUNNING   skill_execution  TRACKED  ││
│  │ 12:00:02.901  ○ PAUSED    wait_visual     NONE     ││  ← ○ = dimmer
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

Key changes:
- **Sparkline charts** for progress and frustration trends
- **Trend arrows** on metrics (▲ +12% or ▼ -0.1)
- **Event stream** with color-coded severity dots and ms-precision timestamps
- **Clear button** for event stream

#### Companion — Redesigned (Most Important)

This is the hero feature. It needs to feel alive.

```
┌─────────────────────────────────────────────────────────┐
│  ┌─────────────────────────────────────────────────────┐│
│  │                                                     ││
│  │              ╭─────────────────╮                    ││
│  │              │                 │                    ││
│  │              │    [Avatar]     │                    ││  ← character art area
│  │              │   (animated)    │                    ││     (not just "A")
│  │              │                 │                    ││
│  │              ╰─────────────────╯                    ││
│  │                   ·  ·  ·                          ││  ← thinking dots anim
│  │                                                     ││
│  │  ┌───────────────────────────────────────────────┐  ││
│  │  │  哎呀，目标跑到哪里去了？                        │  ││  ← chat bubble
│  │  │  让我重新找找看...                             │  ││     (typed-in animation)
│  │  └───────────────────────────────────────────────┘  ││
│  │                                                     ││
│  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐           ││
│  │  │ 😊   │  │ 🤔   │  │ 😰   │  │ ⚠️   │           ││  ← emotion indicator
│  │  │normal│  │think │  │nervus│  │warn  │           ││
│  │  └──────┘  └──────┘  └──────┘  └──────┘           ││
│  │                                                     ││
│  │  Persona: [Aurora ▾]   Event: [TARGET_LOST ▾]      ││
│  │  [Trigger Event]  [Why Failed?]                     ││
│  │                                                     ││
│  │  ┌───────────────────────────────────────────────┐  ││
│  │  │  12:03 TARGET_LOST   "目标消失了..."           │  ││  ← event history
│  │  │  12:01 TASK_COMPLETE  "太好了！任务完成！"     │  ││
│  │  │  12:00 DODGE_REFLEX   "危险！紧急闪避！"       │  ││
│  │  └───────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────┘│
│                                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │  ⚠ EMERGENCY STOP                                   ││  ← always visible
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

Key changes:
- **Character avatar** takes center stage — use a stylized SVG illustration, not just a letter
- **Chat bubble** with typing animation — text appears character by character
- **Emotion indicators** as visual cards with face/icon, not just a text pill
- **Event history** — scrollable log of companion messages with timestamps
- **Emergency stop** always visible at bottom — full-width danger button
- **Typing indicator** (···) when waiting for response

#### Combat — Redesigned

```
┌─────────────────────────────────────────────────────────┐
│  ┌───────────────────────┐  ┌──────────────────────────┐│
│  │ Combat Playbook        │  │ Danger Assessment        ││
│  │                        │  │                          ││
│  │   ┌─────────┐         │  │  ████████████░░░░  72%   ││  ← danger meter
│  │   │maintain │────────┐│  │                          ││     bigger & dramatic
│  │   │  lock   │        ││  │  Score: 0.72  HIGH       ││
│  │   └─────────┘        ││  │  Node: dodge_if_danger   ││
│  │         │             ││  │  Dodge: ● Ready          ││
│  │         ▼             ││  │  Cooldown: 450ms         ││
│  │   ┌─────────┐         ││  │                          ││
│  │   │ attack  │         ││  │  "检测到危险！准备闪避！"  ││  ← companion line
│  │   └─────────┘         ││  │                          ││
│  │         │             ││  │  [Trigger Danger Signal]  ││
│  │         ▼             ││  │  [Run Showcase Demo]     ││
│  │   ┌─────────┐         ││  └──────────────────────────┘│
│  │   │ dodge   │         ││                             │
│  │   └─────────┘         ││                             │
│  │                        ││                             │
│  └───────────────────────┘│                             │
│                            │                             │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Reflex History                                       ││
│  │  ● 12:03:21  score=0.72  HIGH  dodged ✓             ││  ← colored timeline
│  │  ● 12:03:18  score=0.31  LOW   ignored              ││
│  │  ○ 12:03:10  score=0.00  —     idle                 ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

Key changes:
- **Graph visualization** — actual connected nodes with arrows, not flat cards
- **Danger meter** — larger, more dramatic with percentage label
- **Companion line** — integrated combat commentary
- **History** — color-coded by severity level with success/failure markers

### 2.4 Animation & Interaction Spec

#### Page Transitions
```
Enter: opacity 0 → 1, translateY(8px) → 0, 200ms ease-out
Exit:  opacity 1 → 0, translateY(0) → -4px, 120ms ease-out
```

#### Card Hover
```
Default: transform none, shadow-sm
Hover:   transform translateY(-2px), shadow-md, border-color brighten
Active:  transform scale(0.98)
Transition: 200ms ease-out
```

#### Button Hover
```
Primary:   glow shadow increases, slight scale(1.02)
Secondary: border-color brightens, bg subtle fill
Danger:    bg color pulses (subtle animation)
```

#### Status Changes
```
ok → warn:  flash yellow once, then settle
warn → error: flash red, shake 4px horizontal
error → ok:  green pulse ripple from center
```

#### Event Stream
```
New event: slide in from left, opacity 0→1, 150ms ease-out
Old events: fade slightly (opacity 0.6) after 10s
```

#### Companion Bubble
```
New message: typing indicator (···) for 500ms, then text types in at 30ms/char
Emotion change: avatar glow color transitions, background subtle shift
```

#### Loading States
```
Skeleton: gray rectangles with shimmer animation (linear-gradient sweep)
Spinner: accent-colored circle, 800ms rotation
Progress: smooth width transition, never jump
```

### 2.5 Sidebar Redesign

```
Current:                    Target:
┌──────────────┐           ┌──────────────────────────────┐
│ [A] Aurora   │           │ [✦] Aurora                   │  ← logo mark
│   Agent      │           │     Agent                    │
│   Vision     │           │     Vision Kernel             │
│              │           │                              │
│ Dashboard    │           │ ── Monitor ──────────────────│  ← section headers
│ Run Monitor  │           │ ● Dashboard                  │
│ Reports      │           │   Run Monitor                │  ← indent hierarchy
│ Settings     │           │   Reports                    │
│              │           │                              │
│ Calibration  │           │ ── Configure ────────────────│
│ Skill Library│           │   Calibration                │
│ Task Planner │           │   Skill Library              │
│              │           │   Task Planner               │
│ Companion    │           │                              │
│ Combat       │           │ ── Intelligence ─────────────│
│ Product Demo │           │   Companion          ♥      │  ← emotion indicator
│              │           │   Combat                     │
│              │           │                              │
│              │           │ ── System ───────────────────│
│              │           │   Settings                   │
│              │           │   Product Demo               │
│              │           │                              │
│              │           │           ● Connected   ▾    │  ← connection status
└──────────────┘           └──────────────────────────────┘
```

Key changes:
- **Section headers** group related pages
- **Active indicator** is a left-edge accent bar (3px wide), not bg color change
- **Connection status** in sidebar footer
- **Companion emotion** shown inline (♥ = happy, ! = warning, etc.)
- **Collapsible** to icon-only mode (56px) via toggle at bottom

### 2.6 JSON Display Replacement Strategy

Every `<pre>{JSON.stringify(...)}</pre>` should be replaced with structured display:

| Context | Current | Target |
|---------|---------|--------|
| Diagnostics output | Raw JSON | Structured status grid with icons |
| Skill draft/timeline | Raw JSON | Visual step tree with connected nodes |
| Task plan | Raw JSON | DAG visualization with node cards |
| Failure explanation | Raw JSON | Formatted card: icon + title + structured details |
| Benchmark results | Raw JSON | Metric cards with delta indicators |
| Combat playbook | Raw JSON or flat node grid | Connected graph with arrows |
| Danger signal | Raw JSON | Danger meter + structured status |
| Product E2E result | Raw JSON | Checklist with progress bar + pass/fail |
| Showcase run | Raw JSON | Timeline + metric summary |

### 2.7 Responsive Behavior

```
>= 1440px: Full layout, sidebar expanded (260px)
1200-1439px: Sidebar collapsed (56px icons only), main content full
900-1199px: Sidebar collapsed, grids collapse to single column
< 900px: Sidebar hidden, hamburger menu, stacked layout
```

### 2.8 Accessibility Requirements

- All interactive elements focusable with keyboard
- Focus ring: 2px solid var(--accent-primary) offset 2px
- Color contrast: WCAG AA minimum (4.5:1 for text, 3:1 for large text)
- Status indicators: not color-only — always include icon or text label
- Emergency stop: always visible, always keyboard accessible (Escape key)
- Reduced motion: respect `prefers-reduced-motion`

---

## Part 3: Implementation Priority

### Phase A: Foundation (Highest Impact)

1. **Design tokens** — Extract all hardcoded colors/spacing into CSS custom properties
2. **Component library** — Build Button, Card, StatusBadge, Select, Input as reusable components
3. **File structure** — Split `main.tsx` into page components, shared components

### Phase B: Core Pages

4. **Dashboard** — Status bar + command card + health list
5. **Run Monitor** — Metric cards with trends + sparklines + colored event stream
6. **Sidebar** — Sections, active indicator, collapsible

### Phase C: Feature Pages

7. **Companion** — Character art, chat bubble with typing animation, emotion cards, event history
8. **Combat** — Graph visualization, enhanced danger meter, companion integration
9. **Skill Library** — Visual timeline/step tree, structured properties panel

### Phase D: Polish

10. **Reports** — Markdown renderer with syntax highlighting
11. **Task Planner** — DAG visualization, streaming output
12. **Product Demo** — Animated checklist with progress bar
13. **Animations** — Page transitions, card hover, status changes
14. **Settings** — Actual configuration toggles

---

## Part 4: File Structure Recommendation

```
desktop/src/
  main.tsx                    ← App shell only (routing, WebSocket, layout)
  styles/
    tokens.css                ← design tokens (colors, spacing, typography)
    base.css                  ← reset, body, scrollbar
    components.css            ← button, card, badge, input styles
    pages.css                 ← page-specific layouts
  components/
    Button.tsx                ← primary/secondary/danger/ghost variants
    Card.tsx                  ← surface/elevated/outlined/inset
    StatusBadge.tsx           ← dot + label + color
    Metric.tsx                ← icon + label + value + trend
    Select.tsx                ← custom dropdown
    JsonView.tsx              ← collapsible JSON tree
    SparkLine.tsx             ← mini SVG chart
    Toast.tsx                 ← notification system
    EmptyState.tsx            ← illustration + message + action
    Sidebar.tsx               ← navigation with sections
    PageHeader.tsx            ← breadcrumb + title + actions
  pages/
    Dashboard.tsx
    RunMonitor.tsx
    Reports.tsx
    Settings.tsx
    Calibration.tsx
    SkillLibrary.tsx
    TaskPlanner.tsx
    Companion.tsx
    Combat.tsx
    ProductDemo.tsx
```

---

## Appendix A: Backend API Data Shapes

Every UI component must be designed against these actual response structures.

### A.1 WebSocket State Push (`/ws/state`, 5Hz)

```typescript
interface AgentState {
  mode: "STOPPED" | "RUNNING" | "PAUSED" | "EMERGENCY_STOPPED";
  current_node: string;                    // e.g. "INIT", "skill_execution"
  current_skill: string | null;            // e.g. "gui_demo_skill"
  target_state: string;                    // e.g. "TRACKED", "NONE", "LOST"
  progress: number;                        // 0.0 to 1.0
  frustration: number;                     // 0.0 to 1.0+
  input_backend: string;                   // "console" (dry-run) or "safe-window"
  focus_status: string;                    // "DRY_RUN" | "FOCUSED" | "UNFOCUSED"
  active_interrupt: {
    priority: number;                      // 0=P0, 10=P1, 20=P2, etc.
    timestamp: number;
    code: string;                          // e.g. "DODGE_REFLEX"
    source: string;
    requires_input_release: boolean;
    payload?: Record<string, unknown>;
  } | null;
  runtime_health: {
    healthy: boolean;
    input_worker_alive: boolean;
    telemetry_ok: boolean;
    release_all_called: boolean;
    updated_at: number;                    // epoch ms
  };
  input_released: boolean;
  telemetry_ok: boolean;
  latest_run_id: string | null;
  updated_at: number;                      // epoch ms
}
```

### A.2 Persona System

**GET /persona/profiles** returns:
```typescript
interface PersonaProfile {
  persona_id: string;                      // "default_companion", "cheerful_guide", etc.
  name: string;                            // "Aurora", "Mira", "Sera", "Nagi", "Dev Console"
  style: string;                           // "balanced", "cheerful", "calm", "healing", "developer"
  tone: string;                            // "warm", "bright", "precise", "soft", "technical"
  avatar_asset: string;                    // "assets/avatar/default_companion.png" (not yet created)
  voice_config: Record<string, unknown>;   // TTS settings (currently empty)
  event_templates: Record<string, string>; // event_code → message text
  safety_style: string;                    // "friendly_safe", "precise_safe", "gentle_safe", "technical_safe"
  technical_detail_level: string;          // "low", "medium", "high"
  emotion_map: Record<string, string>;     // event_code → emotion name
}
```

**POST /persona/event** returns:
```typescript
interface DialogueLine {
  persona_id: string;
  event_code: string;                      // "TARGET_LOST", "TASK_COMPLETE", etc.
  message: string;                         // Chinese text response
  overlay_state: string;                   // "观察中", "思考中", "执行中", "遇到问题", "暂停", "完成"
  emotion: string;                         // "normal", "thinking", "nervous", "happy", "warning"
}
```

**Emotion state machine:**
```
normal ←→ thinking ←→ nervous
  ↕           ↕           ↕
  └───────→ happy ←── warning
```

**Event code catalog (8 core + 12 extended):**

| Event | Emotion | Overlay | Template (Aurora) |
|-------|---------|---------|-------------------|
| TARGET_LOST | nervous | 遇到问题 | 目标跑出视野啦，我正在重新搜索。 |
| NO_TASK_PROGRESS | thinking | 思考中 | 这里好像被挡住了，我换个方向试试。 |
| RECOVERY_STARTED | thinking | 执行中 | 我先做一次恢复动作，再继续任务。 |
| SKILL_TIMEOUT | warning | 遇到问题 | 这个动作没有在预期时间内完成，我会先停下来检查。 |
| TASK_COMPLETE | happy | 完成 | 任务完成，已经整理好结果。 |
| FOCUS_LOST | warning | 暂停 | 目标窗口失焦了，我先暂停，避免误操作。 |
| EMERGENCY_STOP | warning | 暂停 | 紧急停止已触发，输入已释放。 |
| DODGE_REFLEX | nervous | 执行中 | 检测到危险，我先闪避一下。 |
| COMBAT_START | nervous | 执行中 | (extended events) |
| COMBAT_VICTORY | happy | 完成 | |
| DANGER_DODGE_SUCCESS | happy | 执行中 | |
| DANGER_HIT | warning | 遇到问题 | |
| COLLECTION_SUCCESS | happy | 完成 | |
| ARRIVED_AT_DESTINATION | happy | 完成 | |
| RESIN_FULL / STAMINA_FULL | happy | 完成 | |
| STAMINA_LOW | warning | 遇到问题 | |

### A.3 Combat System

**POST /combat/danger** returns:
```typescript
interface DangerEvaluation {
  danger_score: number;                    // 0.0 to 1.0
  level: "LOW" | "MEDIUM" | "HIGH";
  components: Record<string, number>;      // signal → weight, e.g. {"ground_danger_zone": 0.8}
  dominant_signal: string | null;          // e.g. "projectile_approaching"
  interrupt: {                             // null if danger_score < threshold
    priority: number;
    timestamp: number;
    code: string;                          // "DODGE_REFLEX"
    source: string;
    requires_input_release: boolean;
    payload: Record<string, unknown>;
  } | null;
  dodge: {                                 // null if not dodging
    dodge_type: string;                    // "iframe_dash"
    direction: string;                     // "left", "right", "back"
    duration_ms: number;
    window_start_ms: number;
    window_end_ms: number;
  } | null;
  dodge_policy: {
    cooldown_ms: number;
    max_dodges_per_minute: number;
    iframe_duration_ms: number;
  };
  companion_message: string | null;        // e.g. "检测到危险！准备闪避！"
}
```

**POST /combat/playbook** returns:
```typescript
interface CombatPlaybook {
  ok: boolean;
  playbook: {
    playbook_id: string;
    nodes: Array<{
      node_id: string;                     // "maintain_lock", "attack_if_safe", "dodge_if_danger"
      type: string;                        // "action", "decision", "reflex"
      priority: number;
      guards: string[];                    // preconditions
      transitions: string[];               // target node_ids
    }>;
    entry_node: string;
    validation: { ok: boolean; errors: string[] };
  };
  validation: { ok: boolean; errors: string[] };
}
```

### A.4 Skill System

**GET /skills** returns summary list. **GET /skills/{id}** returns full definition:
```typescript
interface SkillDefinition {
  skill_id: string;
  name: string;
  type: "ui" | "navigation" | "combat" | "recovery" | "verification";
  version: number;
  metadata: Record<string, unknown>;
  environment_profile: string;             // e.g. "default_1920x1080"
  preconditions: string[];                 // ["require_focus"]
  steps: Array<{
    step_id: string;
    type: string;                          // "wait_visual_trigger", "fallback_basic_loop", etc.
    label: string;
    delay_ms: number;
    timeout_ms: number;
    interruptible: boolean;
    params: Record<string, unknown>;
  }>;
  visual_triggers: Record<string, { type: string; [k: string]: unknown }>;
  success_criteria: string[];
  failure_policy: { max_retries: number; fallback: string };
  cleanup: Array<{ type: string }>;
  safety: {
    dry_run_default: boolean;
    interruptible: boolean;
    require_focus: boolean;
    max_duration_ms: number;
  };
  archived: boolean;
  updated_at: number | null;
}
```

**Recording session state:**
```typescript
interface RecordingSession {
  session_id: string;
  started_at: number;
  active_window_title: string;
  backend_name: string;                    // "mock", "test-window"
  focus_state: string;
  roi_profile: string;
  events: RecordedEvent[];
}
```

### A.5 Planner System

**POST /planner/task** returns:
```typescript
interface PlannerResult {
  ok: boolean;
  provider: string;                        // "mock", "glm", "minimax"
  task_spec: {                             // full TaskSpec object
    task_id: string;
    goal: string;
    steps: Array<{ skill_id: string; params: Record<string, unknown> }>;
    [k: string]: unknown;
  };
  skill_chain: string[];                   // ordered skill IDs
  risks: string[];                         // identified risks
  validation: {
    ok: boolean;
    simulation: boolean;
    errors: string[];
  };
  usage: Record<string, unknown>;          // token usage for LLM providers
  provider_error?: string;
}
```

**POST /planner/explain_failure** returns:
```typescript
interface FailureExplanation {
  user_friendly_summary: string;           // Chinese text explanation
  technical_summary: string;               // English technical details
  suggested_next_steps: string[];          // actionable recommendations
  possible_skill_patch: Record<string, unknown>; // suggested skill modifications
  provider?: string;
  provider_error?: string;
}
```

### A.6 Diagnostics

**POST /diagnostics/run** returns:
```typescript
interface DiagnosticsReport {
  ok: boolean;
  report_path: string;
  checks: Array<{
    key: string;                           // "python_version", "fastapi", "dxcam", etc.
    label: string;                         // "Python Version", "FastAPI Module"
    status: "ok" | "warn" | "fail";
    detail: string;                        // human-readable result
  }>;
}
```

Check items: python_version, node_npm, tauri_cli, fastapi, numpy, dxcam, mss, ultralytics, torch, model_yaml, calibration_profiles, skills_index, port_8765, logs_dir, desktop_build.

### A.7 Calibration System

**GET /calibration/profiles/{id}** returns:
```typescript
interface CalibrationProfile {
  profile_id: string;                      // "profile_1920x1080"
  window_title: string;
  source_resolution: [number, number];     // [1920, 1080]
  normalized_resolution: [number, number]; // [1280, 720]
  rois: Record<string, {
    mode: "relative" | "anchor";
    // relative mode:
    x?: number; y?: number; w?: number; h?: number;  // 0.0 to 1.0
    // anchor mode:
    anchor?: string;                       // "top-left", "top-right", etc.
    offset_x_px?: number | [number, number];
    offset_y_px?: number | [number, number];
    width_px?: number;
    height_px?: number;
  }>;
  created_at: string;
  display_mode: string;
  environment: string;
}
```

Standard ROI names: `main_view`, `target_area`, `minimap`, `skill_bar`, `status_area`, `dialog_area`, `interaction_prompt_area`.

### A.8 Showcase / Product E2E

**POST /showcase/run** returns:
```typescript
interface ShowcaseResult {
  ok: boolean;
  run_id: string | null;
  report_path: string | null;
  report_markdown: string | null;          // full markdown report
  stdout: string;
  stderr: string;
}
```

**POST /product/run_e2e** returns:
```typescript
interface ProductE2EResult {
  ok: boolean;
  run_id: string;
  run_dir: string;
  report_path: string;
  checklist: Array<{
    key: string;
    label: string;
    ok: boolean;
    detail: string;
  }>;
  selected_profile: string;
  selected_skill: string;
  planner_provider: string;
  task_validation: Record<string, unknown>;
  execution_mode: string;
  safety_events: string[];
  release_all_called: boolean;
  companion_summary: string;
  confirm_required?: boolean;              // true when safe-window needs confirmation
  error?: string;
}
```

### A.9 Model Status

**GET /models/status** returns:
```typescript
interface ModelStatus {
  detector_backend: string;                // "yolov8"
  model_path: string | null;
  model_exists: boolean;
  ultralytics_available: boolean;
  tracker: string;                         // "botsort"
  tracker_available: boolean;
  device: string;                          // "cuda" or "cpu"
  half: boolean;                           // FP16 mode
}
```

**POST /models/benchmark** returns:
```typescript
interface BenchmarkResult {
  ok: boolean;
  capture_fps: number;                     // e.g. 60.0
  detector_latency_ms: number | null;      // e.g. 15.2
  tracker_latency_ms: number | null;       // e.g. 2.1
  message: string;
}
```

---

## Appendix B: Persona Data Deep Dive

### B.1 Five Persona Profiles

| ID | Name | Style | Tone | Safety | Tech Level | Role |
|----|------|-------|------|--------|------------|------|
| default_companion | Aurora | balanced | warm | friendly_safe | medium | Default companion |
| cheerful_guide | Mira | cheerful | bright | friendly_safe | low | Upbeat guide |
| calm_operator | Sera | calm | precise | precise_safe | high | Technical operator |
| healing_partner | Nagi | healing | soft | gentle_safe | low | Gentle companion |
| developer_mode | Dev Console | developer | technical | technical_safe | high | Debug/development |

### B.2 Event Template Matrix

All 5 personas have unique Chinese-language templates for all 8 core events. The templates differ by:
- **Aurora**: balanced, warm — "目标跑出视野啦，我正在重新搜索。"
- **Mira**: cheerful, bright — "呀！目标不见了～让我找找看！"
- **Sera**: calm, precise — "目标丢失，已启动重新搜索流程。"
- **Nagi**: healing, soft — "目标不见了…不要担心，我会慢慢找到的。"
- **Dev Console**: technical — "TARGET_LOST: 视觉追踪丢失，启动重搜。"

### B.3 Extended Character Persona System

Beyond the 5 base personas, `persona/character_persona.py` supports game-specific character personas loaded from `knowledge/persona_characters.yaml`. These include:
- Rich personality profiles with speech patterns
- MBTI hints and personality traits
- Combat voices and emotional triggers
- World knowledge and lore depth
- LLM system prompts for dynamic responses

This system is used for Genshin/HSR in-game character companions but has no avatar assets yet.

### B.4 Voice/TTS Integration

Voice synthesis infrastructure exists but is not wired to the GUI:
- **Providers**: MiniMax, GLM (Zhipu), DashScope (Alibaba)
- **Output**: MP3, 24kHz
- **Controls**: speed, pitch, voice_id per persona
- **Current status**: text-only in GUI, no audio playback

**UI implication**: Companion page should include a speaker icon with mute/unmute toggle. Audio playback would use `AudioContext` or `<audio>` element. The infrastructure is ready; the GUI just needs a player widget.

---

## Appendix C: Missing Assets & Capabilities

### C.1 Assets That Don't Exist Yet

| Asset | Status | Needed For |
|-------|--------|------------|
| Avatar images (5 persona) | Not created | Companion page |
| App icon (.ico, .png) | Not created | Tauri window, taskbar |
| Favicon | Not created | Browser tab |
| Splash screen | Not created | App startup |
| Empty state illustrations | Not created | All pages |
| Logo SVG | Not created | Sidebar, title bar |

### C.2 Capabilities Missing from GUI

| Capability | Backend Status | GUI Status |
|------------|---------------|------------|
| Voice/TTS playback | Ready (MiniMax/GLM/DashScope) | Not wired |
| Skill version management | API exists (`/skills/{id}/versions`) | Not exposed |
| Skill archiving | API exists (`/skills/{id}/archive`) | Not exposed |
| Knowledge system | API exists (`/knowledge/resolve`, `/knowledge/routes`) | No page |
| Mission planning | API exists (`/mission/plan`) | Not exposed |
| Calibration profile listing | API exists (`/calibration/profiles`) | Not in wizard |
| Model loading | API exists (`/models/load`) | Not exposed |
| Error notifications | Backend returns errors | Silently swallowed |
| WebSocket reconnection | Backend supports | No reconnect logic |
| Keyboard shortcuts | Not implemented | Not implemented |
| Multi-window selection | Backend supports | Not exposed |
| Configuration editing | Config files exist | Settings page is placeholder |

### C.3 Dependencies (Current package.json)

```json
{
  "dependencies": {
    "@tauri-apps/cli": "^2.11.2",
    "@vitejs/plugin-react": "^4.3.1",
    "lucide-react": "^0.468.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.0"
  }
}
```

**Zero UI libraries.** Consider adding for the redesign:
- `react-router-dom` — proper page routing with URL sync
- `framer-motion` — animations (page transitions, card hover, typing indicator)
- `@radix-ui/react-*` or `@headlessui/react` — accessible primitives (Select, Dialog, Popover)
- `recharts` or `visx` — sparkline charts for progress/frustration trends
- `react-markdown` + `rehype-highlight` — markdown rendering for reports
- `react-hot-toast` or `sonner` — toast notifications

---

## Appendix D: Tauri Window Configuration

Current config (`desktop/src-tauri/tauri.conf.json`):
```json
{
  "productName": "Aurora Vision Agent",
  "version": "0.1.0",
  "identifier": "local.aurora.vision-agent",
  "app": {
    "windows": [{
      "title": "Aurora Vision Agent",
      "width": 1280,
      "height": 820,
      "resizable": true
    }]
  }
}
```

**Missing Tauri features:**
- No custom title bar (uses OS default)
- No system tray icon
- No app icon
- No splashscreen
- No auto-updater
- No single-instance lock

---

## Appendix E: 中英文适配规范 (Chinese Localization Spec)

### E.0 设计原则

1. **中文为主**：默认语言为简体中文，英文为可选切换
2. **术语一致性**：技术术语统一翻译，不混用中英（如 "Dry-run" → "模拟运行"）
3. **不翻译的内容**：API 路径、代码标识符、JSON 字段名保持英文
4. **Persona 名称不翻译**：Aurora / Mira / Sera / Nagi 保持原名
5. **状态枚举翻译**：STOPPED/RUNNING/PAUSED 等系统状态翻译为中文展示

### E.1 品牌与服务状态

| 当前英文 | 目标中文 | 备注 |
|----------|----------|------|
| Aurora Vision Agent (HTML title) | Aurora 视觉伴游 | 浏览器标签页标题 |
| Aurora Agent (sidebar) | Aurora Agent | 品牌名保留英文 |
| Vision Kernel Shell | 视觉内核控制台 | 副标题 |
| Local Service Connected | 本地服务已连接 | |
| Local Service Offline | 本地服务离线 | |

### E.2 导航菜单

| 当前英文 | 目标中文 |
|----------|----------|
| Dashboard | 控制台 |
| Run Monitor | 运行监视 |
| Reports | 报告 |
| Settings | 设置 |
| Calibration | 校准向导 |
| Skill Library | 技能库 |
| Task Planner | 任务规划 |
| Companion | 伴游 |
| Combat | 战斗 |
| Product Demo | 产品验证 |

### E.3 系统状态 (Mode Pills)

| 当前英文 | 目标中文 | 颜色 |
|----------|----------|------|
| STOPPED | 已停止 | 默认灰 |
| RUNNING | 运行中 | 绿 #80f7c4 |
| PAUSED | 已暂停 | 黄 #ffe082 |
| EMERGENCY_STOPPED | 紧急停止 | 红 #ff8fa3 |

### E.4 Dashboard 页面

| 当前英文 | 目标中文 |
|----------|----------|
| Dry-run default | 模拟运行模式 |
| No active skill | 无活跃技能 |
| Start | 启动 |
| Pause | 暂停 |
| Resume | 恢复 |
| Stop | 停止 |
| Emergency Stop | 紧急停止 |
| Start Local Service | 启动本地服务 |
| Run Diagnostics | 运行诊断 |
| Open Calibration | 打开校准向导 |
| Open Skill Library | 打开技能库 |
| Focus OK | 焦点状态 |
| Input Released | 输入状态 |
| Telemetry OK | 遥测状态 |
| Runtime Health | 运行时健康 |
| DRY_RUN | 模拟模式 |
| Released | 已释放 |
| Held | 占用中 |
| Streaming | 数据流正常 |
| Backpressure | 背压 |
| Healthy | 健康 |
| Attention | 需关注 |

### E.5 Run Monitor 页面

| 当前英文 | 目标中文 |
|----------|----------|
| Progress | 进度 |
| Frustration | 挫败感 |
| Target | 目标状态 |
| Interrupt | 中断 |
| None | 无 |
| Event Stream | 事件流 |
| Waiting for state frames... | 等待状态帧... |

### E.6 Reports 页面

| 当前英文 | 目标中文 |
|----------|----------|
| Report Reader | 报告阅读器 |
| Latest Run | 最近运行 |
| Kernel | 内核报告 |
| Product | 产品报告 |
| Showcase | 演示报告 |
| Latest Kernel Run | 最近内核运行 |
| Latest Product Report | 最近产品报告 |
| Latest Showcase Report | 最近演示报告 |
| No report found. Run a demo, then choose Kernel, Product, or Showcase. | 未找到报告。请先运行演示，然后选择内核、产品或演示报告。 |

### E.7 Settings 页面

| 当前英文 | 目标中文 |
|----------|----------|
| Input Backend | 输入后端 |
| Real Input | 实际输入 |
| Disabled by default | 默认禁用 |
| Safe Window | 安全窗口 |
| Required for physical input | 实际输入需要 |
| F9 Stop | F9 紧急停止 |
| Enabled in runners | 已在运行器中启用 |

### E.8 Calibration Wizard 页面

| 当前英文 | 目标中文 |
|----------|----------|
| First-run setup | 首次运行设置 |
| Calibration Wizard | 校准向导 |
| Step 1 / Step 2 / ... | 步骤 1 / 步骤 2 / ... |
| Back | 上一步 |
| Next | 下一步 |
| Sandbox Demo | 沙盒演示 |
| QA Environment | QA 测试环境 |
| Analysis Only | 仅分析 |
| Dry-run Only | 仅模拟运行 |
| No physical input will be used. | 不使用实际输入。 |
| Guided setup with dry-run safety defaults. | 引导式设置，默认安全模拟模式。 |
| Refresh Windows | 刷新窗口列表 |
| focused | 已聚焦 |
| Select a window first. | 请先选择目标窗口。 |
| main_view | 主画面 |
| target_area | 目标区域 |
| minimap | 小地图 |
| skill_bar | 技能栏 |
| status_area | 状态区域 |
| dialog_area | 对话区域 |
| interaction_prompt_area | 交互提示区 |
| relative | 相对坐标 |
| anchor-based | 锚点坐标 |
| top-left | 左上 |
| top-right | 右上 |
| bottom-left | 左下 |
| bottom-right | 右下 |
| center | 中心 |
| Detector | 检测器 |
| Model File | 模型文件 |
| Found | 已就绪 |
| Missing | 缺失 |
| Ultralytics | Ultralytics 框架 |
| Available | 可用 |
| Unavailable | 不可用 |
| Tracker | 追踪器 |
| Run Benchmark | 运行基准测试 |
| Benchmark returns capture FPS and latency estimates. | 基准测试将返回采集帧率和延迟估算。 |
| Input Backend | 输入后端 |
| dry-run / console | 模拟运行 / 控制台 |
| F9 Emergency Stop | F9 紧急停止 |
| Enabled | 已启用 |
| Focus Protection | 焦点保护 |
| Required for safe-window | 安全窗口模式必需 |
| release_all Test | 输入释放测试 |
| Available via Emergency Stop | 可通过紧急停止触发 |
| Save Active Profile | 保存当前配置 |
| Save Profile | 保存配置 |
| The profile will be written to configs/profiles, versioned, and set active. | 配置将保存至 configs/profiles，自动版本管理并设为活跃。 |
| Choose a mode to begin. | 选择一个运行模式开始。 |
| Select the target window from the list. | 从列表中选择目标窗口。 |
| No target window found. Start the test environment first. | 未找到目标窗口。请先启动测试环境。 |
| Window selected. Review the live snapshot before drawing ROIs. | 已选中窗口。预览截图后开始绘制 ROI。 |
| Select a target window before saving a profile. | 保存配置前请先选择目标窗口。 |
| {roiName} ROI captured. Add more ROIs or continue. | {name} ROI 已捕获。可继续添加或进入下一步。 |
| Could not load windows. Is the service running? | 无法加载窗口列表。请确认服务是否已启动？ |
| Profile {profile_id} saved and validated. | 配置 {id} 已保存并验证通过。 |
| Profile saved but needs review: {errors} | 配置已保存，但需要检查：{errors} |

### E.9 Skill Library 页面

| 当前英文 | 目标中文 |
|----------|----------|
| Start Recording | 开始录制 |
| Capture Event | 捕获事件 |
| Marker | 标记 |
| Stop Recording | 停止录制 |
| Save Draft | 保存草稿 |
| Save Demo Skill | 保存演示技能 |
| Timeline / Step Tree | 时间线 / 步骤树 |
| Properties | 属性面板 |
| Validate | 验证 |
| Dry-run | 模拟运行 |
| Replay Dry-run | 重放模拟运行 |
| Record or select a skill... | 录制或选择一个技能。生成的草稿将包含原始事件、分段、检查点和回退策略。 |
| Ready. | 就绪。 |
| SkillDraft generated with automatic segments. | 技能草稿已生成，自动分段完成。 |
| Marker added. | 标记已添加。 |
| Test-window event captured. | 测试窗口事件已捕获。 |
| Validation passed. | 验证通过。 |
| Saved draft as {skill_id} v{version} | 草稿已保存为 {id} v{version} |

### E.10 Task Planner 页面

| 当前英文 | 目标中文 |
|----------|----------|
| Natural Language Goal | 自然语言目标 |
| Sandbox Validation | 沙盒验证 |
| Failure Explanation | 失败原因解释 |
| Generate TaskSpec | 生成任务规格 |
| Explain Mock Failure | 解释模拟失败 |
| TaskSpec must pass schema validation... | 任务规格必须通过格式验证、技能存在性检查、安全工具校验、最大重试限制和模拟图运行后才能执行。 |
| No failure selected. | 未选择失败事件。 |
| Default goal text | 分析沙盒目标并完成经过验证的模拟运行流程。 |

Provider 名称保持英文：mock / glm / minimax

### E.11 Companion 页面

| 当前英文 | 目标中文 |
|----------|----------|
| {name} Companion | {name} 伴游 |
| Trigger Mock Event | 触发模拟事件 |
| Why Failed? | 为什么失败？ |
| Emergency Stop | 紧急停止 |

事件代码保持英文（技术标识符）：TARGET_LOST, NO_TASK_PROGRESS 等

已为中文的内容保持不变：
- "观察中" → 保持
- "我会把底层事件翻译成用户能理解的反馈，并保留安全边界。" → 保持

### E.12 Combat 页面

| 当前英文 | 目标中文 |
|----------|----------|
| Combat Playbook | 战斗策略 |
| Reflex Evasion | 反射闪避 |
| Reflex History | 闪避记录 |
| Graph | 图表 |
| JSON | JSON |
| Generate Playbook | 生成策略 |
| Trigger Danger | 触发危险信号 |
| Run Showcase Demo | 运行演示 |
| DangerScore | 危险评分 |
| Current Node | 当前节点 |
| Dodge | 闪避 |
| Cooldown | 冷却 |
| Generate a playbook to inspect schema validation. | 生成战斗策略以检查格式验证。 |
| Mock/LLM strategist will generate guarded behavior-tree nodes. | 模拟/LLM 策略器将生成带保护的行为树节点。 |
| Companion will explain danger, dodge, recovery, and completion events. | 伴游将解释危险、闪避、恢复和完成事件。 |
| No danger events yet. | 暂无危险事件。 |
| DangerScore will emit DODGE_REFLEX when high threshold is crossed. | 危险评分超过阈值时将触发闪避反射。 |

### E.13 Product Demo 页面

| 当前英文 | 目标中文 |
|----------|----------|
| Product Demo Checklist | 产品验证清单 |
| Run Result | 运行结果 |
| Run Dry-run E2E | 运行端到端模拟测试 |
| Refresh Checklist | 刷新清单 |
| Latest Report | 最近报告 |
| OK | 通过 |
| WAIT | 等待 |
| Ready for E2E dry-run. | 端到端模拟测试就绪。 |
| Running dry-run E2E... | 正在运行端到端模拟测试... |
| E2E passed. Report: {report_path} | 端到端测试通过。报告：{path} |
| E2E failed: {error} | 端到端测试失败：{error} |

### E.14 通用术语对照表

| 英文 | 中文 | 使用场景 |
|------|------|----------|
| dry-run | 模拟运行 | 全局 |
| safe-window | 安全窗口 | 全局 |
| console | 控制台 | 输入后端 |
| skill | 技能 | 全局 |
| target | 目标 | 追踪 |
| tracker | 追踪器 | 感知 |
| detector | 检测器 | 感知 |
| benchmark | 基准测试 | 性能 |
| calibration | 校准 | 配置 |
| profile | 配置文件 | 配置 |
| ROI (Region of Interest) | 感兴趣区域 | 校准 |
| playbook | 策略 | 战斗 |
| reflex | 反射 | 战斗 |
| dodge | 闪避 | 战斗 |
| companion | 伴游 | 交互 |
| persona | 人格 | 交互 |
| frustration | 挫败感 | 控制 |
| progress | 进度 | 控制 |
| telemetry | 遥测 | 系统 |
| diagnostics | 诊断 | 系统 |
| emergency stop | 紧急停止 | 安全 |
| focus | 焦点 | 安全 |
| interrupt | 中断 | 控制 |
| release all | 释放全部输入 | 安全 |
| timeout | 超时 | 执行 |
| fallback | 回退策略 | 执行 |
| trigger | 触发器 | 感知 |
| visual trigger | 视觉触发器 | 感知 |
| action block | 动作块 | 编排 |
| StateBus | 状态总线 | 内部（不展示） |
| watchdog | 看门狗 | 内部（不展示） |
| deadman switch | 死人开关 | 内部（不展示） |

### E.15 实现方案建议

#### 方案一：简单字典替换（推荐 MVP）

不引入 i18n 框架，用一个 `zh.ts` 字典文件统一管理：

```typescript
// desktop/src/i18n/zh.ts
const t = {
  // Brand
  brandTitle: "Aurora Agent",
  brandSub: "视觉内核控制台",

  // Nav
  nav_dashboard: "控制台",
  nav_monitor: "运行监视",
  nav_reports: "报告",
  nav_settings: "设置",
  nav_calibration: "校准向导",
  nav_skills: "技能库",
  nav_planner: "任务规划",
  nav_companion: "伴游",
  nav_combat: "战斗",
  nav_checklist: "产品验证",

  // Status
  status_connected: "本地服务已连接",
  status_offline: "本地服务离线",
  mode_stopped: "已停止",
  mode_running: "运行中",
  mode_paused: "已暂停",
  mode_emergency: "紧急停止",

  // Dashboard
  dash_dryrun: "模拟运行模式",
  dash_no_skill: "无活跃技能",
  btn_start: "启动",
  btn_pause: "暂停",
  btn_resume: "恢复",
  btn_stop: "停止",
  btn_emergency: "紧急停止",
  // ... 约 200 条
} as const;
export default t;
```

组件中使用：
```tsx
import t from "../i18n/zh";
// <button>{t.btn_start}</button>
// <h1>{t.nav_dashboard}</h1>
```

#### 方案二：React Context + 语言切换（未来扩展）

当需要支持英文切换时，升级为：

```typescript
// desktop/src/i18n/context.tsx
const languages = { zh: zhDict, en: enDict };
const I18nContext = createContext(languages.zh);
// <I18nProvider lang="zh"><App /></I18nProvider>
```

#### 建议

**当前阶段使用方案一**。理由：
1. 200 个字符串的字典文件约 150 行，轻量可维护
2. 避免引入 react-i18next 等额外依赖
3. 后续需要英文切换时，字典文件可直接迁移为 i18n 资源
4. 所有翻译集中在 `i18n/zh.ts`，不散落在组件中

### E.16 HTML 页面标题

```html
<!-- desktop/index.html -->
<title>Aurora 视觉伴游</title>
```

# Meridian --- Design System

**Document:** `DESIGN_SYSTEM.md`\
**Product:** Meridian --- Clarity for complex engineering\
**Status:** Proposed MVP design specification\
**Applies to:** Web app, investigation workspace, shared components, and
product UI\
**Last updated:** 2026-10-28

------------------------------------------------------------------------

## 1. Purpose

This document defines Meridian's visual language, design tokens,
component behavior, layout rules, interaction patterns, accessibility
expectations, and implementation conventions.

Meridian is an evidence-driven software investigation platform. The
interface should feel like a serious engineering workspace: calm,
precise, readable, transparent about uncertainty, and trustworthy under
pressure.

The design system must make the difference between **observed
evidence**, **AI-generated hypotheses**, **proposed changes**, and
**verified outcomes** visually unmistakable.

## 2. Product design principles

1.  **Clarity over decoration.** Favor hierarchy, spacing, typography,
    and clear labels over gradients, glow effects, or ornamental
    visuals.
2.  **Evidence before confidence.** Show source and evidence links
    beside claims. Do not make a model hypothesis look like an
    established fact.
3.  **Truthful states.** A patch proposal, an approved patch, and a
    verified patch must have distinct visual states.
4.  **Dense but readable.** Developers need logs, paths, diffs, and
    timelines. Use compact data layouts without sacrificing legibility.
5.  **Progressive disclosure.** Show the most important information
    first; place raw logs, metadata, and advanced settings behind
    expandable panels.
6.  **Safe by design.** Risky actions such as patch approval and source
    deletion require clear context and confirmation.
7.  **Keyboard-first and accessible.** All workflows must be operable
    without a mouse, and status must not depend on color alone.
8.  **Responsive, not merely shrunk.** Mobile layouts must prioritize
    essential information and adapt complex tables and sidebars rather
    than squeezing desktop UI onto a small screen.
9.  **Consistent engineering language.** Use stable terms across UI,
    API, database, and reports.
10. **Respect reduced motion.** Motion should communicate state change,
    not act as decoration.

------------------------------------------------------------------------

## 3. Brand identity

### 3.1 Brand

-   **Name:** Meridian
-   **Tagline:** Clarity for complex engineering.
-   **Category:** AI-assisted software debugging and reliability.
-   **Personality:** Precise, composed, technical, transparent,
    dependable.
-   **Visual metaphor:** A clear line through a complex
    system---signals, evidence, and decisions converging into an
    understandable path.

### 3.2 Art direction

Use a dark-first engineering interface with neutral charcoal surfaces,
high-contrast text, and a restrained blue accent. A muted teal may be
used sparingly for successful states or secondary emphasis. Avoid
purple-heavy themes, rainbow gradients, excessive glassmorphism, bright
neon borders, and glowing cards.

The product should look like a mature developer tool, not a gaming
dashboard or generic AI landing page.

### 3.3 Logo direction

Use a simple wordmark and a compact geometric mark inspired by a
meridian, a central axis, or two aligned paths. The mark must remain
recognizable at 16--24 px and work in monochrome.

Rules: - Prefer SVG for the logo. - Use a one-color version by
default. - Do not use gradients in the core logo. - Avoid literal bug
icons, robot heads, magic wands, and complex circuitry. - Keep clear
space around the mark. - The wordmark should read `Meridian` with normal
capitalization.

The logo can be refined later; do not block MVP engineering on custom
branding.

------------------------------------------------------------------------

## 4. Color system

Use CSS variables/design tokens as the single source of truth. Values
below are initial recommendations; validate contrast using automated
checks and manual review before release.

### 4.1 Core dark palette

  Token                      Hex                  Usage
  -------------------------- -------------------- ---------------------------------------
  `--color-canvas`           `#0B0D10`            Main application background
  `--color-surface-1`        `#11151A`            Primary panels and sidebars
  `--color-surface-2`        `#171C22`            Cards, elevated panels
  `--color-surface-3`        `#202730`            Hovered/active surfaces
  `--color-surface-inset`    `#0E1216`            Code and log wells
  `--color-border`           `#29313A`            Standard borders
  `--color-border-strong`    `#3A4652`            Emphasized dividers
  `--color-text-primary`     `#F3F5F7`            Primary text
  `--color-text-secondary`   `#B0BAC5`            Supporting text
  `--color-text-muted`       `#7F8A96`            Timestamps, tertiary labels
  `--color-accent`           `#6EA8FE`            Primary actions and focus accents
  `--color-accent-hover`     `#8AB8FF`            Accent hover
  `--color-accent-pressed`   `#4D8FE8`            Accent pressed
  `--color-accent-subtle`    `#17283E`            Selected accent background
  `--color-teal`             `#5BC4B8`            Secondary emphasis and positive trend
  `--color-overlay`          `rgb(0 0 0 / 64%)`   Modal backdrop

### 4.2 Semantic colors

  -----------------------------------------------------------------------
  Token                   Hex                     Meaning
  ----------------------- ----------------------- -----------------------
  `--color-success`       `#49C59A`               Confirmed successful
                                                  checks

  `--color-warning`       `#E8B45B`               Caution, pending
                                                  approval, partial
                                                  results

  `--color-danger`        `#F07178`               Failures, destructive
                                                  actions

  `--color-info`          `#78AFFF`               Informational messages

  `--color-neutral`       `#AAB4BF`               Unknown or neutral
                                                  state
  -----------------------------------------------------------------------

Semantic colors must always be paired with text labels and/or icons. Do
not use color alone to communicate a result.

### 4.3 Light theme

The MVP may launch dark-first. If a light theme is added, define a
complete token set rather than inverting individual colors ad hoc.
Preserve semantic meaning and verify contrast independently. Do not mix
dark and light surfaces within the same view except for deliberate,
accessible overlays.

### 4.4 Color usage rules

-   Use the accent for primary actions, focused controls, selected
    navigation, and links---not for every border.
-   Keep most surfaces neutral.
-   Reserve semantic colors for status and feedback.
-   Avoid large saturated fills behind long text.
-   Do not use gradient backgrounds for dashboard cards or page
    sections.
-   Ensure selected states are visible in both color and shape/border.
-   Verify text contrast against actual rendered surfaces; do not assume
    the palette automatically meets WCAG AA for every combination.

------------------------------------------------------------------------

## 5. Typography

### 5.1 Font stack

Recommended UI stack:

``` css
font-family:
  Inter,
  "Segoe UI",
  Roboto,
  Helvetica,
  Arial,
  sans-serif;
```

Use a local/self-hosted font when licensing and performance allow. A
system fallback must always exist.

Recommended monospace stack for code, paths, logs, and identifiers:

``` css
font-family:
  "JetBrains Mono",
  "SFMono-Regular",
  Consolas,
  "Liberation Mono",
  monospace;
```

### 5.2 Type scale

  ----------------------------------------------------------------------------
  Token                     Size     Line height          Weight Typical use
  -------------- --------------- --------------- --------------- -------------
  `--text-xs`              12 px           16 px        400--500 Metadata,
                                                                 compact
                                                                 labels

  `--text-sm`              13 px           20 px        400--500 Secondary UI,
                                                                 table details

  `--text-md`              14 px           22 px        400--500 Default
                                                                 application
                                                                 text

  `--text-lg`              16 px           24 px        500--600 Card titles
                                                                 and
                                                                 emphasized
                                                                 content

  `--text-xl`              20 px           28 px             600 Section
                                                                 headings

  `--text-2xl`             24 px           32 px        600--650 Page titles

  `--text-3xl`             30 px           38 px        600--700 Marketing or
                                                                 major
                                                                 overview
                                                                 headings
  ----------------------------------------------------------------------------

Use sentence case for headings. Avoid all-caps section headings except
tiny, clearly secondary metadata labels. Keep long-form report text at a
comfortable line length.

### 5.3 Typography rules

-   Use left-aligned headings consistently.
-   Use one font family for most UI; reserve monospace for technical
    content.
-   Avoid very thin weights on dark backgrounds.
-   Do not use tiny text for critical status or error messages.
-   Use tabular numerals for durations, counts, and metric columns where
    available.
-   Preserve user-provided code and logs without typographic
    substitutions.
-   Do not use color alone to distinguish inline code or links.

------------------------------------------------------------------------

## 6. Spacing, sizing, and layout

### 6.1 Spacing scale

Use a 4 px base unit.

  Token            Value
  -------------- -------
  `--space-1`       4 px
  `--space-2`       8 px
  `--space-3`      12 px
  `--space-4`      16 px
  `--space-5`      20 px
  `--space-6`      24 px
  `--space-8`      32 px
  `--space-10`     40 px
  `--space-12`     48 px
  `--space-16`     64 px

Use consistent spacing within component families. Do not introduce
arbitrary values unless a layout constraint requires it.

### 6.2 Radius

  Token                Value Usage
  ----------------- -------- ----------------------------------------
  `--radius-sm`         4 px Small controls, badges
  `--radius-md`         8 px Buttons, inputs, compact cards
  `--radius-lg`        12 px Main cards, dialogs
  `--radius-xl`        16 px Large landing sections or empty states
  `--radius-pill`     999 px Pills and status chips

Use restrained corner rounding. Avoid rounding every nested container;
too many nested rounded boxes make technical interfaces feel soft and
cluttered.

### 6.3 Layout dimensions

  Token                                                       Recommended value
  ----------------------------- -----------------------------------------------
  `--topbar-height`                                                       56 px
  `--sidebar-width`                                                      248 px
  `--sidebar-collapsed-width`                                             64 px
  `--inspector-width`                                                    320 px
  `--content-max-width`                                                 1440 px
  `--page-padding`                24 px desktop, 16 px tablet, 12--16 px mobile
  `--touch-target-min`                                               44 × 44 px

Use CSS grid/flex layouts that can collapse gracefully. Avoid hard-coded
widths that cause horizontal overflow on smaller screens.

------------------------------------------------------------------------

## 7. Elevation, borders, and surfaces

Meridian should communicate hierarchy primarily through surface contrast
and spacing, not heavy shadows.

-   **Level 0:** canvas background.
-   **Level 1:** primary shell panels.
-   **Level 2:** cards and grouped content.
-   **Level 3:** popovers, menus, and dialogs.
-   **Inset:** code/log panels and input wells.

Use 1 px borders for most panel boundaries. Use shadows sparingly for
overlays only. Avoid persistent glow effects, excessive blur, and
decorative glass panels that reduce code readability.

Example:

``` css
.panel {
  background: var(--color-surface-1);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.panel--elevated {
  background: var(--color-surface-2);
  border-color: var(--color-border-strong);
}

.code-well {
  background: var(--color-surface-inset);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}
```

------------------------------------------------------------------------

## 8. Design tokens

Recommended starter token file:

``` css
:root {
  color-scheme: dark;

  --color-canvas: #0B0D10;
  --color-surface-1: #11151A;
  --color-surface-2: #171C22;
  --color-surface-3: #202730;
  --color-surface-inset: #0E1216;

  --color-border: #29313A;
  --color-border-strong: #3A4652;

  --color-text-primary: #F3F5F7;
  --color-text-secondary: #B0BAC5;
  --color-text-muted: #7F8A96;

  --color-accent: #6EA8FE;
  --color-accent-hover: #8AB8FF;
  --color-accent-pressed: #4D8FE8;
  --color-accent-subtle: #17283E;
  --color-teal: #5BC4B8;

  --color-success: #49C59A;
  --color-warning: #E8B45B;
  --color-danger: #F07178;
  --color-info: #78AFFF;
  --color-neutral: #AAB4BF;
  --color-overlay: rgb(0 0 0 / 64%);

  --font-sans: Inter, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;

  --text-xs: 0.75rem;
  --text-sm: 0.8125rem;
  --text-md: 0.875rem;
  --text-lg: 1rem;
  --text-xl: 1.25rem;
  --text-2xl: 1.5rem;
  --text-3xl: 1.875rem;

  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --space-12: 3rem;
  --space-16: 4rem;

  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-pill: 999px;

  --topbar-height: 56px;
  --sidebar-width: 248px;
  --sidebar-collapsed-width: 64px;
  --inspector-width: 320px;
  --content-max-width: 1440px;

  --focus-ring: 0 0 0 3px rgb(110 168 254 / 35%);
}
```

Use tokens in components. Do not duplicate hex values throughout the
codebase. If using Tailwind, map tokens to Tailwind theme variables and
use semantic class names where appropriate.

------------------------------------------------------------------------

## 9. Core interaction states

All interactive controls must have explicit visual states:

-   Default
-   Hover
-   Focus-visible
-   Active/pressed
-   Selected
-   Disabled
-   Loading
-   Success
-   Error

### 9.1 Focus

Use a visible focus ring. Never remove the browser outline without
providing a stronger replacement.

``` css
:where(button, a, input, textarea, select, [tabindex]):focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
```

### 9.2 Loading

-   Keep layout stable while loading.
-   Use skeletons only when they represent the final content structure.
-   Label long-running operations with text, such as "Capturing browser
    evidence" or "Running regression checks."
-   Do not use an infinite spinner as the only explanation of progress.
-   Allow cancellation where safe and supported.

### 9.3 Empty states

Every list or panel should have an intentional empty state that explains
what is missing and, when useful, offers one clear next action. Avoid
empty dashboards with unexplained blank space.

### 9.4 Error states

Errors should state: 1. What failed. 2. What is known. 3. Whether any
work is still running. 4. What the user can do next.

Never imply that a bug was fixed if the run ended inconclusively or
verification did not complete.

------------------------------------------------------------------------

## 10. Semantic status design

Status must be communicated by label, icon/shape, and color. Never use
color alone.

  -----------------------------------------------------------------------
  Meaning                 Label examples          Visual treatment
  ----------------------- ----------------------- -----------------------
  Queued                  `Queued`                Neutral badge + queue
                                                  icon

  Running                 `Running`               Accent badge + subtle
                                                  activity indicator

  Awaiting human approval `Needs approval`        Warning badge +
                                                  approval icon

  Completed workflow      `Completed`             Neutral/positive badge,
                                                  with outcome explained
                                                  separately

  Verified checks passed  `Checks passed`         Success badge + check
                                                  icon + list of checks

  Verification failed     `Checks failed`         Danger badge + failure
                                                  icon + failed check
                                                  details

  Blocked                 `Blocked`               Warning/danger badge +
                                                  reason

  Inconclusive            `Inconclusive`          Neutral badge +
                                                  explicit uncertainty

  Cancelled               `Cancelled`             Neutral badge

  Stale patch             `Patch stale`           Warning badge +
                                                  rebase/regenerate
                                                  guidance
  -----------------------------------------------------------------------

### 10.1 Distinguish workflow completion from fix success

The investigation may be complete while the outcome is inconclusive,
blocked, or a patch fails verification. Avoid using a single green
"Success" badge for every terminal investigation.

### 10.2 Evidence and hypothesis labels

-   **Observed:** directly captured from a deterministic tool or
    supplied by the user.
-   **Hypothesis:** a candidate explanation that may be supported or
    refuted.
-   **Proposed:** a suggested test or patch not yet applied.
-   **Approved:** a human approved the exact diff and base snapshot.
-   **Applied:** the patch was applied to an isolated workspace.
-   **Verified:** configured checks actually ran and passed.
-   **Not verified:** required checks were skipped, blocked, timed out,
    or not run.

Use these labels consistently across cards, timelines, patch views, and
reports.

------------------------------------------------------------------------

## 11. Component specifications

### 11.1 Buttons

Variants: - **Primary:** one main action per local context. -
**Secondary:** normal alternative action. - **Tertiary/ghost:**
low-emphasis navigation or utility. - **Danger:** destructive or
high-risk action. - **Icon button:** compact utility with accessible
name and tooltip.

Rules: - Minimum height: 36 px for dense desktop controls; 44 px touch
target on touch layouts. - Pair loading state with a text label where
possible. - Do not place multiple competing primary buttons side by
side. - Destructive actions must not use the primary accent style. -
Disabled controls should explain why the action is unavailable when that
is not obvious.

### 11.2 Inputs and text areas

-   Use persistent labels, not placeholder-only labels.
-   Show helper text for constraints and accepted formats.
-   Keep validation messages near the relevant field.
-   Preserve user input after validation errors.
-   Use a visible character count for long bug reports.
-   Never render user input as HTML.

### 11.3 Cards and panels

Use cards to group related information, not to wrap every single line.
Keep titles left-aligned and content hierarchy consistent.

A standard panel contains: 1. Optional eyebrow/metadata. 2. Left-aligned
title. 3. Main content. 4. Optional footer actions.

Avoid excessive nested cards, ornamental gradients, and giant border
radii.

### 11.4 Data tables

-   Use semantic table markup where appropriate.
-   Align numeric columns consistently.
-   Use tabular numerals for timestamps/counts.
-   Provide visible sort direction when sorting is enabled.
-   On mobile, switch to stacked summary rows or allow deliberate
    horizontal scrolling within the table container.
-   Keep row actions accessible to keyboard and screen-reader users.
-   Do not truncate critical statuses without an accessible full label.

### 11.5 Code and diff viewer

-   Use monospace typography and a high-contrast inset surface.
-   Show file path, change type, and diff status.
-   Distinguish additions/deletions using color plus `+`/`−` markers and
    accessible labels.
-   Preserve whitespace and line breaks.
-   Support line numbers and copy-to-clipboard where useful.
-   Do not interpret diff content as HTML or executable markup.
-   Clearly label the base snapshot and diff digest in the patch review
    view.
-   Require a deliberate action to approve the exact diff currently
    displayed.

### 11.6 Log viewer

-   Use a monospace font and preserve line breaks.
-   Offer wrap/no-wrap controls where practical.
-   Support copying and filtering without losing the original evidence.
-   Show capture time, source tool, and truncation indicator.
-   Redact secrets before display.
-   Avoid placing logs in tiny fixed-height boxes with no expansion
    control.

### 11.7 Evidence card

Each evidence card should show: - Evidence type and capture time. -
Source tool or capture method. - One-sentence description. - Redaction
state where relevant. - Related stage or hypothesis. - Open/download
action, only when authorized.

Never display a "captured" artifact as proof that a hypothesis is true
without showing the relationship.

### 11.8 Hypothesis card

Each hypothesis card should show: - Explicit `Hypothesis` label. - Short
explanation. - Confidence only if it is clearly described as
model-estimated and not calibrated. - Supporting and contradicting
evidence counts. - Current status: proposed, supported, refuted,
inconclusive, or superseded. - Evidence links. - Optional user
feedback/review state.

Do not display a confidence percentage as though it were a statistically
calibrated probability unless calibration has been measured.

### 11.9 Patch review panel

Must include: - Patch summary. - Base snapshot/commit. - Diff digest or
stable patch version. - Files changed. - Evidence and hypotheses
motivating the change. - Baseline test results. - Approval and
verification status. - Clear approve/reject controls. - Explicit warning
that approval applies to this exact diff. - Confirmation when approval
will trigger isolated application and verification.

Approval must be disabled when the diff is stale, unavailable, changed
since review, or the user lacks permission.

### 11.10 Verification summary

Show each required check independently: - Build - Unit/integration
tests - Regression test - Lint - Type check - Browser reproduction
check, if applicable

For each check show its actual status, exit code when available,
duration, and link to output. Use `Skipped`, `Blocked`, `Timed out`, and
`Not run` distinctly. A summary must not turn mixed results into a
blanket "passed."

### 11.11 Timeline

Use a chronological activity feed with: - Timestamp. - Event label. -
Short user-facing summary. - Related resource links. - Clear distinction
between user action and system event.

Keep the feed concise. Link to detailed artifacts rather than embedding
full logs.

### 11.12 Dialogs and confirmations

Use dialogs for actions that require focus or confirmation, not routine
navigation. For patch approval, the dialog should restate the action and
identify the exact diff/base snapshot. For destructive actions, explain
consequences and whether data can be recovered.

Dialogs must trap focus correctly, close with Escape when safe, and
return focus to the triggering control.

### 11.13 Toasts and inline alerts

-   Use toasts for brief confirmations that do not require action.
-   Use inline alerts for persistent errors, blocked workflows, and
    important warnings.
-   Do not use a toast as the only record of patch approval or
    verification outcome; the timeline must retain the event.
-   Do not automatically dismiss critical errors before users can read
    them.

------------------------------------------------------------------------

## 12. Application layout

### 12.1 Global shell

Desktop shell: - Top bar: brand, workspace/project context, global
actions, user menu. - Left navigation: workspace/project navigation and
investigation history. - Main content: page-specific content. - Optional
right inspector: selected evidence, hypothesis, or patch details.

Keep the global navigation stable between views. Avoid unnecessary
full-page transitions during an investigation.

### 12.2 Recommended navigation

-   Overview
-   Projects
-   Investigations
-   Reports
-   Workspace settings

Project-level navigation may include: - Summary - Investigations -
Repository snapshots - Settings

Investigation-level tabs or sections: - Overview - Evidence -
Hypotheses - Patch - Verification - Activity

On smaller screens, collapse the sidebar into a drawer and make the
right inspector a full-screen or bottom-sheet panel.

### 12.3 Dashboard

Prioritize: - Active investigations and their current stage. -
Investigations awaiting user approval. - Latest outcomes, including
inconclusive/blocked. - Project/source health. - Recent activity.

Do not add vanity metrics that do not help developers take action. Use
clear empty states for new workspaces.

### 12.4 Investigation workspace

Suggested desktop structure:

``` text
┌─────────────────────────────────────────────────────────────────┐
│ Top bar: Meridian / Workspace / Project / User                   │
├──────────────┬──────────────────────────────────┬───────────────┤
│ Left nav     │ Investigation main content      │ Inspector     │
│              │                                  │ (optional)    │
│ Projects     │ Title + status + current stage   │ Selected      │
│ Investigations│ Stage progress                 │ evidence or   │
│ Reports      │ Evidence / hypotheses / patch    │ patch details │
│ Settings     │ Verification / activity          │               │
└──────────────┴──────────────────────────────────┴───────────────┘
```

Use the inspector only when it adds value. On narrow screens, make it
collapsible.

### 12.5 Stage progress

Show the investigation stage list with state labels and short
descriptions. Do not show fake percentage progress unless it is computed
from real stage data. If progress is indeterminate, say what is
currently happening rather than inventing a completion estimate.

------------------------------------------------------------------------

## 13. Responsive behavior

Design and test at these widths:

-   Small mobile: 320--374 px
-   Standard mobile: 375--767 px
-   Tablet: 768--1023 px
-   Desktop: 1024--1439 px
-   Wide desktop: 1440 px and above

Rules: - No horizontal page overflow at 320 px. - Use responsive padding
and flexible grids. - Keep primary actions visible without covering
content. - Convert multi-column panels to stacked sections on mobile. -
Collapse sidebars and inspectors. - Make code/diff panels horizontally
scrollable within their own container, not across the entire page. -
Provide accessible touch targets. - Preserve keyboard access and focus
order at every breakpoint. - Ensure dialogs fit the viewport and scroll
internally if needed. - Test long filenames, stack traces, URLs, and
unbroken identifiers.

------------------------------------------------------------------------

## 14. Accessibility

Target **WCAG 2.2 AA** as the product baseline.

Requirements: - Sufficient text and non-text contrast. - Keyboard
operation for all functionality. - Visible focus indicator. - Logical
heading hierarchy and landmark regions. - Accessible labels and error
descriptions for form fields. - Screen-reader announcements for
asynchronous status changes where appropriate. - Status communicated
through text/icon as well as color. - Reduced-motion support via
`prefers-reduced-motion`. - No flashing or attention-grabbing
animation. - Dialog focus management and Escape behavior. - Proper table
headers and accessible sort state. - Alternative text for meaningful
imagery; decorative images use empty alt text. - Do not use color as the
only way to distinguish diff lines or verification states.

Example reduced-motion rule:

``` css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

Accessibility checks should be part of component and end-to-end testing,
not a final visual polish task.

------------------------------------------------------------------------

## 15. Motion and micro-interactions

Use motion only to explain state changes: - Brief hover/focus
transitions. - Small progress indicator changes when a stage state
changes. - Subtle disclosure animation for accordions. - Respect
reduced-motion settings. - Never animate logs or the entire page
continuously. - Avoid parallax, decorative particle effects, glowing
cursor trails, and large spring animations in the engineering workspace.

Recommended transition duration: approximately 120--180 ms for common
control states. Keep movement small and consistent.

------------------------------------------------------------------------

## 16. Content and terminology

Use plain, precise engineering language.

  Prefer                    Avoid
  ------------------------- ---------------------------------------------
  `Observed`                `AI knows`
  `Hypothesis`              `Root cause confirmed` before evidence
  `Patch proposed`          `Fixed` before application and verification
  `Checks passed`           `Bug fixed` based only on a green status
  `Inconclusive`            `Success` when evidence is insufficient
  `Blocked` with a reason   Silent spinner or unexplained failure
  `Not run`                 Implying a skipped test passed
  `Approval required`       Ambiguous action labels like `Continue`

For user-facing errors, explain the next action. Avoid internal acronyms
unless they are familiar to the target developer audience or explained
in context.

------------------------------------------------------------------------

## 17. Frontend implementation guidance

Recommended frontend: React/Next.js with TypeScript. The system can be
implemented with Tailwind CSS or CSS Modules, provided the tokens remain
centralized and component behavior stays consistent.

### 17.1 Suggested structure

``` text
frontend/
  src/
    app/
    components/
      ui/
        Button.tsx
        Input.tsx
        Textarea.tsx
        Badge.tsx
        Card.tsx
        Dialog.tsx
        Tooltip.tsx
        Tabs.tsx
        DataTable.tsx
        Skeleton.tsx
        Alert.tsx
      investigation/
        StageProgress.tsx
        EvidenceCard.tsx
        HypothesisCard.tsx
        PatchReviewPanel.tsx
        DiffViewer.tsx
        VerificationSummary.tsx
        ActivityTimeline.tsx
      layout/
        AppShell.tsx
        Sidebar.tsx
        Topbar.tsx
        InspectorPanel.tsx
    styles/
      tokens.css
      globals.css
```

### 17.2 Component rules

-   Use semantic HTML before custom ARIA roles.
-   Prefer a small, composable component set.
-   Keep design tokens centralized.
-   Use typed props and discriminated unions for stateful components.
-   Keep visual components separate from data-fetching/workflow logic.
-   Do not implement different status colors separately in each page.
-   Use a single status mapping utility for investigation, stage, patch,
    and verification states.
-   Test loading, empty, error, disabled, and mobile states---not only
    the happy path.
-   Avoid adding a UI library solely for one component; choose a
    consistent accessible component foundation.

### 17.3 Status mapping example

``` ts
type VerificationStatus =
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "blocked"
  | "timed_out"
  | "cancelled"
  | "inconclusive";

const verificationStatusMeta: Record<
  VerificationStatus,
  { label: string; tone: "neutral" | "info" | "success" | "danger" | "warning" }
> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "info" },
  passed: { label: "Checks passed", tone: "success" },
  failed: { label: "Checks failed", tone: "danger" },
  blocked: { label: "Blocked", tone: "warning" },
  timed_out: { label: "Timed out", tone: "warning" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  inconclusive: { label: "Inconclusive", tone: "neutral" },
};
```

Do not map investigation `completed` directly to verification `passed`;
they represent different concepts.

------------------------------------------------------------------------

## 18. Testing and quality gates

Before shipping any shared component or page, verify:

-   [ ] Dark palette and token usage are consistent.
-   [ ] Headings are left-aligned and hierarchy is clear.
-   [ ] Focus, hover, active, disabled, loading, success, and error
    states are implemented.
-   [ ] No color-only status communication.
-   [ ] Text contrast is checked for relevant combinations.
-   [ ] Keyboard navigation works.
-   [ ] Screen-reader labels and announcements are appropriate.
-   [ ] Responsive layouts work at 320, 375, 768, 1024, and 1440 px.
-   [ ] Long logs, paths, and diffs do not cause page-level overflow.
-   [ ] Empty and failure states are designed.
-   [ ] Patch approval clearly identifies the exact diff and base
    snapshot.
-   [ ] Verification UI distinguishes passed, failed, blocked, timed
    out, skipped, and not run.
-   [ ] Reduced-motion preference is respected.
-   [ ] No fake progress, fake metrics, or unsupported success claims
    appear.

------------------------------------------------------------------------

## 19. Definition of done

The design system is ready for MVP implementation when:

-   [ ] Tokens are implemented once and used across all pages.
-   [ ] Shared components cover the main interaction states.
-   [ ] Navigation and layout work at desktop, tablet, and mobile
    widths.
-   [ ] Status labels and colors are centralized.
-   [ ] Evidence, hypotheses, patches, and verification outcomes are
    visually distinct.
-   [ ] Patch approval requires deliberate review of the exact diff.
-   [ ] All critical actions are keyboard accessible.
-   [ ] Core flows include loading, empty, error, blocked, and
    inconclusive states.
-   [ ] Accessibility and responsive checks are part of CI/manual QA.
-   [ ] No decorative effect reduces code, log, or diff readability.

------------------------------------------------------------------------

## 20. Future extensions

After the MVP is stable, consider: - A complete light theme. -
User-configurable density for logs and tables. - More advanced diff
navigation. - Saved investigation filters. - Workspace-level visual
customization within approved tokens. - A Figma component library that
mirrors the production tokens. - Design token export for CSS variables
and Tailwind configuration.

Do not expand the theme system before the core investigation flow is
reliable.

------------------------------------------------------------------------

**End of document.**

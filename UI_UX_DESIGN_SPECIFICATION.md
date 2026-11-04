# Meridian AI --- UI/UX Design Specification

**File:** `UI_UX_DESIGN_SPECIFICATION.md`\
**Purpose:** Complete screen inventory, visual system, interaction
specification, and screen-by-screen Stitch design brief.\
**Product:** Meridian AI --- Clarity for complex engineering\
**Design direction:** Sage & Bone\
**Version:** 1.0

------------------------------------------------------------------------

# 1. Product and design intent

Meridian is an AI-assisted software debugging and reliability platform.
It turns a bug report into a structured investigation using project
inspection, controlled browser reproduction, runtime and visual
evidence, evidence-linked hypotheses, regression tests, human-approved
patches, and execution-based verification.

The interface must always make five things clear:

1.  What was actually observed.
2.  What is an AI-generated hypothesis.
3.  What is only a proposed action.
4.  What the user has approved.
5.  What was actually executed and verified.

Never visually imply that a hypothesis is a fact, a proposed patch is
already applied, or a skipped test passed.

## Design identity: Sage & Bone

The supplied reference establishes the **Sage & Bone** visual
language: - Warm paper neutrals. - Deep green-ink text and actions. -
Sage green as the brand voice. - Mostly neutral surfaces. - Restrained
semantic colors. - Editorial serif headlines on marketing pages. - Clean
sans-serif UI text. - Monospace technical content.

**Dark mode is the default workspace theme.** Light mode is a
sage-tinted bone studio. The supplied light landing-page screenshot is a
reference for the marketing direction; the palette screenshot defines
both themes.

The product should feel calm, precise, premium, technical, and
trustworthy---not like a generic AI dashboard.

Avoid excessive gradients, neon glows, decorative glassmorphism, giant
rounded cards, random charts, and long explanatory copy in navigation.

------------------------------------------------------------------------

# 2. Design principles

1.  Evidence before interpretation.
2.  Compact navigation and short labels.
3.  Progressive disclosure for technical detail.
4.  One primary action per view.
5.  Status uses text plus icon/shape, never color alone.
6.  Real backend state only; no fake progress.
7.  Human control for approval and destructive actions.
8.  Responsive layouts, not merely shrunk desktop layouts.
9.  Accessible contrast, keyboard use, and reduced motion.
10. Neutral surfaces; color communicates meaning.

------------------------------------------------------------------------

# 3. Color system

Use these exact canonical values from the supplied palette.

## 3.1 Light --- Sage & Bone Studio

  Role      Name    Hex         Usage
  --------- ------- ----------- ----------------------------
  Canvas    Bone    `#eff0e6`   Main background
  Surface   Cream   `#fafbf6`   Cards, panels, dialogs
  Text      Ink     `#1e2119`   Primary text
  Action    Ink     `#1e2119`   Strong actions
  Sage      Moss    `#57663f`   Brand accent, active state
  Success   Leaf    `#2c7a4d`   Passed checks
  Warning   Ochre   `#96690f`   Pending/caution
  Danger    Clay    `#c23b2e`   Errors/destructive
  Info      Blue    `#325fc4`   Informational state

## 3.2 Dark --- Night & Moss

  Role      Name    Hex         Usage
  --------- ------- ----------- ----------------------------
  Canvas    Night   `#0e100c`   Main background
  Surface   Moss    `#171a14`   Cards, panels, dialogs
  Text      Pale    `#eef2e6`   Primary text
  Action    Pale    `#eef2e6`   Strong action treatment
  Sage      Mist    `#a9bd93`   Brand accent, active state
  Success   Mint    `#4fd08c`   Passed checks
  Warning   Sand    `#e8b45a`   Pending/caution
  Danger    Coral   `#f26d5f`   Errors/destructive
  Info      Sky     `#7fb0f5`   Informational state

## 3.3 Usage rules

-   Most surfaces stay neutral.
-   Sage is used for brand identity, selection, links, and key
    highlights.
-   Semantic colors appear only when the corresponding state exists.
-   Accent flips with theme: dark ink buttons on light; pale buttons on
    dark.
-   Use subtle tinted status backgrounds, not large blocks of saturated
    color.
-   Never use success green for a proposed or unverified fix.
-   A hypothesis must not look like a confirmed outcome.
-   Avoid color-only status indicators.
-   Test contrast rather than assuming every palette pairing is
    accessible.

## 3.4 Semantic CSS tokens

Implement tokens such as: `--bg-canvas`, `--bg-surface`,
`--bg-elevated`, `--text-primary`, `--text-secondary`, `--text-muted`,
`--border-subtle`, `--border-strong`, `--brand`, `--success`,
`--warning`, `--danger`, `--info`.

Map them to the light/dark values above. Secondary text and borders may
use opacity variants, but verify contrast.

## 3.5 Charts

-   Neutral axes and grid lines.
-   Sage for the primary series.
-   Semantic colors only for actual statuses.
-   Tooltips show exact values and units.
-   Provide legends and text/table alternatives.
-   Every chart has an empty state.
-   Never show fabricated chart values.

------------------------------------------------------------------------

# 4. Typography

Use three consistent font roles:

-   **Display serif:** marketing hero and selected editorial moments
    only. Suggested: Newsreader or DM Serif Display.
-   **UI sans-serif:** all application UI. Suggested: Inter or Geist
    Sans.
-   **Monospace:** code, paths, IDs, hashes, logs, timestamps, API
    routes. Suggested: JetBrains Mono or Geist Mono.

Choose one family per role; do not mix several fonts in the same role.

  Style               Size Usage
  ------------ ----------- ---------------------------
  Display XL     64--76 px Landing hero
  Display L      48--56 px Marketing section heading
  H1             30--36 px Workspace page title
  H2             22--26 px Main panel heading
  H3             16--18 px Card/section title
  Body           14--16 px Standard UI
  Body L         16--18 px Main explanatory text
  Small          12--13 px Metadata
  Micro          11--12 px Compact labels, sparingly
  Code           12--14 px Logs and code

### Low-text navigation rule

The user specifically wants low text density in tabs and the left
panel: - Sidebar labels: one or two words maximum. - Tabs: one or two
words maximum. - Use icon + short label. - No descriptions or paragraphs
in the sidebar. - Tooltips for icon-only controls. - Card descriptions:
one concise sentence maximum. - Use expandable `Details` for long
explanations. - Actions use short verbs: `New`, `Run`, `Review`,
`Approve`, `Reject`, `Retry`. - Keep full technical details in dedicated
views, not navigation.

------------------------------------------------------------------------

# 5. Layout, spacing, and component shape

## Workspace shell

**Desktop** - Expanded sidebar: 232--256 px. - Collapsed sidebar: 64--72
px. - Top bar: 60--68 px. - Main content max width: 1440 px for standard
views. - Main padding: 24--32 px. - Panel gap: 16--24 px. -
Investigation and diff views may use wider layouts.

**Tablet** - Sidebar becomes a drawer/collapsible rail. - Main padding:
20--24 px. - Multi-column layouts reduce to one or two columns.

**Mobile** - Drawer or compact navigation. - Main padding: 16 px. - Keep
primary actions reachable. - Tables become stacked rows or controlled
horizontal scroll. - Diff review uses file-by-file layout if necessary.

## Spacing scale

Use a 4 px base scale: `4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80`.

## Radii

-   Small controls: 8--10 px.
-   Inputs/buttons: 10--12 px.
-   Cards: 14--18 px.
-   Dialogs: 18--22 px.
-   Pills: fully rounded.

## Borders and shadows

Use subtle 1 px borders. Shadows are reserved for elevated menus,
dialogs, drawers, and floating controls. Dark mode should rely on tonal
separation rather than glow.

------------------------------------------------------------------------

# 6. Global application shell

## Left sidebar

**Workspace selector** - Meridian mark. - Workspace name. - Dropdown
chevron.

**Primary navigation** - Overview - Projects - Investigations

**Secondary** - Members (only if implemented) - Settings

**Bottom** - Help - User avatar/account menu

Keep labels short. Do not add explanatory text under navigation items.

## Top bar

-   Breadcrumb/current page.
-   Optional global search/command menu.
-   Contextual actions.
-   Theme toggle.
-   Profile or notification controls only if functional.

## Navigation behavior

-   Active item: restrained sage surface or left indicator.
-   Hover: subtle neutral surface.
-   Collapsed icons have tooltips.
-   Preserve navigation context when practical.
-   Warn before leaving unsaved forms.
-   Always show keyboard focus.

------------------------------------------------------------------------

# 7. Complete screen inventory

## Public / marketing

  ID       Screen                Route                             Priority
  -------- --------------------- --------------------------------- -------------------------
  PUB-01   Landing               `/`                               P0
  PUB-02   How it works          `/#workflow` or `/how-it-works`   P1
  PUB-03   Principles & trust    `/#principles` or `/principles`   P1
  PUB-04   Demo / product tour   `/demo`                           P1
  PUB-05   Status                `/status`                         P2
  PUB-06   Developer             `/developers`                     P2
  PUB-07   Privacy               `/privacy`                        P0 before public launch
  PUB-08   Terms                 `/terms`                          P0 before public launch

## Authentication

  ID        Screen                Route                Priority
  --------- --------------------- -------------------- --------------------
  AUTH-01   Sign in               `/login`             P0
  AUTH-02   Create account        `/signup`            P0
  AUTH-03   Forgot password       `/forgot-password`   P1 if applicable
  AUTH-04   Reset password        `/reset-password`    P1 if applicable
  AUTH-05   Verify email          `/verify-email`      Provider-dependent
  AUTH-06   Auth callback/error   `/auth/callback`     P0 for OAuth

## Workspace

  ID      Screen                       Route                     Priority
  ------- ---------------------------- ------------------------- ----------
  WS-01   Overview dashboard           `/app`                    P0
  WS-02   Project list                 `/app/projects`           P0
  WS-03   Investigation list           `/app/investigations`     P0
  WS-04   Global search/command menu   Overlay                   P1
  WS-05   Activity/notifications       `/app/activity`           P2
  WS-06   Members                      `/app/settings/members`   P2
  WS-07   Workspace settings           `/app/settings`           P1

## Projects

  --------------------------------------------------------------------------------------------
  ID                Screen            Route                                  Priority
  ----------------- ----------------- -------------------------------------- -----------------
  PROJ-01           Add               `/app/projects/new`                    P0
                    project/source                                           

  PROJ-02           Validation        `/app/projects/new/validation`         P0
                    progress                                                 

  PROJ-03           Project overview  `/app/projects/:projectId`             P0

  PROJ-04           Snapshots         `/app/projects/:projectId/snapshots`   P1

  PROJ-05           Project settings  `/app/projects/:projectId/settings`    P1

  PROJ-06           Project activity  `/app/projects/:projectId/activity`    P2
  --------------------------------------------------------------------------------------------

## Investigations

  ------------------------------------------------------------------------------------------------------
  ID                Screen             Route                                           Priority
  ----------------- ------------------ ----------------------------------------------- -----------------
  INV-01            New investigation  `/app/projects/:projectId/investigations/new`   P0

  INV-02            Investigation      `/app/investigations/:id`                       P0
                    workspace                                                          

  INV-03            Overview           `/app/investigations/:id/overview`              P0

  INV-04            Reproduction       `/app/investigations/:id/reproduction`          P0

  INV-05            Evidence explorer  `/app/investigations/:id/evidence`              P0

  INV-06            Hypothesis review  `/app/investigations/:id/hypotheses`            P0

  INV-07            Regression tests   `/app/investigations/:id/tests`                 P0

  INV-08            Patch review       `/app/investigations/:id/patch`                 P0

  INV-09            Verification       `/app/investigations/:id/verification`          P0

  INV-10            Report             `/app/investigations/:id/report`                P0

  INV-11            Activity history   `/app/investigations/:id/activity`              P1

  INV-12            Investigation      Context menu                                    P1
                    actions/settings                                                   
  ------------------------------------------------------------------------------------------------------

## Account and system

  ID       Screen                    Route                         Priority
  -------- ------------------------- ----------------------------- ----------
  SET-01   Profile                   `/app/settings/profile`       P1
  SET-02   Preferences               `/app/settings/preferences`   P1
  SET-03   Security                  `/app/settings/security`      P1
  SET-04   Usage                     `/app/settings/usage`         P2
  SYS-01   Not found                 `/404`                        P0
  SYS-02   Access denied             `/403`                        P0
  SYS-03   Application error         Error boundary                P0
  SYS-04   Unavailable/maintenance   `/unavailable`                P2

------------------------------------------------------------------------

# 8. Screen-by-screen specifications

## PUB-01 --- Landing page

**Purpose:** Explain Meridian quickly and establish trust.

**Layout** - Minimal top navigation. - Left-aligned editorial hero. -
Right-side investigation activity illustration. - Generous whitespace
and restrained paper texture/dot pattern. - Clear CTA.

**Header** - Meridian icon and wordmark. - Links: Workflow, Principles,
Demo, Status, Developer. - Theme toggle. - `Open workspace`.

**Hero content** - Eyebrow: `MERIDIAN AI · DEBUGGING & RELIABILITY` -
Headline: `Bug reports in. Investigation-grade clarity.` - Supporting
copy:
`Meridian reproduces software failures in isolation, captures evidence, proposes testable hypotheses, and verifies proposed fixes with real test runs—with you approving every change.` -
Primary CTA: `Open the workspace` - Secondary CTA: `How it works`

**Right-side visual** A compact investigation activity panel: -
Investigation identifier. - Current status. - Short timestamped
events. - Artifact count. - Sandbox health.

If illustrative, label it as demo data. Never imply a simulated activity
feed is live.

**Below hero** - Three principles: Evidence first, Human approved,
Verified by execution. - Workflow. - Trust principles. - Demo. - Footer.

**Motion** Subtle text reveal and panel fade/translate. No constant
looping motion.

**Mobile** Stack hero and illustration; maintain readable headline;
buttons wrap or become full-width.

## PUB-02 --- How it works

-   Headline: `From symptom to verified change.`
-   Five steps: Report, Reproduce, Analyze, Review, Verify.
-   Each step has one short sentence and a small interface illustration.
-   Expandable details for longer explanation.
-   Avoid large text blocks.

## PUB-03 --- Principles & trust

Sections: - Evidence over guesses. - Hypotheses are not facts. - Human
approval before patch application. - Verification comes from
execution. - Untrusted code runs in isolation. - Private
project/evidence access.

Use concise copy and simple icons. Do not invent certifications.

## PUB-04 --- Demo / product tour

-   Select a seeded sample investigation.
-   Show workflow states, evidence, hypothesis, diff, and verification.
-   Clearly label illustrative demo data.
-   If no interactive demo exists, use a recorded walkthrough or static
    demo state.

## PUB-05 --- Status

Show API, web, worker, model provider (if monitored), object storage,
and real incidents. Never show a green status without monitoring
evidence.

## PUB-06 --- Developer

Show API overview, supported profiles, evidence/report formats, security
model, and documentation links. Never expose private endpoints or
secrets.

## AUTH-01 --- Sign in

Compact centered or split layout: - Meridian logo. - `Welcome back.` -
Email. - Password if applicable. - `Sign in`. - OAuth only for
configured providers. - Forgot password and sign-up links.

States: default, invalid credentials, loading, provider unavailable,
verification required, rate limited. Keep marketing copy out of the
form.

## AUTH-02 --- Create account

Fields: name if needed, email, password if first-party auth, terms
acceptance. Validate inline, show concise password requirements, prevent
duplicate submission.

## AUTH-03 / AUTH-04 --- Password recovery

Forgot: email + `Send reset link`.\
Reset: new password + confirmation + `Update password`.\
Avoid account enumeration.

## AUTH-05 / AUTH-06 --- Verification and callback

States: verifying, verified, expired, failed. Provide retry or return to
sign in. Technical error codes stay behind `Details`.

## WS-01 --- Workspace overview dashboard

**Purpose:** Show what needs attention and where work stands.

**Header** - Title: `Overview` - Primary: `New investigation` -
Secondary: `Add project`

**Summary metrics** - Projects. - Active investigations. - Awaiting
review. - Verified fixes.

Counts must come from backend records. Show zero when zero; never
fabricate values.

**Main panels** 1. Recent investigations: Issue, Project, Status,
Updated. 2. Active work / needs attention. 3. Recent projects. 4.
Activity timeline.

**Empty state** - `Your workspace is ready.` - `Add a project` -
Optional `Explore the workflow`.

Avoid vanity charts and generic AI usage graphs. Add analytics only when
sufficient real data exists.

**Responsive** Four metric columns desktop; two tablet; one/two mobile.
Activity moves below primary work on mobile.

## WS-02 --- Project list

-   Heading: `Projects`
-   CTA: `Add project`
-   Search.
-   Filters: All, Active, Archived.
-   Rows: icon, project name, stack, snapshot hash, last activity,
    status, menu.
-   Empty state: `No projects yet.` + `Add your first project`.

## WS-03 --- Investigation list

-   Heading: `Investigations`
-   CTA: `New investigation`
-   Filters: All, Running, Review, Completed, Blocked.
-   Columns: Issue, Project, Stage/status, Updated, Owner if
    collaboration exists.
-   Search, sort, filter.
-   Empty and no-results states.

## WS-04 --- Global search / command menu

Centered command dialog triggered by search or keyboard shortcut. Search
input and grouped results: Projects, Investigations, Actions. Actions
include New project, New investigation, Settings only when authorized.

## PROJ-01 --- Add project

Focused three-step flow: 1. Source. 2. Details. 3. Review.

Show only implemented source options. ZIP upload can be primary
initially. Include drag/drop, browse, file validation, progress, cancel,
and concise security note:
`Repository code is treated as untrusted and is not executed during upload validation.`

## PROJ-02 --- Project validation

Real stages: - Upload received. - Archive validated. - Project
inspected. - Runtime profile detected. - Snapshot created.

Each row shows status, timestamp, concise detail, expandable output.
States: running, completed, failed, unsupported, blocked. Do not animate
a stage to completion before backend confirmation.

## PROJ-03 --- Project overview

Header: project name, stack badges, snapshot short hash,
`New investigation`, menu.

Content: summary, latest snapshot, recent investigations, activity,
runtime profile, validation warnings.

Short tabs: Overview, Issues, Snapshots, Settings.

## PROJ-04 --- Snapshots

Table: snapshot ID/hash, created date, source revision, runtime profile,
linked investigations. Detail drawer: file count, content hash, manifest
metadata, validation, source origin.

## PROJ-05 --- Project settings

Sections: General, Runtime, Test profile, Access/retention,
Archive/delete if supported. Commands map only to approved profiles;
never accept arbitrary model commands.

## PROJ-06 --- Project activity

Compact chronological events with timestamp, actor/source, stage, and
related record.

## INV-01 --- New investigation

Fields: - Title. - Description. - Expected behavior. - Actual
behavior. - Reproduction steps. - Route/URL (optional). - Severity
(optional). - Screenshot/log attachments (optional).

Use short labels and helpful placeholders. Show attachment previews and
remove controls. Sticky footer: `Cancel`, `Start investigation`.
Navigate only after API confirms creation.

## INV-02 / INV-03 --- Investigation workspace and overview

This is the most important authenticated screen.

**Header** - Breadcrumb: Project / Investigation. - Issue title. -
Compact status badge. - Snapshot short hash. - Context menu.

**Compact stage rail** - Inspect - Reproduce - Analyze - Test - Patch -
Verify - Report

Show completed/current/pending/failed/blocked/skipped states. Full
backend stage names live in technical details.

**Main content** - Current finding. - Reproduction summary. - Hypotheses
with evidence counts. - Baseline/post-patch test status. - Recent
evidence. - Activity timeline. - One contextual next action.

**Short tabs** - Overview - Evidence - Hypotheses - Tests - Patch -
Verify - Report - Activity

If too wide, use overflow/secondary navigation rather than tiny labels.

All activity must link to persisted records. Empty/blocked states
explain the missing prerequisite and safe next action.

## INV-04 --- Reproduction

Two-column desktop layout: - Main: browser screenshot/preview and
reproduction steps. - Side: run details and browser events.

Show status, timestamp, browser/runtime profile, steps, screenshot
checkpoints, console events, failed requests, trace metadata.

Action: `Run again` only if retry is safe. Statuses: Reproduced, Not
reproduced, Blocked, Inconclusive. Never say Fixed here.

## INV-05 --- Evidence explorer

Filters: All, Images, Console, Network, Logs, Tests, Source.

Evidence rows/cards show ID, type, short title, timestamp, origin/stage.
Detail panel shows screenshot or log, source metadata, related tool run,
snapshot, related hypotheses, authorized download.

Raw evidence must be visually distinct from AI summaries. Clicking an
evidence reference opens the exact artifact.

## INV-06 --- Hypothesis review

Left: compact hypothesis list with ID, short title, status, evidence
count. Right: selected hypothesis.

Detail: statement, confidence rationale, supporting evidence,
contradicting evidence, missing information, suggested next step.

Actions: Mark useful, Reject, Request more evidence if supported. A user
click must not falsely mark a hypothesis as technically confirmed.

Proposed hypotheses use neutral/sage styling, not success green.

## INV-07 --- Regression tests

List: test name, framework, baseline status, latest status. Detail:
purpose, proposed code, file path, validation, command profile, output,
duration, exit code.

Actions: Review proposal, Run baseline, View logs. Distinguish proposed
tests from executed tests.

## INV-08 --- Patch review

Critical safety screen.

Header metadata: - Patch ID. - Status. - Base snapshot hash. - Diff
hash. - Changed file count. - Added/deleted lines.

Layout: - Left changed-files list. - Center syntax-highlighted diff. -
Right explanation, related hypothesis, evidence links, risk,
limitations. - Sticky footer: `Approve patch`, `Reject`.

Approval dialog identifies exact patch and base snapshot and explains
consequences. If diff or base hash changes, previous approval is
invalid. Never hide changed files.

## INV-09 --- Verification

Summary: aggregate status, counts of passed/failed/blocked/skipped/timed
out, timestamp, patch identity.

Check list: regression test, type check, lint, build, other supported
checks. Each row: status, duration, exit code, `View logs`.

Show baseline versus post-patch results where useful.

Statuses: - Passed: success. - Failed: danger. - Blocked:
warning/neutral. - Skipped: muted. - Timed out: warning/danger by
policy. - Inconclusive: neutral.

Include note:
`Verification reflects the checks executed in this environment. It does not guarantee the absence of all possible defects.`

Never show a large success banner if required checks were skipped or
blocked.

## INV-10 --- Investigation report

Report title, final status, project/snapshot metadata, export menu.

Sections: 1. Issue summary. 2. Project and snapshot. 3. Reproduction
outcome. 4. Key observations. 5. Hypotheses and evidence. 6.
Regression-test proposal. 7. Baseline results. 8. Patch and approval. 9.
Post-patch verification. 10. Limitations and unresolved questions. 11.
Timeline.

Generate from persisted records. Model summarization may explain records
but cannot invent or overwrite results. Markdown/HTML first; PDF when
implemented and tested.

## INV-11 --- Activity history

Chronological event list: event, actor/system, timestamp, stage, related
evidence/tool run, expandable details. Keep default view compact.

## SET-01 --- Profile

Display name, email, avatar/initials, account creation date. Only allow
changes supported by identity provider.

## SET-02 --- Preferences

Theme: System / Dark / Light. Reduced motion: System / On / Off.
Timezone preference if supported. Persist preferences and preview theme
immediately.

## SET-03 --- Security

Authentication provider, active sessions if supported, sign-out
controls, security notices. Never display credentials or secrets.

## SET-04 --- Usage

Only build when reliable usage data exists: investigation count,
execution time, storage, model usage/cost, plan limits if applicable. No
fabricated numbers.

## SYS-01 to SYS-04 --- System states

Not found, access denied, unexpected error, unavailable/maintenance.
Each has a concise explanation, safe next action, return link, and
optional technical details disclosure. Never expose raw stack traces to
ordinary users.

------------------------------------------------------------------------

# 9. Reusable component inventory

Build a coherent design system.

**Navigation** - WorkspaceSwitcher - Sidebar - SidebarItem - Topbar -
Breadcrumbs - PageTabs - CommandMenu

**Forms/actions** - Button - IconButton - Input - Textarea - Select -
Combobox - Checkbox - RadioGroup - Switch - FileDropzone - FormField -
InlineValidation

**Data display** - MetricCard - DataTable - ProjectRow -
InvestigationRow - StatusBadge - Metadata - EmptyState - Skeleton -
Pagination

**Investigation** - InvestigationHeader - StageRail - StageTimeline -
ActivityEvent - EvidenceCard - EvidenceViewer - HypothesisCard -
EvidenceReference - TestResultRow - DiffViewer - PatchApprovalDialog -
VerificationSummary - VerificationCheck - ReportSection

**Feedback/overlays** - Dialog - Drawer - Popover - Tooltip - Toast -
Alert - ConfirmActionDialog - ErrorBoundary

All components must support both themes and accessible states.

------------------------------------------------------------------------

# 10. Motion and animation

Motion should explain transitions, not distract.

  Token           Duration Use
  ---------- ------------- -----------------------
  Fast         120--160 ms Hover/button feedback
  Base         180--240 ms Menus, tabs
  Slow         260--360 ms Drawers, dialogs
  Emphasis     400--550 ms Landing hero only

Suggested easing: `cubic-bezier(0.2, 0, 0, 1)`.

Allowed: - Landing hero fade/translate. - Sidebar collapse width
transition. - Dialog/drawer fade and slight scale. - Tab indicator
transition. - Toast slide/fade. - Stage indicator change after a real
backend transition. - Low-contrast skeleton shimmer. - Brief diff-line
highlight after navigation.

Avoid: - Infinite spinning logos. - Animated charts without changing
data. - Fake typing to simulate AI thought. - Fake progress bars. -
Confetti for routine test passes. - Parallax that harms usability. -
Large 3D scenes in the investigation workspace. - Spline as a dependency
for core functionality.

Respect `prefers-reduced-motion`. Stage animations may run only after
backend-confirmed transitions.

------------------------------------------------------------------------

# 11. Content and microcopy

## Preferred short labels

  Action             Label
  ------------------ -------------------
  Create             New investigation
  Add source         Add project
  Inspect proposal   Review patch
  Accept             Approve patch
  Decline            Reject
  Reproduce again    Run again
  Inspect artifact   View evidence
  Inspect output     View logs
  Retry safe step    Retry
  Open report        View report

## Status vocabulary

**Investigation:** Queued, Running, Awaiting review, Completed, Failed,
Blocked, Inconclusive, Cancelled.

**Reproduction:** Reproduced, Not reproduced, Blocked, Inconclusive.

**Hypothesis:** Proposed, Supported, Rejected, Needs evidence, Validated
by test only when criteria are met.

**Patch:** Draft, Ready for review, Awaiting approval, Approved,
Rejected, Applied, Failed to apply.

**Verification:** Passed, Failed, Blocked, Skipped, Timed out,
Inconclusive.

Do not reuse one status vocabulary for different concepts.

Use plain English, short active phrases, and direct explanations. Never
say "fixed" unless verification policy supports the claim.

------------------------------------------------------------------------

# 12. Dashboard data and visualization

The dashboard should help the developer decide what to work on next.

## Summary metrics

-   Projects.
-   Active investigations.
-   Awaiting review.
-   Verified fixes.

Definitions: - Active = non-terminal and progressing. - Awaiting review
= explicit user decision required. - Verified fixes = required
verification policy passed. - Rejected patches are not verified fixes.

## Main panels

1.  Recent investigations.
2.  Active work / needs attention.
3.  Recent projects.
4.  Recent activity.

Optional analytics after real data exists: - Investigations by status. -
Median time to first evidence. - Verification outcomes over time. -
Common failure categories.

Avoid vanity metrics such as "AI intelligence score." Every metric needs
a defensible definition.

## Empty dashboard

Show zero counts, `Your workspace is ready`, and one next action. Never
use placeholder chart values.

------------------------------------------------------------------------

# 13. Loading, empty, error, blocked, and partial states

Every screen must define these states.

**Loading:** geometry-matched skeletons; avoid full-page spinner unless
route cannot render.

**Empty:** explain what is absent and provide one primary action.

**Error:** say what failed, whether data was saved, and provide safe
retry if available. Put technical details behind disclosure.

**Blocked:** explain the missing prerequisite and who can resolve it. Do
not show a useless retry button.

**Partial:** preserve completed stages and evidence; show failed/skipped
stages separately.

**Long-running:** show persisted stage and last update; poll with
backoff or use supported event stream; cancellation only if backend
supports it.

------------------------------------------------------------------------

# 14. Accessibility

-   Target WCAG 2.2 AA where practical and test contrast.
-   Semantic landmarks and heading hierarchy.
-   Keyboard-reachable controls and visible focus.
-   Dialogs trap and restore focus.
-   Associated form labels and readable errors.
-   Status uses text/icon as well as color.
-   Code/diff viewers have accessible labels and keyboard navigation.
-   Charts have text summaries or data tables.
-   Reduced motion support.
-   Added/removed diff lines must not rely on color alone.
-   Layout survives browser zoom and text scaling.

------------------------------------------------------------------------

# 15. Responsive breakpoints

-   **Desktop 1280 px+:** expanded sidebar, multi-column overview,
    side-by-side evidence and details, full diff.
-   **Laptop 1024--1279 px:** collapsible sidebar, reduced columns, no
    page overflow.
-   **Tablet 768--1023 px:** drawer sidebar, selective stacking,
    essential table columns.
-   **Mobile \<768 px:** compact header, one-column content, sticky
    primary action where useful, full-screen evidence viewer,
    file-by-file diff review.

Test at 375, 768, 1024, 1280, and 1440 px.

------------------------------------------------------------------------

# 16. Stitch screen generation strategy

Generate screens one at a time. Use one shared design foundation, then
append the relevant screen prompt. Do not ask Stitch to generate the
entire product in one pass.

## 16.1 Shared Stitch master prompt

``` text
Design a premium developer SaaS application named Meridian AI.
Tagline: "Clarity for complex engineering."

Meridian investigates software bug reports using isolated browser reproduction,
real runtime evidence, evidence-linked hypotheses, regression tests,
human-approved patches, and execution-based verification.

VISUAL IDENTITY: Sage & Bone.
Dark mode is the default. Light mode is a warm sage-tinted bone studio.

LIGHT:
Canvas #eff0e6; Surface #fafbf6; Text/Action #1e2119;
Sage #57663f; Success #2c7a4d; Warning #96690f;
Danger #c23b2e; Info #325fc4.

DARK:
Canvas #0e100c; Surface #171a14; Text/Action #eef2e6;
Sage #a9bd93; Success #4fd08c; Warning #e8b45a;
Danger #f26d5f; Info #7fb0f5.

Style: calm, precise, editorial, premium, technical.
Mostly neutral surfaces, restrained sage accents, fine borders,
subtle elevation, no excessive gradients, neon glow, or generic AI dashboard style.
Use refined serif only for major marketing headlines, clean sans-serif for UI,
and monospace for code/logs.

Navigation: compact left sidebar with short labels:
Overview, Projects, Investigations. Settings and Help near bottom.
Icons plus short labels. No sidebar descriptions or paragraphs.
Compact top bar with breadcrumbs, search/actions, theme toggle.

Content density: tabs and navigation labels one or two words.
Concise labels and compact metadata. Progressive disclosure for details.
Do not fill the screen with decorative cards.

Trust: distinguish observations, hypotheses, proposed patches, and verified results.
Never label a proposed patch as fixed. Never use success green for unverified work.
Use text plus icon/shape for every status.

Design desktop-first with responsive adaptation. Use realistic content;
mark illustrative demo data. Generate only the requested screen and
preserve reusable components and design language.
```

## 16.2 Screen-specific Stitch prompts

### Stitch 01 --- Landing page

``` text
Create the Meridian AI landing page. Minimal top navigation:
Meridian wordmark, Workflow, Principles, Demo, Status, Developer,
theme toggle, Open workspace.

Hero:
Eyebrow: "MERIDIAN AI · DEBUGGING & RELIABILITY"
Headline: "Bug reports in. Investigation-grade clarity."
Short copy about reproducing failures in isolation, capturing evidence,
proposing hypotheses, and verifying patches with human approval.

Place a compact investigation activity panel on the right with an investigation ID,
Reproducing status, short timestamped events, artifact count, and sandbox health.
Label it demo data if illustrative.

Below: three principles, workflow, trust section, and footer.
Use Sage & Bone; no generic chatbot styling.
```

### Stitch 02 --- Workspace dashboard

``` text
Create the authenticated Meridian overview in dark mode by default.
Compact sidebar: Overview, Projects, Investigations, Settings, Help.
Top bar: workspace selector, search, theme, profile.

Heading: Overview. Primary: New investigation. Secondary: Add project.
Four compact metrics: Projects, Active investigations, Awaiting review, Verified fixes.
Below: Recent investigations table (Issue, Project, Status, Updated),
Active work panel, Recent projects, compact activity timeline.
Use realistic sample data clearly marked illustrative.
No decorative charts or unsupported AI metrics.
Also show a polished empty-state variant if possible.
```

### Stitch 03 --- Project list

``` text
Create the Projects page. Heading Projects, action Add project.
Search and filters All, Active, Archived.
Rows show project icon/name, stack, snapshot hash, last activity, status, menu.
Include a concise empty state. Keep labels short and metadata compact.
```

### Stitch 04 --- Add project

``` text
Create Add project onboarding with three steps: Source, Details, Review.
Show only implemented source methods; ZIP upload is primary.
Include drag/drop, browse, accepted file details, upload/validation state,
and note: "Repository code is treated as untrusted and is not executed during upload validation."
Minimal technical layout.
```

### Stitch 05 --- New investigation

``` text
Create New investigation form. Fields: Title, Description, Expected behavior,
Actual behavior, Reproduction steps, Route (optional), Severity (optional),
Attachments. Short labels, concise placeholders, attachment preview.
Sticky footer: Cancel and Start investigation. Avoid long help paragraphs.
```

### Stitch 06 --- Investigation workspace

``` text
Create the main Meridian investigation workspace.
Header: Project / Investigation breadcrumb, issue title, status, snapshot hash, menu.
Compact stage rail: Inspect, Reproduce, Analyze, Test, Patch, Verify, Report.
Main content: Current finding, reproduction summary, hypotheses with evidence counts,
test status, recent evidence, activity timeline.
Short tabs: Overview, Evidence, Hypotheses, Tests, Patch, Verify, Report, Activity.
Dense but calm and scannable. No fabricated progress or unverified success.
```

### Stitch 07 --- Reproduction

``` text
Create Reproduction tab. Show status, timestamp, browser/runtime profile, run ID.
Large browser screenshot preview, ordered reproduction steps,
side panel with console events, failed requests, trace metadata.
Action Run again only as permitted. States: Reproduced, Not reproduced, Blocked, Inconclusive.
```

### Stitch 08 --- Evidence explorer

``` text
Create Evidence explorer. Filters: All, Images, Console, Network, Logs, Tests, Source.
Evidence rows/cards show ID, type icon, title, timestamp, origin stage.
Selected detail panel shows screenshot/log preview, source metadata, tool run,
snapshot, related hypothesis, authorized download.
Separate raw evidence from AI summaries.
```

### Stitch 09 --- Hypothesis review

``` text
Create Hypothesis review. Left compact list with H-001, short title, status, evidence count.
Right detail: hypothesis statement, confidence rationale, supporting evidence,
contradicting evidence, missing information, next step.
Neutral/sage styling for proposed hypotheses, not verified-success green.
```

### Stitch 10 --- Regression tests

``` text
Create Regression tests. List: test name, framework, baseline status, latest status.
Detail: purpose, code preview, file path, validation, command profile,
duration, exit code, logs. Actions Review proposal, Run baseline, View logs.
Distinguish proposed from executed tests.
```

### Stitch 11 --- Patch review

``` text
Create professional Patch review. Header: patch ID, status, base snapshot hash,
diff hash, changed files, added/deleted line counts.
Left changed-files list, center syntax-highlighted diff, right explanation,
related hypothesis, evidence, risk, limitations.
Sticky footer: Approve patch and Reject.
Approval should feel deliberate. Do not show patch as applied before approval.
```

### Stitch 12 --- Verification

``` text
Create Verification screen. Aggregate status and counts: passed, failed, blocked,
skipped, timed out. List regression test, type check, lint, build.
Each row shows status, duration, exit code, View logs.
Show baseline vs post-patch where available.
Include note that verification covers only checks executed in the recorded environment.
No success styling if required checks did not pass.
```

### Stitch 13 --- Report

``` text
Create Investigation report with title, final status, project/snapshot metadata,
export menu. Sections: Issue summary, Reproduction, Observations, Hypotheses,
Evidence, Regression tests, Baseline, Patch and approval, Post-patch verification,
Limitations, Timeline. Compact section navigation and audit-friendly typography.
```

### Stitch 14 --- Settings

``` text
Create Meridian settings with compact navigation: Profile, Preferences, Security, Usage.
Show Preferences: theme System/Dark/Light, reduced motion, timezone if supported.
Use Sage & Bone, compact labels, short forms.
```

## 16.3 Stitch workflow

1.  Generate shared design foundation.
2.  Generate landing page.
3.  Generate workspace shell/dashboard.
4.  Generate project list and onboarding.
5.  Generate investigation workspace.
6.  Generate evidence, hypotheses, tests, patch, verification, report.
7.  Generate authentication and settings.
8.  Review every screen against this document.
9.  Reuse tokens/components in refinements.
10. Implement exported designs with real APIs.

Stitch mock data is design-only and must never become production data.

------------------------------------------------------------------------

# 17. Design-to-development handoff

For every screen, handoff must specify: - Screen ID and route. - Purpose
and primary user task. - Desktop layout. - Responsive behavior. -
Components. - Exact content/microcopy. - Data fields and backend
source. - Loading, empty, error, blocked, and permission states. -
Interactions and animation. - Accessibility notes. - Acceptance
criteria.

Build reusable components rather than one-off pages.

## Data integrity in the UI

-   Use real API data.
-   Show loading while fetching.
-   Show zero when a count is truly zero.
-   Use "Not available" only when data is genuinely unavailable.
-   Never turn missing data into success.
-   Keep raw evidence separate from model interpretation.
-   Display timestamps/statuses from persisted backend records.

------------------------------------------------------------------------

# 18. Design acceptance checklist

## Visual

-   [ ] Exact Sage & Bone palette in both themes.
-   [ ] Dark is default for workspace.
-   [ ] Light matches supplied bone/sage reference.
-   [ ] Consistent typography and spacing.
-   [ ] Compact tabs and sidebar.
-   [ ] No uncontrolled gradients/glows.

## Screens

-   [ ] Landing and public pages.
-   [ ] Authentication.
-   [ ] Workspace dashboard.
-   [ ] Project list and onboarding.
-   [ ] Investigation creation and workspace.
-   [ ] Reproduction.
-   [ ] Evidence explorer.
-   [ ] Hypothesis review.
-   [ ] Regression tests.
-   [ ] Patch review/approval.
-   [ ] Verification.
-   [ ] Report and activity.
-   [ ] Settings.
-   [ ] Error states.

## Interaction

-   [ ] Complete control states.
-   [ ] Working tabs/navigation.
-   [ ] Accessible dialogs/drawers.
-   [ ] Progress reflects backend.
-   [ ] Approval binds to exact patch/snapshot.
-   [ ] Downloads are authorized.
-   [ ] Theme persists.
-   [ ] Reduced motion works.

## Product truthfulness

-   [ ] No fake activity.
-   [ ] No fabricated metrics.
-   [ ] Proposed patch is not shown as applied.
-   [ ] Hypothesis is not shown as fact.
-   [ ] Skipped test is not shown as passed.
-   [ ] Unmonitored service is not shown as healthy.

------------------------------------------------------------------------

# 19. Recommended UI implementation order

    Order Screens                           Reason
  ------- --------------------------------- --------------------------
        1 Tokens and component foundation   Consistency
        2 Workspace shell/dashboard         Navigation foundation
        3 Project list/onboarding           Project workflow
        4 Investigation creation            Input flow
        5 Investigation workspace           Core product
        6 Reproduction/evidence             Evidence experience
        7 Hypotheses/tests                  Reasoning and validation
        8 Patch review                      Human approval
        9 Verification/report               End-to-end outcome
       10 Auth/settings polish              Account experience
       11 Public marketing pages            Product presentation

Authentication and authorization must be implemented before protected
workspace use, even if visual polish is parallelized.

------------------------------------------------------------------------

# 20. Final design rule

Meridian should feel like a calm, precise engineering workspace. Its
visual identity is Sage & Bone: bone/cream in light mode, night/moss in
dark mode, ink/pale text, restrained sage accents, and semantic status
colors.

The highest-priority screens are: 1. Investigation Workspace. 2.
Evidence Explorer. 3. Hypothesis Review. 4. Patch Review. 5.
Verification.

The most important rule is:

**Make the truth of the investigation visible: what was observed, what
is inferred, what is proposed, what the user approved, and what was
actually verified.**

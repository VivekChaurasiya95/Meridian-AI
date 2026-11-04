"use client";

import * as React from "react";
import Link from "next/link";
import { motion, useReducedMotion, useScroll, useSpring } from "framer-motion";
import {
  Archive,
  ArrowRight,
  BookOpen,
  Check,
  Copy,
  Database,
  FileSearch,
  Fingerprint,
  FlaskConical,
  FolderKanban,
  KeyRound,
  Layers,
  Lock,
  Play,
  ScanSearch,
  ShieldCheck,
  Users,
  Workflow,
} from "lucide-react";
import { MeridianLogo } from "@/components/brand/Logo";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { Badge } from "@/components/ui/Badge";
import { Reveal } from "@/components/ui/Reveal";
import { RotatingWord, StaggerHeadline } from "@/components/ui/AnimatedHeadline";
import { cn } from "@/lib/cn";

const SECTIONS = [
  { id: "overview", label: "Overview", icon: BookOpen },
  { id: "quickstart", label: "Quickstart", icon: Play },
  { id: "concepts", label: "Core concepts", icon: Layers },
  { id: "pipeline", label: "Investigation pipeline", icon: Workflow },
  { id: "evidence", label: "Evidence & verification", icon: FileSearch },
  { id: "security", label: "Security & isolation", icon: ShieldCheck },
  { id: "reference", label: "Reference", icon: Database },
  { id: "faq", label: "FAQ", icon: Fingerprint },
] as const;

const HERO_WORDS = ["reproduced.", "evidenced.", "verified.", "approved by you."];

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-center gap-3 font-mono text-xs font-medium text-sage">
      <span aria-hidden="true" className="h-px w-8 bg-sage" />
      {children}
    </p>
  );
}

function SectionHeading({
  index,
  title,
  lede,
  headingId,
}: {
  index: string;
  title: string;
  lede: string;
  headingId: string;
}) {
  return (
    <Reveal className="max-w-2xl">
      <Eyebrow>{index}</Eyebrow>
      <h2 id={headingId} className="font-display mt-5 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
        {title}
      </h2>
      <p className="mt-4 text-[15px] leading-7 text-ink-2">{lede}</p>
    </Reveal>
  );
}

function Callout({
  tone,
  title,
  children,
}: {
  tone: "sage" | "warning" | "info";
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-surface-1 p-5 shadow-card",
        tone === "sage" && "border-sage/30",
        tone === "warning" && "border-warning/30",
        tone === "info" && "border-info/30",
      )}
    >
      <p className="flex items-center gap-2 text-[13px] font-semibold text-ink">
        <ShieldCheck
          aria-hidden="true"
          className={cn(
            "size-4",
            tone === "sage" && "text-sage",
            tone === "warning" && "text-warning",
            tone === "info" && "text-info",
          )}
        />
        {title}
      </p>
      <div className="mt-2 text-sm leading-6 text-ink-2">{children}</div>
    </div>
  );
}

function CodeBlock({ title, code }: { title: string; code: string }) {
  const [copied, setCopied] = React.useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }
  return (
    <figure className="overflow-hidden rounded-xl border border-line bg-ink text-canvas shadow-card dark:bg-surface-1 dark:text-ink">
      <div className="flex items-center justify-between gap-3 border-b border-line/40 px-4 py-2.5">
        <figcaption className="truncate font-mono text-[11px] tracking-wide opacity-70">
          {title}
        </figcaption>
        <button
          type="button"
          onClick={copy}
          className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 font-mono text-[11px] font-medium opacity-70 transition-opacity hover:opacity-100"
          aria-live="polite"
        >
          {copied ? <Check aria-hidden="true" className="size-3.5" /> : <Copy aria-hidden="true" className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-[12.5px] leading-6">
        <code>{code}</code>
      </pre>
    </figure>
  );
}

function useActiveSection(ids: readonly string[]) {
  const [active, setActive] = React.useState(ids[0]);
  React.useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { rootMargin: "-30% 0px -60% 0px" },
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [ids]);
  return active;
}

const QUICKSTART_STEPS = [
  {
    title: "Create an account and sign in",
    body: "Sign up with email and password, or continue with Google or GitHub where offered. Sessions last 24 hours of idle time and are stored in a secure, HttpOnly cookie — sign in once and the workspace remembers you.",
  },
  {
    title: "Make a workspace",
    body: "A workspace is your team's shared home. Give it a name and a slug, then invite teammates by email with a role: owner, admin, developer, or viewer. Every project and investigation lives inside exactly one workspace.",
  },
  {
    title: "Add your first codebase",
    body: "Upload a ZIP archive (validated and inspected on the way in) or connect a public GitHub repository, which is pinned to an exact commit. Either path produces an immutable snapshot — a frozen, content-addressed copy of the code under investigation.",
  },
  {
    title: "File a report and follow the evidence",
    body: "Describe the failure: what you expected, what happened instead, and how to reach it. Meridian reproduces it in an isolated sandbox, captures screenshots, console output, and network traces, then proposes hypotheses that cite that evidence — never bare assertions.",
  },
  {
    title: "Review the diff, approve the fix",
    body: "A regression test is drafted against the unchanged code first; then a minimal patch is proposed. You review the exact diff — files, lines, hashes, risks — and approve or reject it. Nothing is applied, pushed, or deployed without you.",
  },
];

const PIPELINE_STAGES = [
  {
    n: "01",
    title: "Report",
    body: "A structured bug report: expected vs actual behavior, reproduction steps, and the failing route. This is the contract every later stage is checked against.",
    outcome: "A written failure contract",
  },
  {
    n: "02",
    title: "Reproduce",
    body: "The pinned snapshot is started in an isolated sandbox while automation attempts the reported failure. Flaky or environment-specific bugs surface here, not in production.",
    outcome: "A replayed failure, or an honest cannot-reproduce",
  },
  {
    n: "03",
    title: "Evidence",
    body: "Screenshots, console errors, failed network requests, traces, and logs are captured as linked artifacts. Each artifact carries an ID that later claims must cite.",
    outcome: "Numbered, inspectable artifacts",
  },
  {
    n: "04",
    title: "Hypothesize",
    body: "Candidate root causes are proposed with citations to specific evidence IDs. A hypothesis without a citation is labeled a guess — visible, but never load-bearing.",
    outcome: "Ranked hypotheses with citations",
  },
  {
    n: "05",
    title: "Test & patch",
    body: "A regression test is proposed and run against the unchanged baseline to prove it captures the bug. Only then is a minimal patch drafted to turn that test green.",
    outcome: "A failing-then-passing test plus a minimal diff",
  },
  {
    n: "06",
    title: "Approve",
    body: "You review the exact diff — files, lines, content hashes, risks — and explicitly approve or reject it. Approval is a deliberate human act, not a default.",
    outcome: "Your decision, recorded",
  },
  {
    n: "07",
    title: "Verify & report",
    body: "Post-patch checks run in isolation and the final status comes from real results: fixed, partially fixed, blocked, or inconclusive — stated plainly either way.",
    outcome: "A verdict grounded in runs, not confidence",
  },
];

export function DocsClient() {
  const reduceMotion = useReducedMotion();
  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 28, mass: 0.4 });
  const ids = React.useMemo(() => SECTIONS.map((s) => s.id), []);
  const active = useActiveSection(ids);
  const [tab, setTab] = React.useState<"zip" | "git">("zip");
  const [openFaq, setOpenFaq] = React.useState<number | null>(0);

  return (
    <div className="texture-grain min-h-screen bg-canvas">
      <motion.div
        aria-hidden="true"
        style={reduceMotion ? undefined : { scaleX: progress }}
        className="fixed inset-x-0 top-0 z-50 h-0.5 origin-left bg-sage"
      />
      {/* Top navigation */}
      <header className="sticky top-0 z-40 border-b border-line/70 bg-canvas/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-2 px-4 sm:px-6">
          <Link href="/" aria-label="Meridian home">
            <MeridianLogo markSize={26} />
          </Link>
          <nav aria-label="Site" className="ml-10 hidden items-center gap-7 text-[13px] font-semibold text-ink-2 md:flex">
            <Link href="/#workflow" className="underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60">Workflow</Link>
            <Link href="/#principles" className="underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60">Principles</Link>
            <Link href="/docs" aria-current="page" className="text-ink underline decoration-sage/60 decoration-2 underline-offset-4">Documentation</Link>
            <Link href="/#faq" className="underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60">FAQ</Link>
            <Link href="/developer" className="underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60">Developer</Link>
          </nav>
          <span className="ml-auto flex items-center gap-2.5">
            <ThemeToggle />
            <Link
              href="/app"
              className="group inline-flex h-9 items-center gap-1.5 rounded-[10px] bg-accent px-3.5 text-[13px] font-semibold text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_8px_20px_-8px_var(--color-accent)] transition-all duration-200 hover:bg-accent-hover active:scale-[0.98]"
            >
              Open workspace
              <ArrowRight aria-hidden="true" className="size-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
            </Link>
          </span>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div aria-hidden="true" className="texture-dots pointer-events-none absolute inset-0 opacity-60 [mask-image:radial-gradient(ellipse_70%_60%_at_30%_20%,black,transparent)]" />
          <div className="relative mx-auto w-full max-w-6xl px-4 pt-14 pb-10 sm:px-6 md:pt-20">
            <Eyebrow>Documentation · The whole product, one page</Eyebrow>
            <h1 className="font-display mt-6 max-w-3xl text-[38px] leading-[1.05] font-semibold tracking-tight text-balance sm:text-[54px]">
              <StaggerHeadline text="Bug reports in." />
              <br />
              <span className="text-ink-2">
                <StaggerHeadline text="Investigations out." delay={0.25} />
              </span>{" "}
              <em className="text-sage not-italic">
                <RotatingWord words={HERO_WORDS} />
              </em>
            </h1>
            <Reveal delay={0.35}>
              <p className="mt-6 max-w-2xl text-[15px] leading-7 text-ink-2">
                Meridian AI turns a bug report into a structured, evidence-backed investigation:
                it reproduces the failure in isolation, captures every artifact, proposes
                hypotheses tied to that evidence, and verifies each patch with real test runs —
                with a human approving every change. This page documents the complete product:
                concepts, workflow, security model, and reference.
              </p>
            </Reveal>
            <Reveal delay={0.45}>
              <div className="mt-7 flex flex-wrap items-center gap-2.5">
                <Badge>Product docs</Badge>
                <Badge dot={false}>7-stage pipeline</Badge>
                <Badge dot={false}>Evidence-first</Badge>
                <Badge dot={false}>Human-approved patches</Badge>
              </div>
            </Reveal>
            <Reveal delay={0.5}>
              <div className="mt-7 flex flex-wrap gap-3">
                <a href="#quickstart" className="inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-[15px] font-semibold text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_12px_28px_-10px_var(--color-accent)] transition-all duration-200 hover:bg-accent-hover active:scale-[0.98]">
                  Start in 5 steps
                  <ArrowRight aria-hidden="true" className="size-4" />
                </a>
                <a href="#pipeline" className="inline-flex h-11 items-center rounded-xl border border-line bg-surface-1 px-5 text-[15px] font-semibold text-ink-2 shadow-card transition-all duration-200 hover:border-line-strong hover:text-ink">
                  How investigations work
                </a>
              </div>
            </Reveal>
          </div>
        </section>

        {/* Mobile section chips */}
        <div className="sticky top-16 z-30 border-b border-line/70 bg-canvas/90 backdrop-blur-xl lg:hidden">
          <nav aria-label="Documentation sections" className="mx-auto flex w-full max-w-6xl gap-2 overflow-x-auto px-4 py-3 sm:px-6">
            {SECTIONS.map((s) => (
              <a
                key={s.id}
                href={`#${s.id}`}
                aria-current={active === s.id ? "true" : undefined}
                className={cn(
                  "shrink-0 rounded-full border px-3.5 py-1.5 text-[13px] font-semibold whitespace-nowrap transition-colors",
                  active === s.id
                    ? "border-sage/50 bg-sage-subtle text-ink"
                    : "border-line bg-surface-1 text-ink-2",
                )}
              >
                {s.label}
              </a>
            ))}
          </nav>
        </div>

        <div className="mx-auto grid w-full max-w-6xl gap-12 px-4 py-12 sm:px-6 md:py-16 lg:grid-cols-[240px_minmax(0,1fr)]">
          {/* Sidebar */}
          <aside className="hidden lg:block">
            <nav aria-label="Documentation sections" className="sticky top-24 flex flex-col gap-1">
              <p className="mb-2 font-mono text-[11px] font-medium tracking-[0.14em] text-ink-3 uppercase">
                On this page
              </p>
              {SECTIONS.map((s, i) => (
                <a
                  key={s.id}
                  href={`#${s.id}`}
                  aria-current={active === s.id ? "true" : undefined}
                  className={cn(
                    "group flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors",
                    active === s.id ? "bg-sage-subtle text-ink" : "text-ink-2 hover:bg-surface-1 hover:text-ink",
                  )}
                >
                  <span className={cn("font-mono text-[11px]", active === s.id ? "text-sage" : "text-ink-3")}>
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <s.icon aria-hidden="true" className="size-4 opacity-60" />
                  {s.label}
                </a>
              ))}
              <div className="mt-6 rounded-xl border border-sage/30 bg-surface-1 p-4 shadow-card">
                <p className="text-[13px] font-semibold text-ink">New to Meridian?</p>
                <p className="mt-1 text-[13px] leading-6 text-ink-2">
                  The Quickstart takes you from signup to your first verified fix.
                </p>
                <a href="#quickstart" className="mt-2 inline-flex items-center gap-1 text-[13px] font-semibold text-sage hover:opacity-75">
                  Jump in <ArrowRight aria-hidden="true" className="size-3.5" />
                </a>
              </div>
            </nav>
          </aside>

          <div className="flex min-w-0 flex-col gap-16 md:gap-20">
            {/* 01 Overview */}
            <section id="overview" aria-labelledby="overview-h" className="scroll-mt-36">
              <SectionHeading
                index="01 · Overview"
                headingId="overview-h"
                title="What Meridian is, and who it is for."
                lede="Meridian is an AI-assisted debugging and reliability platform. Instead of answering from the report alone, it runs the failing code, watches it fail, keeps the receipts, and proves the fix — with you in charge at every step."
              />
              <div className="mt-8 grid gap-4 sm:grid-cols-3">
                {[
                  { icon: ScanSearch, title: "Reproduces first", body: "The failure is replayed in an isolated sandbox before anyone theorizes about it." },
                  { icon: FileSearch, title: "Evidence over assertion", body: "Screenshots, logs, and traces are linked artifacts. Claims cite them or say so." },
                  { icon: KeyRound, title: "You approve patches", body: "No diff is applied, pushed, or deployed without your explicit review." },
                ].map((c, i) => (
                  <Reveal key={c.title} delay={Math.min(i * 0.07, 0.2)}>
                    <div className="h-full rounded-xl border border-line bg-surface-1 p-5 shadow-card">
                      <span className="flex size-9 items-center justify-center rounded-lg bg-sage-subtle text-sage">
                        <c.icon aria-hidden="true" className="size-4.5" />
                      </span>
                      <h3 className="mt-4 text-[15px] font-semibold text-ink">{c.title}</h3>
                      <p className="mt-1.5 text-sm leading-6 text-ink-2">{c.body}</p>
                    </div>
                  </Reveal>
                ))}
              </div>
              <Reveal className="mt-6">
                <Callout tone="sage" title="Who it serves">
                  Engineering teams who fix user-facing bugs in web applications: developers file
                  precise reports, reviewers see exactly what was observed versus guessed, and
                  approvers sign off on diffs backed by passing test runs — not model confidence.
                </Callout>
              </Reveal>
            </section>

            {/* 02 Quickstart */}
            <section id="quickstart" aria-labelledby="quickstart-h" className="scroll-mt-36">
              <SectionHeading
                index="02 · Quickstart"
                headingId="quickstart-h"
                title="From signup to verified fix in five steps."
                lede="The shortest path through the whole product. Each step below maps to a real screen in the workspace — nothing here is conceptual."
              />
              <ol className="mt-8 flex flex-col">
                {QUICKSTART_STEPS.map((step, i) => (
                  <Reveal as="li" key={step.title} delay={Math.min(i * 0.04, 0.2)}>
                    <div className="group flex gap-5 border-t border-line/70 py-6 last:border-b sm:gap-7 sm:px-4">
                      <span className="font-display tnum w-10 shrink-0 text-2xl font-semibold text-line-strong transition-colors duration-200 group-hover:text-sage">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block font-semibold text-ink">{step.title}</span>
                        <span className="mt-1 block text-[14.5px] leading-7 text-ink-2">{step.body}</span>
                      </span>
                    </div>
                  </Reveal>
                ))}
              </ol>
              <Reveal className="mt-6">
                <div className="flex flex-wrap gap-3">
                  <Link href="/signup" className="inline-flex h-11 items-center rounded-xl bg-accent px-5 text-[15px] font-semibold text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_12px_28px_-10px_var(--color-accent)] transition-all duration-200 hover:bg-accent-hover active:scale-[0.98]">
                    Create an account
                  </Link>
                  <Link href="/app" className="inline-flex h-11 items-center rounded-xl border border-line bg-surface-1 px-5 text-[15px] font-semibold text-ink-2 shadow-card transition-all duration-200 hover:border-line-strong hover:text-ink">
                    Open the workspace
                  </Link>
                </div>
              </Reveal>
            </section>

            {/* 03 Core concepts */}
            <section id="concepts" aria-labelledby="concepts-h" className="scroll-mt-36">
              <SectionHeading
                index="03 · Core concepts"
                headingId="concepts-h"
                title="Five ideas that explain everything."
                lede="Workspaces hold people, projects hold code, snapshots freeze it, investigations examine it, and jobs do the work. Learn these five and the entire product clicks into place."
              />
              <div className="mt-8 flex flex-col gap-4">
                {[
                  {
                    icon: Users,
                    title: "Workspaces & roles",
                    body: "A workspace is a team's shared home: it holds projects, investigations, and members. Invite anyone by email with a role — owner, admin, developer, or viewer — and every screen, action, and API response respects that role. Foreign workspaces simply don't exist for you: their projects return not-found, never forbidden, so membership can't be probed.",
                  },
                  {
                    icon: FolderKanban,
                    title: "Projects & sources",
                    body: "A project is one codebase under investigation. Add it from a ZIP archive or a public GitHub repository. Uploads are validated on the way in — archive type, size, depth, file count, symlinks, secrets — and Git sources are grammar-checked to canonical https://github.com/owner/repo form, then pinned to the exact commit that was fetched.",
                  },
                  {
                    icon: Archive,
                    title: "Snapshots: frozen, hashed, immutable",
                    body: "Every import produces a snapshot: a deterministic tarball whose SHA-256 digest addresses its content, alongside a manifest of files, sizes, and hashes plus small text previews for the index. Snapshots never change after creation — a later import is a new snapshot, so any investigation can always point at the exact bytes it examined.",
                  },
                  {
                    icon: FlaskConical,
                    title: "Investigations in seven stages",
                    body: "An investigation walks the pipeline below — report, reproduce, evidence, hypothesize, test & patch, approve, verify — persisting its inputs and outputs at every stage. You can open it at any point and see the reproduction, the artifacts, and the reasoning, not just the conclusion.",
                  },
                  {
                    icon: Layers,
                    title: "Jobs: durable background work",
                    body: "Reproductions, previews, and imports run as jobs on a durable queue: claimed with leases, kept alive with heartbeats, retried with backoff, and deduplicated with idempotency keys. Terminal states are final — a completed job never runs again — and every attempt leaves a stage trail you can audit.",
                  },
                ].map((c, i) => (
                  <Reveal key={c.title} delay={Math.min(i * 0.04, 0.16)}>
                    <div className="flex gap-4 rounded-xl border border-line bg-surface-1 p-5 shadow-card sm:gap-5 sm:p-6">
                      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-sage-subtle text-sage">
                        <c.icon aria-hidden="true" className="size-5" />
                      </span>
                      <div className="min-w-0">
                        <h3 className="text-[16px] font-semibold text-ink">{c.title}</h3>
                        <p className="mt-1.5 text-[14.5px] leading-7 text-ink-2">{c.body}</p>
                      </div>
                    </div>
                  </Reveal>
                ))}
              </div>
              <Reveal className="mt-6">
                <Callout tone="info" title="Two ways to bring code">
                  Prefer archives for private or in-progress code — nothing is fetched, only what you
                  upload is inspected. Prefer Git for public repositories you want pinned to a commit,
                  with branch previews before import. Both converge on the same immutable snapshot.
                </Callout>
              </Reveal>
              {/* Source tabs */}
              <Reveal className="mt-6">
                <div className="overflow-hidden rounded-xl border border-line bg-surface-1 shadow-card">
                  <div role="tablist" aria-label="Source comparison" className="flex gap-1 border-b border-line/70 p-2">
                    {(
                      [
                        { key: "zip", label: "ZIP archive" },
                        { key: "git", label: "Git repository" },
                      ] as const
                    ).map((t) => (
                      <button
                        key={t.key}
                        role="tab"
                        aria-selected={tab === t.key}
                        onClick={() => setTab(t.key)}
                        className={cn(
                          "h-9 flex-1 rounded-lg text-[14px] font-semibold transition-colors",
                          tab === t.key ? "bg-sage-subtle text-ink" : "text-ink-3 hover:text-ink",
                        )}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>
                  <div className="p-5 sm:p-6">
                    {tab === "zip" ? (
                      <div className="text-[14px] leading-7 text-ink-2">
                        <p><strong className="text-ink">Best for:</strong> private code, local prototypes, exact trees you already have.</p>
                        <p className="mt-2"><strong className="text-ink">What happens:</strong> the archive is type-checked, size- and depth-limited, extracted to a temporary directory, stripped of skip-dirs and secrets from the index, hashed into a snapshot tarball, and verified by re-reading its digest before anything is committed.</p>
                        <p className="mt-2"><strong className="text-ink">Limits:</strong> 25&nbsp;MB archives, 5,000 files, secret files (like .env) never enter the index.</p>
                      </div>
                    ) : (
                      <div className="text-[14px] leading-7 text-ink-2">
                        <p><strong className="text-ink">Best for:</strong> public GitHub repositories you want tracked to an exact commit.</p>
                        <p className="mt-2"><strong className="text-ink">What happens:</strong> the URL is validated as pure grammar (no network), a preview job lists real branches from the remote, you pick a branch, and the import fetches exactly one ref with a shallow, submodule-free, redirect-refusing clone — pinned to the resulting commit SHA.</p>
                        <p className="mt-2"><strong className="text-ink">Limits:</strong> public GitHub HTTPS only; submodules and LFS are refused with a clear message.</p>
                      </div>
                    )}
                  </div>
                </div>
              </Reveal>
            </section>

            {/* 04 Pipeline */}
            <section id="pipeline" aria-labelledby="pipeline-h" className="scroll-mt-36">
              <SectionHeading
                index="04 · Investigation pipeline"
                headingId="pipeline-h"
                title="One pipeline, from report to verified fix."
                lede="Every stage persists its inputs and outputs, so nothing is a black box. Follow a report through all seven stages to see how raw failure becomes a fix you can trust."
              />
              <ol className="mt-8 flex flex-col">
                {PIPELINE_STAGES.map((stage, i) => (
                  <Reveal as="li" key={stage.n} delay={Math.min(i * 0.03, 0.18)}>
                    <div className="group grid gap-3 border-t border-line/70 py-6 transition-colors duration-200 last:border-b hover:bg-surface-1/60 sm:grid-cols-[3rem_1fr] sm:gap-6 sm:px-4">
                      <span className="font-display tnum text-2xl font-semibold text-line-strong transition-colors duration-200 group-hover:text-sage">
                        {stage.n}
                      </span>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                          <h3 className="text-[17px] font-semibold text-ink">{stage.title}</h3>
                          <span className="font-mono text-[12px] text-sage">{stage.outcome}</span>
                        </div>
                        <p className="mt-1.5 max-w-2xl text-[14.5px] leading-7 text-ink-2">{stage.body}</p>
                      </div>
                    </div>
                  </Reveal>
                ))}
              </ol>
              <Reveal className="mt-6">
                <Callout tone="warning" title="Honest terminal states">
                  Not every investigation ends in a fix. Blocked, inconclusive, and timed-out
                  outcomes are preserved as first-class results — never quietly rounded up to
                  success. A shrug is a valid, visible answer, and it tells you exactly what to try next.
                </Callout>
              </Reveal>
            </section>

            {/* 05 Evidence & verification */}
            <section id="evidence" aria-labelledby="evidence-h" className="scroll-mt-36">
              <SectionHeading
                index="05 · Evidence & verification"
                headingId="evidence-h"
                title="Proof is a structure, not a feeling."
                lede="Every claim Meridian makes is traceable to something it actually observed. This is the machinery that keeps guesses and facts from blending together."
              />
              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                {[
                  { icon: FileSearch, title: "Linked artifacts", body: "Screenshots, console output, failed requests, traces, and logs are stored with IDs. Nothing important is described purely in prose — it is pointed at." },
                  { icon: ScanSearch, title: "Cited hypotheses", body: "Each hypothesis names the evidence IDs behind it and is ranked. An idea with no citation stays visible, but marked as a guess." },
                  { icon: FlaskConical, title: "Baseline-first tests", body: "The regression test runs against the unchanged snapshot first, proving it captures the bug. A test that can't fail before the fix can't prove anything after it." },
                  { icon: KeyRound, title: "Minimal, reviewable diffs", body: "Patches stay small and scoped to the failure. You see files, line ranges, content hashes, and risks — then decide." },
                ].map((c, i) => (
                  <Reveal key={c.title} delay={Math.min(i * 0.07, 0.2)}>
                    <div className="h-full rounded-xl border border-line bg-surface-1 p-5 shadow-card">
                      <span className="flex size-9 items-center justify-center rounded-lg bg-sage-subtle text-sage">
                        <c.icon aria-hidden="true" className="size-4.5" />
                      </span>
                      <h3 className="mt-4 text-[15px] font-semibold text-ink">{c.title}</h3>
                      <p className="mt-1.5 text-sm leading-6 text-ink-2">{c.body}</p>
                    </div>
                  </Reveal>
                ))}
              </div>
              <Reveal className="mt-6">
                <CodeBlock
                  title="evidence-chain.json — what a verified fix points at"
                  code={`{
  "report": "login refresh returns 500 for expired sessions",
  "reproduction": "job 8f31… · status completed · sandbox run #3",
  "artifacts": ["shot-03 (console 500)", "trace-07 (failed POST /refresh)"],
  "hypothesis": "H-2 — stale token reuse (cites trace-07, log-11)",
  "regression_test": "fails on snapshot a3f9c1, passes after patch",
  "patch": "auth/refresh.ts +14 −6 · sha 9be2… · approved by you",
  "verdict": "fixed — post-patch run completed in isolation"
}`}
                />
              </Reveal>
            </section>

            {/* 06 Security */}
            <section id="security" aria-labelledby="security-h" className="scroll-mt-36">
              <SectionHeading
                index="06 · Security & isolation"
                headingId="security-h"
                title="Untrusted code never gets a chance."
                lede="Your code is treated as evidence to examine, never as software to trust. Execution happens in a disposable sandbox; the main application only ever handles validated data."
              />
              <div className="mt-8 flex flex-col gap-4">
                {[
                  { icon: Lock, title: "Sandboxed execution", body: "Reproductions run in a separate, resource-limited worker with an allowlisted container profile — never in the API process, never on your machine. Execution containers hold no credentials at all; the worker holds only the read-only access it needs, and every run is cleaned up afterward." },
                  { icon: ShieldCheck, title: "Fetch-time defenses", body: "Git imports resolve the remote once, reject any non-public address (loopback, private ranges, link-local, metadata endpoints), refuse redirects, and pin the connection to the verified address. Malformed URLs, embedded credentials, submodules, and LFS pointers are rejected with clear errors before any fetch begins." },
                  { icon: Fingerprint, title: "Secrets stay out", body: "Credential files, environment files, and dependency directories are excluded from every index. Archives are rejected for symlinks, absolute paths, and traversal entries; snapshots are re-verified by digest on read-back." },
                  { icon: Users, title: "Identity & tenancy", body: "Email/password auth uses salted hashes and opaque session tokens over HttpOnly cookies; Google/GitHub sign-in is exchanged server-side for the same session. Workspace roles gate every action, and resources outside your membership are indistinguishable from nonexistent." },
                ].map((c, i) => (
                  <Reveal key={c.title} delay={Math.min(i * 0.04, 0.16)}>
                    <div className="flex gap-4 rounded-xl border border-line bg-surface-1 p-5 shadow-card sm:gap-5 sm:p-6">
                      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-sage-subtle text-sage">
                        <c.icon aria-hidden="true" className="size-5" />
                      </span>
                      <div className="min-w-0">
                        <h3 className="text-[16px] font-semibold text-ink">{c.title}</h3>
                        <p className="mt-1.5 text-[14.5px] leading-7 text-ink-2">{c.body}</p>
                      </div>
                    </div>
                  </Reveal>
                ))}
              </div>
            </section>

            {/* 07 Reference */}
            <section id="reference" aria-labelledby="reference-h" className="scroll-mt-36">
              <SectionHeading
                index="07 · Reference"
                headingId="reference-h"
                title="The facts, tabulated."
                lede="Roles, job types, limits, and the shape of the API — everything you need when the prose above isn't precise enough."
              />
              <Reveal className="mt-8">
                <h3 className="text-[16px] font-semibold text-ink">Workspace roles</h3>
                <div className="mt-3 overflow-x-auto rounded-xl border border-line bg-surface-1 shadow-card">
                  <table className="w-full min-w-[520px] text-left text-[13.5px]">
                    <thead>
                      <tr className="border-b border-line/70 font-mono text-[11px] tracking-wide text-ink-3 uppercase">
                        <th scope="col" className="px-4 py-3 font-medium">Role</th>
                        <th scope="col" className="px-4 py-3 font-medium">Projects & imports</th>
                        <th scope="col" className="px-4 py-3 font-medium">Members & roles</th>
                        <th scope="col" className="px-4 py-3 font-medium">Investigations</th>
                      </tr>
                    </thead>
                    <tbody className="text-ink-2">
                      {[
                        ["Owner", "Full control", "Manage all roles", "Approve patches"],
                        ["Admin", "Full control", "Manage developers & viewers", "Approve patches"],
                        ["Developer", "Create & import", "—", "Run & propose"],
                        ["Viewer", "Read", "—", "Read & comment"],
                      ].map((row) => (
                        <tr key={row[0]} className="border-b border-line/50 last:border-0">
                          <th scope="row" className="px-4 py-3 font-semibold text-ink">{row[0]}</th>
                          <td className="px-4 py-3">{row[1]}</td>
                          <td className="px-4 py-3">{row[2]}</td>
                          <td className="px-4 py-3">{row[3]}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Reveal>
              <Reveal className="mt-8">
                <h3 className="text-[16px] font-semibold text-ink">Job types</h3>
                <div className="mt-3 overflow-x-auto rounded-xl border border-line bg-surface-1 shadow-card">
                  <table className="w-full min-w-[520px] text-left text-[13.5px]">
                    <thead>
                      <tr className="border-b border-line/70 font-mono text-[11px] tracking-wide text-ink-3 uppercase">
                        <th scope="col" className="px-4 py-3 font-medium">Job</th>
                        <th scope="col" className="px-4 py-3 font-medium">What it does</th>
                        <th scope="col" className="px-4 py-3 font-medium">Result</th>
                      </tr>
                    </thead>
                    <tbody className="text-ink-2">
                      {[
                        ["git_preview", "Lists real branches on the remote", "Branch names + HEAD SHAs"],
                        ["git_import", "Fetches one ref, builds a snapshot", "Immutable snapshot + commit SHA"],
                        ["lifecycle_test", "Smoke-checks the pipeline", "Pass / fail with stages"],
                        ["manifest_recheck", "Re-verifies a snapshot manifest", "Digest verification report"],
                        ["sandbox_smoke", "Proves the sandbox is healthy", "Sandbox readiness signal"],
                      ].map((row) => (
                        <tr key={row[0]} className="border-b border-line/50 last:border-0">
                          <th scope="row" className="px-4 py-3 font-mono text-[12.5px] font-medium text-ink">{row[0]}</th>
                          <td className="px-4 py-3">{row[1]}</td>
                          <td className="px-4 py-3">{row[2]}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Reveal>
              <Reveal className="mt-8">
                <h3 className="text-[16px] font-semibold text-ink">Practical limits</h3>
                <ul className="mt-3 grid gap-2.5 sm:grid-cols-2">
                  {[
                    ["25 MB", "Max ZIP archive size"],
                    ["5,000", "Max files per archive"],
                    ["120 s", "Git fetch timeout"],
                    ["24 h", "Session idle lifetime"],
                  ].map(([value, label]) => (
                    <li key={label} className="flex items-baseline gap-3 rounded-xl border border-line bg-surface-1 px-4 py-3 shadow-card">
                      <span className="font-display text-xl font-semibold text-ink">{value}</span>
                      <span className="text-[13px] text-ink-3">{label}</span>
                    </li>
                  ))}
                </ul>
              </Reveal>
              <Reveal className="mt-6">
                <CodeBlock
                  title="api-shape.txt — every response follows the envelope"
                  code={`success → { "data": {…}, "request_id": "req_…" }
failure → { "error": { "code": "…", "message": "…", "details": […] } }`}
                />
              </Reveal>
            </section>

            {/* 08 FAQ */}
            <section id="faq" aria-labelledby="faq-h" className="scroll-mt-36">
              <SectionHeading
                index="08 · FAQ"
                headingId="faq-h"
                title="Asked often, answered plainly."
                lede="The questions every team asks before trusting a debugging platform with their code."
              />
              <div className="mt-8 flex flex-col gap-3">
                {[
                  {
                    q: "Will Meridian change my code without asking?",
                    a: "Never. No patch is applied, pushed, or deployed without your explicit review of the exact diff. The model proposes; you dispose — approval is a deliberate act, not a default.",
                  },
                  {
                    q: "How is this different from asking a chatbot?",
                    a: "A chatbot answers from the report alone. Meridian reproduces the failure in isolation, captures linked evidence, drafts a regression test against the unchanged code, and verifies the patch with real runs — labeling guesses as guesses throughout.",
                  },
                  {
                    q: "Is my code safe during an investigation?",
                    a: "Yes. Code runs only in a separate, resource-limited sandbox worker — never in the main application and never on your machine. Only members of your workspace can see its projects, and secrets are excluded from every index.",
                  },
                  {
                    q: "What happens when an investigation can't reach a verdict?",
                    a: "Blocked, inconclusive, and timed-out outcomes are kept as first-class results with the evidence gathered so far. You'll see exactly where it stopped and what to try next — never a confident-sounding guess.",
                  },
                  {
                    q: "Can I use private repositories?",
                    a: "Bring private or in-progress code as a ZIP archive: nothing is fetched, only what you upload is inspected. Git connections accept public GitHub repositories, pinned to an exact commit at import.",
                  },
                ].map((item, i) => {
                  const open = openFaq === i;
                  return (
                    <Reveal key={item.q} delay={Math.min(i * 0.04, 0.16)}>
                      <div className={cn("overflow-hidden rounded-xl border bg-surface-1 shadow-card transition-colors", open ? "border-sage/40" : "border-line")}>
                        <button
                          type="button"
                          onClick={() => setOpenFaq(open ? null : i)}
                          aria-expanded={open}
                          className="flex w-full items-center gap-3 px-5 py-4 text-left text-[15px] font-semibold text-ink"
                        >
                          <span className="flex-1">{item.q}</span>
                          <motion.span
                            aria-hidden="true"
                            animate={reduceMotion ? undefined : { rotate: open ? 45 : 0 }}
                            transition={{ duration: 0.2 }}
                            className="flex size-7 shrink-0 items-center justify-center rounded-full border border-line text-[18px] leading-none text-sage"
                          >
                            +
                          </motion.span>
                        </button>
                        {open && (
                          <motion.div
                            initial={reduceMotion ? false : { height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                            className="overflow-hidden"
                          >
                            <p className="px-5 pb-5 text-[14.5px] leading-7 text-ink-2">{item.a}</p>
                          </motion.div>
                        )}
                      </div>
                    </Reveal>
                  );
                })}
              </div>
            </section>

            {/* Closing CTA */}
            <Reveal>
              <div className="relative overflow-hidden rounded-2xl border border-sage/25 bg-surface-1 shadow-pop">
                <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-sage" />
                <div className="p-8 sm:p-10">
                  <p className="font-mono text-xs font-medium tracking-[0.14em] text-sage uppercase">
                    Ready when you are
                  </p>
                  <h2 className="font-display mt-4 text-3xl leading-[1.1] font-semibold tracking-tight text-balance">
                    File your first report. Follow the evidence.
                  </h2>
                  <p className="mt-4 max-w-xl text-[15px] leading-7 text-ink-2">
                    Create an account, add a codebase, and watch a failure become a
                    cited, tested, approved fix — every step inspectable.
                  </p>
                  <div className="mt-7 flex flex-wrap gap-3">
                    <Link href="/signup" className="group inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 font-semibold text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_12px_28px_-10px_var(--color-accent)] transition-all duration-200 hover:bg-accent-hover active:scale-[0.98]">
                      Create an account
                      <ArrowRight aria-hidden="true" className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
                    </Link>
                    <Link href="/app" className="inline-flex h-11 items-center rounded-xl border border-line bg-canvas px-5 font-semibold text-ink-2 transition-all duration-200 hover:border-line-strong hover:text-ink">
                      Open the workspace
                    </Link>
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}





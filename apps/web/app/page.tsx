import Link from "next/link";
import { ArrowRight, ArrowUpRight, Bug, Camera, FlaskConical, GitPullRequest, SearchCheck, ShieldCheck, TerminalSquare } from "lucide-react";
import { MeridianLogo } from "@/components/brand/Logo";
import { AgentPlayground } from "@/components/landing/AgentPlayground";
import { DeveloperSection } from "@/components/landing/DeveloperSection";
import { FaqSection } from "@/components/landing/FaqSection";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { VideoSpotlight } from "@/components/landing/VideoSpotlight";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { Badge } from "@/components/ui/Badge";
import { Meter } from "@/components/ui/Meter";
import { Reveal } from "@/components/ui/Reveal";
import { StaggerHeadline, RotatingWord } from "@/components/ui/AnimatedHeadline";

const STAGES = [
  { n: "01", title: "Report", body: "A structured bug report: expected vs actual behavior, reproduction steps, and the route that fails.", icon: Bug },
  { n: "02", title: "Reproduce", body: "The project runs in an isolated environment while browser automation attempts the reported failure.", icon: FlaskConical },
  { n: "03", title: "Evidence", body: "Screenshots, console errors, failed network requests, traces, and logs are captured as linked artifacts.", icon: Camera },
  { n: "04", title: "Hypothesize", body: "The model proposes root-cause hypotheses grounded in real evidence IDs — never bare assertions.", icon: SearchCheck },
  { n: "05", title: "Test & patch", body: "A regression test is proposed and run against the unchanged baseline; then a minimal patch is drafted.", icon: TerminalSquare },
  { n: "06", title: "Approve", body: "You review the exact diff — files, lines, hash, risks — and explicitly approve or reject it.", icon: GitPullRequest },
  { n: "07", title: "Verify & report", body: "Post-patch checks run in isolation and the final status comes from real results, not model confidence.", icon: ShieldCheck },
];

const PRINCIPLES = [
  { n: "i", title: "Evidence over assertion", body: "Observed facts, model hypotheses, executed actions, and verified outcomes are labeled as what they are — so you always know what was seen versus what was guessed." },
  { n: "ii", title: "Humans approve every patch", body: "No patch is applied, pushed, or deployed without explicit review of the exact diff. The model proposes; you dispose." },
  { n: "iii", title: "Uncertainty is explicit", body: "Blocked, inconclusive, and timed-out states are preserved — never quietly rounded up to success. A shrug is a valid, visible result." },
  { n: "iv", title: "Isolation by default", body: "Untrusted project code runs in a separate, resource-limited worker. Never in the API process, never on your machine." },
];

const TICKER_WORDS = ["evidence.", "answers.", "verdicts.", "clarity."];

const MARQUEE = ["Reproduce in isolation", "Capture every artifact", "Hypothesize with citations", "Test before patching", "Humans approve diffs", "Verify with real runs"];

const LEDGER_ROWS = [
  ["09:41:02", "snapshot pinned · a3f9c1", "text-ink-3"],
  ["09:41:09", "app started in sandbox", "text-ink-3"],
  ["09:41:31", "console error captured", "text-danger"],
  ["09:41:33", "screenshot evidence #3", "text-info"],
  ["09:41:40", "hypothesis H-2 proposed", "text-warning"],
  ["09:42:07", "regression test drafted", "text-teal"],
  ["09:42:51", "patch diff ready · +14 −6", "text-success"],
];

export default function LandingPage() {
  return (
    <div className="texture-grain min-h-screen bg-canvas">
      {/* Top navigation */}
      <header className="sticky top-0 z-40 border-b border-line/70 bg-canvas/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-2 px-4 sm:px-6">
          <Link href="/" aria-label="Meridian home">
            <MeridianLogo markSize={26} />
          </Link>
          <nav aria-label="Landing" className="ml-10 hidden items-center gap-7 text-[13px] font-semibold text-ink-2 md:flex">
            <a href="#workflow" className="underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60">Workflow</a>
            <a href="#principles" className="underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60">Principles</a>
            <a href="#demo" className="underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60">Demo</a>
            <Link href="/docs" className="underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60">Documentation</Link>
            <a href="#faq" className="underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60">FAQ</a>
            <a href="#status" className="underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60">Status</a>
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
        {/* Hero — editorial split */}
        <section className="relative overflow-hidden">
          <div aria-hidden="true" className="texture-dots pointer-events-none absolute inset-0 opacity-60 [mask-image:radial-gradient(ellipse_70%_60%_at_30%_20%,black,transparent)]" />
          <div className="relative mx-auto grid w-full max-w-6xl gap-12 px-4 pt-14 pb-16 sm:px-6 md:grid-cols-[1.15fr_0.85fr] md:items-center md:pt-20 md:pb-24">
            <div>
              <p className="flex items-center gap-3 font-mono text-xs font-medium text-sage">
                <span aria-hidden="true" className="h-px w-8 bg-sage" />
                Meridian AI · Debugging &amp; reliability
              </p>
              <h1 className="font-display mt-6 text-[42px] leading-[1.04] font-semibold tracking-tight text-balance sm:text-[56px]">
                <StaggerHeadline text="Bug reports in." />
                <br />
                <span className="text-ink-2">
                  <StaggerHeadline text="Investigation-grade" delay={0.25} />
                </span>{" "}
                <em className="text-sage not-italic">
                  <RotatingWord words={TICKER_WORDS} />
                </em>
              </h1>
              <Reveal delay={0.35}>
                <p className="mt-6 max-w-xl text-[15px] leading-7 text-ink-2">
                  Meridian turns a bug report into a structured investigation: it reproduces the
                  failure in isolation, captures the evidence, proposes hypotheses linked to that
                  evidence, and verifies every patch with real test runs — with you approving each step.
                </p>
              </Reveal>
              <Reveal delay={0.45}>
                <div className="mt-8 flex flex-wrap items-center gap-3">
                  <Link
                    href="/app"
                    className="group inline-flex h-12 items-center gap-2 rounded-xl bg-accent px-6 text-[15px] font-semibold text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_12px_28px_-10px_var(--color-accent)] transition-all duration-200 hover:bg-accent-hover active:scale-[0.98]"
                  >
                    Open the workspace
                    <ArrowRight aria-hidden="true" className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
                  </Link>
                  <a
                    href="#workflow"
                    className="inline-flex h-12 items-center gap-1.5 rounded-xl border border-line bg-surface-1 px-6 text-[15px] font-semibold text-ink-2 shadow-card transition-all duration-200 hover:border-line-strong hover:text-ink"
                  >
                    How it works
                    <ArrowUpRight aria-hidden="true" className="size-4 opacity-70" />
                  </a>
                </div>
              </Reveal>
              <Reveal delay={0.55}>
                <dl className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-3 border-t border-line/70 pt-6">
                  {[
                    ["07", "pipeline stages"],
                    ["M1–M2", "live today"],
                    ["0", "patches without approval"],
                  ].map(([value, label]) => (
                    <div key={label} className="flex items-baseline gap-2">
                      <dt className="sr-only">{label}</dt>
                      <dd className="font-display text-2xl font-semibold text-ink">{value}</dd>
                      <dd className="text-[13px] text-ink-3">{label}</dd>
                    </div>
                  ))}
                </dl>
              </Reveal>
            </div>

            {/* Investigation ledger */}
            <Reveal delay={0.2} className="relative">
              <div aria-hidden="true" className="absolute inset-x-6 top-6 bottom-0 rounded-2xl border border-line bg-surface-2/70" />
              <figure aria-label="Concept preview of an investigation record" className="relative rounded-2xl border border-line bg-surface-1 shadow-pop">
                <div className="flex items-center justify-between gap-3 border-b border-line/70 px-5 py-3.5">
                  <span className="truncate font-mono text-xs text-ink-3">investigation · login-refresh-500</span>
                  <Badge tone="warning" pulse>Reproducing</Badge>
                </div>
                <div className="h-40 overflow-hidden px-5 py-2">
                  <ol className="flex animate-ticker flex-col font-mono text-xs">
                    {[...LEDGER_ROWS, ...LEDGER_ROWS.slice(0, 3)].map(([time, label, tone], i) => (
                      <li key={`${time}-${i}`} className="flex h-7 items-center gap-3 border-b border-line/50 last:border-0">
                        <span className="tnum shrink-0 text-ink-3">{time}</span>
                        <span className={tone}>{label}</span>
                      </li>
                    ))}
                  </ol>
                </div>
                <div className="flex items-center justify-between border-t border-line/70 bg-inset/70 px-5 py-3">
                  <span className="font-mono text-[11px] text-ink-3">artifacts · 14 linked</span>
                  <span className="font-mono text-[11px] font-medium text-success">sandbox · healthy</span>
                </div>
              </figure>
              <div className="absolute -bottom-5 left-6 flex animate-float items-center gap-2.5 rounded-xl border border-line bg-surface-1 py-2.5 pr-4 pl-2.5 shadow-pop">
                <span className="flex size-8 items-center justify-center rounded-lg bg-success/15 text-success">
                  <ShieldCheck aria-hidden="true" className="size-4" />
                </span>
                <span>
                  <span className="block text-[13px] font-semibold text-ink">H-2 confirmed</span>
                  <span className="block font-mono text-[11px] text-ink-3">3 citations · 0 guesses</span>
                </span>
              </div>
              <figcaption className="mt-8 text-xs text-ink-3">
                Concept preview — the investigation workspace arrives in Milestone 4.
              </figcaption>
            </Reveal>
          </div>
        </section>

        {/* Capability marquee */}
        <div aria-hidden="true" className="overflow-hidden border-y border-line/70 bg-surface-1/60 py-3.5">
          <div className="flex w-max animate-marquee gap-0 hover:[animation-play-state:paused]">
            {[0, 1].map((copy) => (
              <div key={copy} className="flex shrink-0 items-center">
                {MARQUEE.map((item) => (
                  <span key={`${copy}-${item}`} className="flex items-center">
                    <span className="px-6 font-mono text-[13px] font-medium tracking-wide text-ink-2 uppercase">{item}</span>
                    <span className="size-1.5 rounded-full bg-sage" />
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>

        <VideoSpotlight />

        <div aria-hidden="true" className="rule-fade mx-auto max-w-6xl" />

        <AgentPlayground />

        <div aria-hidden="true" className="rule-fade mx-auto max-w-6xl" />

        {/* Workflow — sticky index + steps */}
        <section id="workflow" className="mx-auto w-full max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 md:py-24">
          <div className="grid gap-10 md:grid-cols-[0.9fr_1.1fr] md:gap-16">
            <div className="md:sticky md:top-24 md:self-start">
              <Reveal>
                <p className="flex items-center gap-3 font-mono text-xs font-medium text-sage">
                  <span aria-hidden="true" className="h-px w-8 bg-sage" />
                  The pipeline
                </p>
                <h2 className="font-display mt-5 text-3xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-4xl">
                  One pipeline, from report to verified fix.
                </h2>
                <p className="mt-4 max-w-md text-[15px] leading-7 text-ink-2">
                  Every stage persists its inputs and outputs. Nothing is a black box:
                  you can inspect the reproduction, the evidence, and the reasoning at any point.
                </p>
                <Link
                  href="/app"
                  className="group mt-7 inline-flex items-center gap-1.5 text-[15px] font-semibold text-sage transition-colors hover:opacity-75"
                >
                  See what works today
                  <ArrowRight aria-hidden="true" className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
                </Link>
              </Reveal>
            </div>
            <ol className="flex flex-col">
              {STAGES.map((stage, i) => (
                <Reveal as="li" key={stage.n} delay={Math.min(i * 0.04, 0.2)}>
                  <div className="group flex gap-5 border-t border-line/70 py-6 transition-colors duration-200 last:border-b hover:bg-surface-1/60 sm:gap-7 sm:px-4">
                    <span className="font-display tnum w-12 shrink-0 text-2xl font-semibold text-line-strong transition-colors duration-200 group-hover:text-sage">
                      {stage.n}
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:gap-6">
                      <span className="flex items-center gap-2.5 font-semibold text-ink sm:w-36 sm:shrink-0">
                        <stage.icon aria-hidden="true" className="size-4 shrink-0 text-ink-3 transition-colors duration-200 group-hover:text-sage sm:hidden" />
                        {stage.title}
                      </span>
                      <span className="text-ink-2">{stage.body}</span>
                    </span>
                  </div>
                </Reveal>
              ))}
            </ol>
          </div>
        </section>

        <div aria-hidden="true" className="rule-fade mx-auto max-w-6xl" />

        {/* Principles — editorial list */}
        <section id="principles" className="mx-auto w-full max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 md:py-24">
          <Reveal className="max-w-2xl">
            <p className="flex items-center gap-3 font-mono text-xs font-medium text-sage">
              <span aria-hidden="true" className="h-px w-8 bg-sage" />
              Operating principles
            </p>
            <h2 className="font-display mt-5 text-3xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-4xl">
              Rules the system cannot break.
            </h2>
          </Reveal>
          <div className="mt-12 grid gap-x-14 md:grid-cols-2">
            {PRINCIPLES.map((principle, i) => (
              <Reveal key={principle.title} delay={(i % 2) * 0.08}>
                <div className="border-t border-line/70 py-7">
                  <p className="font-display text-lg text-sage italic">({principle.n})</p>
                  <h3 className="font-display mt-2 text-[22px] font-semibold tracking-tight">{principle.title}</h3>
                  <p className="mt-2 max-w-md leading-6 text-ink-2">{principle.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        <div aria-hidden="true" className="rule-fade mx-auto max-w-6xl" />

        <FaqSection />

        {/* Build status — warm panel */}
        <section id="status" className="mx-auto w-full max-w-6xl scroll-mt-20 px-4 pb-16 sm:px-6 md:pb-24">
          <Reveal>
            <div className="relative overflow-hidden rounded-2xl border border-sage/25 bg-surface-1 shadow-pop">
              <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-sage" />
              <div className="grid gap-10 p-8 sm:p-12 md:grid-cols-[1.2fr_0.8fr] md:items-center">
                <div>
                  <p className="font-mono text-xs font-medium tracking-[0.14em] text-sage uppercase">
                    Build status · Milestones 1–3 live
                  </p>
                  <h2 className="font-display mt-4 text-3xl leading-[1.1] font-semibold tracking-tight text-balance">
                    Under active construction, honestly labeled.
                  </h2>
                  <p className="mt-4 max-w-xl leading-7 text-ink-2">
                    The application shell, session authentication, workspace management, and
                    project onboarding with immutable snapshots are live in this workspace,
                    backed by PostgreSQL. The investigation pipeline follows in Milestones 4–10.
                  </p>
                  <div className="mt-7 flex flex-wrap gap-3">
                    <Link
                      href="/app"
                      className="group inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 font-semibold text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_12px_28px_-10px_var(--color-accent)] transition-all duration-200 hover:bg-accent-hover active:scale-[0.98]"
                    >
                      Open the workspace
                      <ArrowRight aria-hidden="true" className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
                    </Link>
                    <Link
                      href="/signup"
                      className="inline-flex h-11 items-center rounded-xl border border-line bg-canvas px-5 font-semibold text-ink-2 transition-all duration-200 hover:border-line-strong hover:text-ink"
                    >
                      Create an account
                    </Link>
                  </div>
                </div>
                <div className="rounded-xl border border-line/70 bg-inset/60 p-6">
                  <p className="font-mono text-[11px] font-medium tracking-[0.14em] text-ink-3 uppercase">Progress</p>
                  <ol className="mt-4 flex flex-col gap-3.5">
                    {[
                      ["Shell & theming", "done", "live"],
                      ["Auth & workspaces", "done", "live"],
                      ["Project onboarding", "done", "live"],
                      ["Investigation pipeline", "next", "M4"],
                    ].map(([label, state, tag]) => (
                      <li key={label} className="flex items-center gap-3 text-[13px]">
                        <span
                          aria-hidden="true"
                          className={
                            state === "done"
                              ? "size-2 rounded-full bg-success"
                              : state === "next"
                                ? "size-2 animate-pulse-dot rounded-full bg-sage"
                                : "size-2 rounded-full bg-surface-3"
                          }
                        />
                        <span className={state === "planned" ? "text-ink-3" : "font-medium text-ink"}>{label}</span>
                        <span className="ml-auto font-mono text-[11px] text-ink-3">
                          {tag}
                        </span>
                      </li>
                    ))}
                  </ol>
                  <Meter value={30} label="Milestone progress" className="mt-5" />
                </div>
              </div>
            </div>
          </Reveal>
        </section>
        <DeveloperSection />
      </main>

      <SiteFooter />
    </div>
  );
}

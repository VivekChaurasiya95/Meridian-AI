"use client";

import * as React from "react";
import Link from "next/link";
import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import {
  ArrowUpRight,
  Bug,
  Check,
  Clapperboard,
  FlaskConical,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";
import { StaggerHeadline } from "@/components/ui/AnimatedHeadline";
import { cn } from "@/lib/cn";

const VIDEO_URL = process.env.NEXT_PUBLIC_DEMO_VIDEO_URL?.trim() || "";

/** Normalize YouTube watch/share links to an embed URL. Null when not YouTube. */
function youtubeEmbed(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  const host = parsed.hostname.replace(/^www\./, "");
  if (host === "youtube.com" || host === "m.youtube.com") {
    const id = parsed.searchParams.get("v");
    if (id) return `https://www.youtube.com/embed/${id}`;
    if (parsed.pathname.startsWith("/embed/")) return url;
    if (parsed.pathname.startsWith("/shorts/")) {
      return `https://www.youtube.com/embed/${parsed.pathname.split("/")[2] ?? ""}`;
    }
    return null;
  }
  if (host === "youtu.be") {
    const id = parsed.pathname.replace("/", "");
    return id ? `https://www.youtube.com/embed/${id}` : null;
  }
  return null;
}

type RowTone = "ink" | "success" | "warning" | "danger" | "info" | "teal" | "sage";

const TONE_TEXT: Record<RowTone, string> = {
  ink: "text-ink-2",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  info: "text-info",
  teal: "text-teal",
  sage: "text-sage",
};

interface DemoRow {
  text: string;
  tone: RowTone;
}

interface DemoTab {
  index: string;
  label: string;
  icon: typeof Bug;
  panelTitleA: string;
  panelTitleB: string;
  steps: [string, string, string, string];
  cardTitle: string;
  cardSub: string;
  rows: [DemoRow, DemoRow, DemoRow, DemoRow];
}

const TABS: DemoTab[] = [
  {
    index: "01",
    label: "Report lands",
    icon: Bug,
    panelTitleA: "From your report",
    panelTitleB: "to an investigation.",
    steps: [
      "Paste the bug report",
      "Failing route mapped",
      "Sandbox spins up",
      "Investigation opens",
    ],
    cardTitle: "Bug report · login-refresh-500",
    cardSub: "Expected vs actual, steps, failing route",
    rows: [
      { text: "Expected: session persists on refresh", tone: "ink" },
      { text: "Actual: 500 after 30 seconds idle", tone: "danger" },
      { text: "Failing route mapped · POST /auth/refresh", tone: "info" },
      { text: "Sandbox healthy · investigation opened", tone: "success" },
    ],
  },
  {
    index: "02",
    label: "Evidence builds",
    icon: FlaskConical,
    panelTitleA: "From signals",
    panelTitleB: "to proof.",
    steps: [
      "Console errors captured",
      "Screenshots linked",
      "Hypothesis proposed",
      "Regression test drafted",
    ],
    cardTitle: "Live investigation · login-refresh-500",
    cardSub: "Every artifact linked to the claim it supports",
    rows: [
      { text: "console error captured", tone: "danger" },
      { text: "screenshot evidence #3", tone: "info" },
      { text: "hypothesis H-2 proposed", tone: "warning" },
      { text: "regression test drafted", tone: "teal" },
    ],
  },
  {
    index: "03",
    label: "Verified fix",
    icon: ShieldCheck,
    panelTitleA: "From a patch",
    panelTitleB: "to proof it holds.",
    steps: [
      "Minimal diff prepared",
      "Repro passes in sandbox",
      "Full suite green · 76 passed",
      "You approve the merge",
    ],
    cardTitle: "Patch diff ready · +14 −6",
    cardSub: "Minimal diff, tested before it is shown",
    rows: [
      { text: "+14 −6 across 2 files", tone: "ink" },
      { text: "repro passes in sandbox", tone: "success" },
      { text: "suite green · 76 passed", tone: "success" },
      { text: "approved by you · merged", tone: "sage" },
    ],
  },
];

const STEP_MS = 1500;
const TAB_PAUSE_MS = 2200;

/**
 * Interactive "watch the work" demo: phased tabs, a live investigation mock
 * whose rows flip from queued to done, and a dark steps panel that checks
 * off in sync. Plays when scrolled into view; reduced-motion users get the
 * finished states statically.
 */
function WatchTheWorkDemo() {
  const reduceMotion = useReducedMotion();
  const frameRef = React.useRef<HTMLDivElement>(null);
  const inView = useInView(frameRef, { amount: 0.3 });
  const [tab, setTab] = React.useState(0);
  const [step, setStep] = React.useState(0);
  const [playing, setPlaying] = React.useState(true);
  const finished = tab === TABS.length - 1 && step >= 4;

  React.useEffect(() => {
    if (reduceMotion || !playing || !inView) return;
    if (step < 4) {
      const timer = setTimeout(() => setStep((s) => s + 1), STEP_MS);
      return () => clearTimeout(timer);
    }
    if (tab < TABS.length - 1) {
      const timer = setTimeout(() => {
        setTab((t) => t + 1);
        setStep(0);
      }, TAB_PAUSE_MS);
      return () => clearTimeout(timer);
    }
    setPlaying(false);
  }, [reduceMotion, playing, inView, tab, step]);

  function selectTab(next: number) {
    setTab(next);
    setStep(0);
    setPlaying(true);
  }

  function replay() {
    setTab(0);
    setStep(0);
    setPlaying(true);
  }

  const active = TABS[tab];
  const shownStep = reduceMotion ? 4 : step;

  return (
    <div
      ref={frameRef}
      className="overflow-hidden rounded-3xl border border-line bg-surface-1 shadow-pop"
    >
      {/* Tab bar */}
      <div className="flex items-center gap-2 overflow-x-auto border-b border-line/70 bg-surface-2/60 px-3 py-2.5 sm:gap-2.5 sm:px-4">
        {TABS.map((item, i) => {
          const selected = i === tab;
          return (
            <button
              key={item.index}
              type="button"
              onClick={() => selectTab(i)}
              aria-pressed={selected}
              className={cn(
                "flex shrink-0 cursor-pointer items-center gap-2 rounded-full px-3.5 py-2 font-mono text-xs font-medium transition-all duration-200",
                selected
                  ? "bg-sage-subtle text-sage shadow-card"
                  : "text-ink-3 hover:bg-surface-3 hover:text-ink-2",
              )}
            >
              <span className={cn(selected ? "text-sage" : "text-ink-3")}>{item.index}</span>
              <item.icon aria-hidden="true" className="size-3.5" />
              {item.label}
            </button>
          );
        })}
        <span className="ml-auto hidden shrink-0 items-center gap-2 sm:flex">
          <button
            type="button"
            onClick={() => (finished ? replay() : setPlaying((p) => !p))}
            aria-label={playing ? "Pause demo" : "Play demo"}
            className="flex size-8 cursor-pointer items-center justify-center rounded-full border border-line text-ink-2 transition-colors duration-200 hover:border-line-strong hover:text-ink"
          >
            {playing ? (
              <Pause aria-hidden="true" className="size-3.5 fill-current" />
            ) : (
              <Play aria-hidden="true" className="size-3.5 fill-current" />
            )}
          </button>
          <button
            type="button"
            onClick={replay}
            aria-label="Replay demo"
            className="flex size-8 cursor-pointer items-center justify-center rounded-full border border-line text-ink-2 transition-colors duration-200 hover:border-line-strong hover:text-ink"
          >
            <RotateCcw aria-hidden="true" className="size-3.5" />
          </button>
          <span className="font-mono text-[11px] text-ink-3">Illustrative demo</span>
        </span>
      </div>

      <div className="grid md:grid-cols-[1.45fr_1fr]">
        {/* Investigation mock */}
        <div className="relative overflow-hidden bg-gradient-to-br from-sage-subtle via-surface-2 to-surface-2 p-4 sm:p-8">
          <div
            aria-hidden="true"
            className="texture-dots pointer-events-none absolute inset-0 opacity-40 [mask-image:radial-gradient(ellipse_60%_60%_at_30%_20%,black,transparent)]"
          />
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={tab}
              className="relative rounded-2xl border border-line bg-surface-1 p-5 shadow-pop sm:p-6"
              initial={reduceMotion ? false : { opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, y: -12 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-xs font-semibold">{active.cardTitle}</p>
                  <p className="mt-1 text-[13px] text-ink-3">{active.cardSub}</p>
                </div>
                <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-sage-subtle px-2.5 py-1 font-mono text-[11px] font-medium text-sage">
                  <span
                    aria-hidden="true"
                    className={cn(
                      "size-1.5 rounded-full bg-sage",
                      shownStep < 4 && !reduceMotion && "animate-pulse-dot",
                    )}
                  />
                  {shownStep < 4 ? "Live" : "Done"}
                </span>
              </div>
              <div className="mt-4 flex flex-col gap-2">
                {active.rows.map((row, i) => {
                  const revealed = shownStep > i;
                  const running = shownStep === i && !reduceMotion && playing;
                  return (
                    <motion.div
                      key={`${tab}-${i}`}
                      className={cn(
                        "flex items-center gap-3 rounded-xl border px-3.5 py-2.5 font-mono text-[13px]",
                        revealed ? "border-line bg-canvas" : "border-line/50 bg-canvas/40",
                      )}
                      initial={reduceMotion ? false : { opacity: 0, x: -10 }}
                      animate={{ opacity: revealed ? 1 : 0.45, x: 0 }}
                      transition={{ duration: 0.3 }}
                    >
                      <span
                        aria-hidden="true"
                        className={cn(
                          "flex size-5 shrink-0 items-center justify-center rounded-full",
                          revealed ? "bg-success/15 text-success" : "bg-surface-3 text-ink-3",
                        )}
                      >
                        <Check className="size-3" strokeWidth={3} />
                      </span>
                      <span className={cn("min-w-0 flex-1 truncate", TONE_TEXT[row.tone])}>
                        {row.text}
                      </span>
                      <span
                        className={cn(
                          "shrink-0 text-[11px] font-medium",
                          revealed ? "text-ink-3" : "text-ink-3/60",
                          running && "text-sage",
                        )}
                      >
                        {revealed ? "Done" : running ? "Running" : "Queued"}
                      </span>
                    </motion.div>
                  );
                })}
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Steps panel — deliberately near-black in both modes */}
        <div className="flex flex-col bg-[#10130f] p-6 text-[#eef2e6] sm:p-8">
          <p className="font-mono text-[11px] font-medium tracking-[0.14em] text-[#8b937f] uppercase">
            Watch the work
          </p>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={tab}
              initial={reduceMotion ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
            >
              <p className="font-display mt-4 text-[26px] leading-[1.15] font-semibold tracking-tight text-balance">
                {active.panelTitleA}{" "}
                <em className="text-[#a9bd93]">{active.panelTitleB}</em>
              </p>
            </motion.div>
          </AnimatePresence>
          <ol className="mt-6 flex flex-1 flex-col justify-center gap-1">
            {active.steps.map((label, i) => {
              const done = shownStep > i;
              return (
                <li key={`${tab}-${i}`} className="relative flex items-center gap-3.5 py-2.5">
                  {i < active.steps.length - 1 && (
                    <span
                      aria-hidden="true"
                      className={cn(
                        "absolute top-[42px] left-[15px] h-[calc(100%-34px)] w-px transition-colors duration-300",
                        shownStep > i + 1 ? "bg-[#7ce495]/60" : "bg-white/10",
                      )}
                    />
                  )}
                  <motion.span
                    aria-hidden="true"
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-full border transition-colors duration-300",
                      done ? "border-[#7ce495]/60 bg-[#7ce495]/15 text-[#7ce495]" : "border-white/15 text-[#5c6656]",
                    )}
                    initial={false}
                    animate={done ? { scale: [1, 1.25, 1] } : {}}
                    transition={{ duration: 0.35 }}
                  >
                    <Check className="size-4" strokeWidth={2.5} />
                  </motion.span>
                  <span
                    className={cn(
                      "text-[15px] transition-colors duration-300",
                      done ? "font-medium text-[#eef2e6]" : "text-[#8b937f]",
                    )}
                  >
                    {label}
                  </span>
                </li>
              );
            })}
          </ol>
          <Link
            href="/app"
            className="group mt-6 inline-flex w-fit items-center gap-1.5 font-medium text-[#a9bd93] transition-colors hover:text-[#7ce495]"
          >
            Open the workspace
            <ArrowUpRight
              aria-hidden="true"
              className="size-4 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
            />
          </Link>
        </div>
      </div>
    </div>
  );
}

/** "Watch the work" landing section: real video or the interactive demo. */
export function VideoSpotlight() {
  const embed = VIDEO_URL ? youtubeEmbed(VIDEO_URL) : null;
  const isMp4 = VIDEO_URL.toLowerCase().split("?")[0].endsWith(".mp4");
  return (
    <section id="demo" className="mx-auto w-full max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 md:py-24">
      <Reveal className="max-w-2xl">
        <p className="flex items-center gap-2.5 font-mono text-xs font-medium text-sage">
          <Clapperboard aria-hidden="true" className="size-3.5" />
          Watch the work
        </p>
        <h2 className="font-display mt-5 text-3xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-4xl">
          <StaggerHeadline text="An investigation, live in miniature." />
        </h2>
        <p className="mt-4 max-w-xl text-[15px] leading-7 text-ink-2">
          A playable miniature of the Meridian loop — report, evidence, verified
          fix — flipping through its paces. The narrated cut lands here when it
          is ready.
        </p>
      </Reveal>
      <Reveal delay={0.1} className="mt-10">
        {embed ? (
          <div className="overflow-hidden rounded-2xl border border-line bg-inset shadow-pop">
            <div className="aspect-video w-full">
              <iframe
                src={embed}
                title="Meridian AI demo video"
                className="size-full"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
              />
            </div>
          </div>
        ) : isMp4 ? (
          <div className="overflow-hidden rounded-2xl border border-line bg-inset shadow-pop">
            <video src={VIDEO_URL} controls preload="metadata" className="aspect-video w-full">
              Your browser cannot play this video.
            </video>
          </div>
        ) : VIDEO_URL ? (
          <a
            href={VIDEO_URL}
            target="_blank"
            rel="noreferrer"
            className="group flex items-center justify-between gap-4 rounded-2xl border border-line bg-surface-1 p-6 shadow-card transition-all duration-200 hover:border-line-strong hover:shadow-pop sm:p-8"
          >
            <span>
              <span className="font-display block text-xl font-semibold">Watch the demo video</span>
              <span className="mt-1 block font-mono text-xs break-all text-ink-3">{VIDEO_URL}</span>
            </span>
            <span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-accent text-accent-ink transition-transform duration-200 group-hover:scale-105">
              <ArrowUpRight aria-hidden="true" className="size-5" />
            </span>
          </a>
        ) : (
          <>
            <WatchTheWorkDemo />
            <p className="mt-3 text-center text-xs text-ink-3">
              Interactive miniature above — set{" "}
              <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-ink-2">
                NEXT_PUBLIC_DEMO_VIDEO_URL
              </code>{" "}
              to attach the narrated video instead.
            </p>
          </>
        )}
      </Reveal>
    </section>
  );
}

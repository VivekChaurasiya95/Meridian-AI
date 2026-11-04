"use client";

import * as React from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import {
  Camera,
  Check,
  FileText,
  Inbox,
  Pause,
  Play,
  ShieldCheck,
} from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";
import { StaggerHeadline } from "@/components/ui/AnimatedHeadline";
import { cn } from "@/lib/cn";

interface PlaygroundMode {
  id: string;
  label: string;
  icon: typeof Inbox;
  file: string;
  captionA: string;
  captionB: string;
  agentMood: string;
  tasks: [string, string, string];
}

const MODES: PlaygroundMode[] = [
  {
    id: "triage",
    label: "Triage a report",
    icon: Inbox,
    file: "bug-report.md",
    captionA: "small report,",
    captionB: "big clarity.",
    agentMood: "Reading every line.",
    tasks: ["Parse expected vs actual", "Map the failing route", "Open the investigation"],
  },
  {
    id: "evidence",
    label: "Build evidence",
    icon: Camera,
    file: "console-errors.log",
    captionA: "faint signals,",
    captionB: "hard proof.",
    agentMood: "Bagging every artifact.",
    tasks: ["Capture console errors", "Link screenshot #3", "Draft regression test"],
  },
  {
    id: "verify",
    label: "Verify a patch",
    icon: ShieldCheck,
    file: "patch.diff",
    captionA: "bold diff,",
    captionB: "calm merge.",
    agentMood: "Trusting only green runs.",
    tasks: ["Run repro in sandbox", "Full suite green", "Approve the merge"],
  },
];

const TEAM = [
  { name: "Triage", blob: "bg-[#dcebd4]", dot: "bg-[#7ce495]" },
  { name: "Evidence", blob: "bg-[#cdeae4]", dot: "bg-[#5ee0c0]" },
  { name: "Verify", blob: "bg-[#e3f2c8]", dot: "bg-[#d9f26b]" },
];

const STEP_MS = 1400;

/** Rolling-hills desktop wallpaper in Sage & Bone tones. */
function Wallpaper() {
  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 size-full"
      viewBox="0 0 1200 620"
      preserveAspectRatio="xMidYMid slice"
    >
      <rect width="1200" height="620" fill="var(--color-canvas)" />
      <circle cx="880" cy="130" r="120" fill="var(--color-sage-subtle)" />
      <circle cx="880" cy="130" r="120" fill="var(--color-surface-1)" opacity="0.35" />
      <path
        d="M0 380 Q 220 300 430 360 T 880 340 T 1200 380 V620 H0 Z"
        fill="var(--color-surface-3)"
        opacity="0.55"
      />
      <path
        d="M0 460 Q 260 390 520 450 T 1200 430 V620 H0 Z"
        fill="var(--color-sage-subtle)"
      />
      <path
        d="M0 540 Q 320 480 640 535 T 1200 520 V620 H0 Z"
        fill="var(--color-surface-2)"
      />
    </svg>
  );
}

/** Cute blob avatar with blinking eyes. */
function BlobFace({
  className,
  eyeClassName,
  blink,
  label,
}: {
  className?: string;
  eyeClassName?: string;
  blink: boolean;
  label: string;
}) {
  return (
    <span role="img" aria-label={label} className={cn("relative block overflow-hidden", className)}>
      <span className={cn("absolute inset-0 flex items-center justify-center gap-[18%]", blink && "animate-blink-eyes")}>
        <span className={cn("block size-[9%] rounded-full bg-current", eyeClassName)} />
        <span className={cn("block size-[9%] rounded-full bg-current", eyeClassName)} />
      </span>
    </span>
  );
}

/**
 * Interactive desktop playground: pick a workflow, tap the file to feed it,
 * and watch the little team work the tasks from queued to done.
 */
export function AgentPlayground() {
  const reduceMotion = useReducedMotion();
  const frameRef = React.useRef<HTMLDivElement>(null);
  const inView = useInView(frameRef, { amount: 0.25 });
  const [mode, setMode] = React.useState(0);
  const [step, setStep] = React.useState(0);
  const [playing, setPlaying] = React.useState(true);
  const [speech, setSpeech] = React.useState(false);
  const [hop, setHop] = React.useState({ i: -1, k: 0 });
  const active = MODES[mode];
  const done = step >= active.tasks.length;
  const shownStep = reduceMotion ? active.tasks.length : step;

  React.useEffect(() => {
    if (reduceMotion || !playing || !inView) return;
    if (step >= active.tasks.length) {
      setPlaying(false);
      return;
    }
    const timer = setTimeout(() => setStep((s) => s + 1), STEP_MS);
    return () => clearTimeout(timer);
  }, [reduceMotion, playing, inView, step, active.tasks.length]);

  function selectMode(next: number) {
    setMode(next);
    setStep(0);
    setPlaying(true);
    setSpeech(false);
  }

  function play() {
    if (done || step >= active.tasks.length) {
      setStep(0);
      setPlaying(true);
      return;
    }
    setPlaying((p) => !p);
  }

  const status = done ? "All done" : playing && inView ? "Working" : "Ready";

  return (
    <section className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 md:py-24">
      <Reveal className="max-w-2xl">
        <p className="flex items-center gap-3 font-mono text-xs font-medium text-sage">
          <span aria-hidden="true" className="h-px w-8 bg-sage" />
          Interactive playground
        </p>
        <h2 className="font-display mt-5 text-3xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-4xl">
          <StaggerHeadline text="A little presence on your desktop." />
        </h2>
        <p className="mt-4 max-w-xl text-[15px] leading-7 text-ink-2">
          Pick a workflow, tap the file to feed it, and watch the little team
          work it from queued to done.
        </p>
      </Reveal>

      <Reveal delay={0.1} className="mt-10">
        <div ref={frameRef} className="overflow-hidden rounded-3xl border border-line bg-surface-1 shadow-pop">
          {/* Scene top bar */}
          <div className="flex items-center justify-between gap-3 border-b border-line/70 px-4 py-3 sm:px-6">
            <p className="flex items-center gap-2 font-mono text-[11px] font-medium tracking-[0.14em] text-ink-3 uppercase">
              <span aria-hidden="true" className="size-1.5 rounded-full bg-sage" />
              A little Meridian on your desktop
            </p>
            <span className="rounded-full border border-line bg-canvas px-3 py-1 font-mono text-[11px] text-ink-2">
              Interactive preview
            </span>
          </div>

          {/* Desktop scene */}
          <div className="relative overflow-hidden select-none">
            <Wallpaper />
            <div className="relative px-4 py-10 sm:px-10 md:px-16 md:py-14">
              {/* Floating file card */}
              <motion.button
                type="button"
                onClick={play}
                whileTap={reduceMotion ? undefined : { scale: 0.94 }}
                aria-label={`Feed ${active.file} to Meridian`}
                className="group absolute bottom-6 left-4 z-10 flex cursor-pointer flex-col items-center gap-1.5 sm:bottom-10 sm:left-8"
              >
                <AnimatePresence mode="wait" initial={false}>
                  <motion.span
                    key={active.file}
                    className="flex size-14 rotate-[-6deg] items-center justify-center rounded-xl border border-line bg-surface-1 text-ink-2 shadow-pop transition-transform duration-200 group-hover:rotate-0"
                    initial={reduceMotion ? false : { opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduceMotion ? undefined : { opacity: 0, y: -6 }}
                    transition={{ duration: 0.25 }}
                  >
                    <FileText aria-hidden="true" className="size-6" />
                  </motion.span>
                </AnimatePresence>
                <span className="font-mono text-[11px] font-medium text-ink-2">{active.file}</span>
                <span className="text-[11px] text-ink-3 transition-colors group-hover:text-sage">
                  Tap to feed ↗
                </span>
              </motion.button>

              {/* Handwritten caption */}
              <div aria-hidden="true" className="absolute top-6 right-6 hidden text-right md:block lg:right-12">
                <svg width="46" height="40" viewBox="0 0 46 40" fill="none" className="ml-auto mb-1 text-ink-3">
                  <path
                    d="M42 4 C 30 10, 18 14, 10 30 M10 30 l-3 -9 M10 30 l9 -2"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <p className="font-display text-2xl leading-tight text-ink-2 italic">
                  {active.captionA}
                  <br />
                  {active.captionB}
                </p>
              </div>

              {/* App window */}
              <div className="relative mx-auto w-full max-w-3xl overflow-hidden rounded-3xl bg-[#10130f] text-[#eef2e6] shadow-pop">
                <div className="flex items-center justify-between px-5 py-3.5">
                  <p className="font-mono text-[11px] text-[#8b937f]">meridian · investigator</p>
                  <p className="flex items-center gap-2 font-mono text-[11px] text-[#8b937f]">
                    <span
                      aria-hidden="true"
                      className={cn(
                        "size-1.5 rounded-full",
                        done ? "bg-[#7ce495]" : playing ? "animate-pulse-dot bg-[#7ce495]" : "bg-[#5c6656]",
                      )}
                    />
                    {done ? "All done" : playing ? status : "Paused"} · {active.agentMood}
                  </p>
                </div>
                <div className="grid gap-3 px-4 pb-4 sm:grid-cols-[auto_1fr_auto] sm:items-center sm:px-5 sm:pb-5">
                  {/* Agent */}
                  <div className="relative hidden flex-col items-center gap-2 px-2 sm:flex">
                    <AnimatePresence>
                      {speech && (
                        <motion.span
                          className="absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 rounded-2xl rounded-bl-sm bg-[#e8eee1] px-3 py-2 text-xs font-medium whitespace-nowrap text-[#10130f] shadow-pop"
                          initial={reduceMotion ? false : { opacity: 0, y: 6, scale: 0.9 }}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={reduceMotion ? undefined : { opacity: 0, y: 4, scale: 0.95 }}
                          transition={{ duration: 0.2 }}
                        >
                          {active.agentMood}
                        </motion.span>
                      )}
                    </AnimatePresence>
                    <motion.span
                      className="block"
                      animate={!reduceMotion && done ? { y: [0, -8, 0] } : {}}
                      transition={{ duration: 0.5, repeat: 1 }}
                    >
                      <motion.button
                        type="button"
                        onClick={() => setSpeech((s) => !s)}
                        aria-label="Ask Meridian how it is doing"
                        whileHover={reduceMotion ? undefined : { rotate: [0, -7, 7, 0] }}
                        whileTap={reduceMotion ? undefined : { scale: 0.92 }}
                        transition={{ duration: 0.4 }}
                        className="block cursor-pointer"
                      >
                        <BlobFace
                          label="Meridian agent"
                          blink={!reduceMotion}
                          className="size-20 rounded-[42%] bg-[#f2f6ec] text-[#10130f]"
                        />
                      </motion.button>
                    </motion.span>
                    <span className="text-[13px] font-medium text-[#eef2e6]">Meridian</span>
                  </div>

                  {/* Tasks */}
                  <div className="rounded-2xl bg-white/[0.06] p-3.5">
                    <div className="flex items-center justify-between px-1 pb-2.5">
                      <p className="text-[13px] font-semibold">{active.label}</p>
                      <p className="font-mono text-[11px] text-[#8b937f]">
                        {shownStep}/{active.tasks.length} done
                      </p>
                    </div>
                    <div className="flex flex-col gap-2">
                      {active.tasks.map((task, i) => {
                        const taskDone = shownStep > i;
                        const running = shownStep === i && playing && !reduceMotion && !done;
                        return (
                          <motion.div
                            key={`${mode}-${i}`}
                            className={cn(
                              "flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px]",
                              taskDone ? "bg-[#7ce495]/12 text-[#eef2e6]" : "bg-white/[0.05] text-[#8b937f]",
                            )}
                            initial={reduceMotion ? false : { opacity: 0, x: -8 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ duration: 0.25, delay: i * 0.06 }}
                          >
                            <span
                              aria-hidden="true"
                              className={cn(
                                "flex size-5 shrink-0 items-center justify-center rounded-full",
                                taskDone
                                  ? "bg-[#7ce495]/25 text-[#7ce495]"
                                  : running
                                    ? "animate-pulse-dot bg-[#a9bd93]/25 text-[#a9bd93]"
                                    : "bg-white/10 text-[#5c6656]",
                              )}
                            >
                              <Check className="size-3" strokeWidth={3} />
                            </span>
                            <span className="min-w-0 flex-1 truncate">{task}</span>
                            <span className="shrink-0 font-mono text-[11px] text-[#8b937f]">
                              {taskDone ? "Done" : running ? "Next" : "Queued"}
                            </span>
                          </motion.div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Team */}
                  <div className="hidden rounded-2xl bg-white/[0.06] p-3.5 sm:block">
                    <p className="px-1 pb-2.5 text-[13px] font-semibold">Your little team</p>
                    <div className="flex gap-2.5">
                      {TEAM.map((member, i) => (
                        <motion.button
                          key={member.name}
                          type="button"
                          onClick={() => setHop((h) => ({ i, k: h.k + 1 }))}
                          aria-label={`Say hi to ${member.name}`}
                          whileHover={reduceMotion ? undefined : { scale: 1.12 }}
                          className="flex cursor-pointer flex-col items-center gap-1.5"
                        >
                          <motion.span
                            key={`hop-${i}-${hop.i === i ? hop.k : 0}`}
                            className="relative block"
                            initial={false}
                            animate={hop.i === i && hop.k > 0 && !reduceMotion ? { y: [0, -9, 0] } : { y: 0 }}
                            transition={{ duration: 0.4 }}
                          >
                            <BlobFace
                              label={`${member.name} agent`}
                              blink={!reduceMotion}
                              className={cn("size-11 rounded-[38%] text-[#10130f]", member.blob)}
                            />
                            <span
                              aria-hidden="true"
                              className={cn(
                                "absolute -right-0.5 -bottom-0.5 size-3 rounded-full border-2 border-[#10130f]",
                                shownStep > i ? member.dot : "bg-[#3a4237]",
                              )}
                            />
                          </motion.span>
                          <span className="text-[11px] text-[#8b937f]">{member.name}</span>
                        </motion.button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Dock */}
                <div className="flex justify-center pb-4">
                  <div className="flex items-center gap-1 rounded-2xl bg-white/[0.07] p-1.5">
                    {MODES.map((item, i) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => selectMode(i)}
                        aria-label={`Switch to ${item.label}`}
                        aria-pressed={i === mode}
                        className={cn(
                          "relative flex size-9 cursor-pointer items-center justify-center rounded-xl transition-colors duration-200",
                          i === mode
                            ? reduceMotion
                              ? "bg-[#e8eee1] text-[#10130f]"
                              : "text-[#10130f]"
                            : "text-[#8b937f] hover:bg-white/10 hover:text-[#eef2e6]",
                        )}
                      >
                        {i === mode && !reduceMotion && (
                          <motion.span
                            layoutId="playground-dock-pill"
                            className="absolute inset-0 rounded-xl bg-[#e8eee1]"
                            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                          />
                        )}
                        <item.icon aria-hidden="true" className="relative size-4" />
                      </button>
                    ))}
                    <span aria-hidden="true" className="mx-1 h-5 w-px bg-white/10" />
                    <button
                      type="button"
                      onClick={play}
                      aria-label={playing && !done ? "Pause workflow" : "Play workflow"}
                      className="flex size-9 cursor-pointer items-center justify-center rounded-xl bg-[#d9f26b] text-[#1e2119] transition-transform duration-200 hover:scale-105 active:scale-95"
                    >
                      {playing && !done ? (
                        <Pause aria-hidden="true" className="size-4 fill-current" />
                      ) : (
                        <Play aria-hidden="true" className="size-4 fill-current" />
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {/* Mode pills + play */}
              <div className="relative mx-auto mt-6 flex w-full max-w-3xl flex-wrap items-center gap-3">
                <div
                  role="group"
                  aria-label="Workflow modes"
                  className="flex flex-wrap items-center gap-1 rounded-full border border-line bg-surface-1/70 p-1.5 shadow-card"
                >
                  {MODES.map((item, i) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => selectMode(i)}
                      aria-pressed={i === mode}
                      className={cn(
                        "relative flex cursor-pointer items-center gap-2 rounded-full px-4 py-2 text-[13px] font-semibold transition-colors duration-200",
                        i === mode
                          ? reduceMotion
                            ? "bg-ink text-canvas shadow-card"
                            : "text-canvas"
                          : "text-ink-3 hover:bg-surface-3/60 hover:text-ink-2",
                      )}
                    >
                      {i === mode && !reduceMotion && (
                        <motion.span
                          layoutId="playground-mode-pill"
                          className="absolute inset-0 rounded-full bg-ink shadow-card"
                          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                        />
                      )}
                      <span className="relative flex items-center gap-2">
                        <item.icon aria-hidden="true" className="size-4" />
                        {item.label}
                      </span>
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={play}
                  className="ml-auto flex cursor-pointer items-center gap-2 rounded-full bg-[#d9f26b] px-5 py-2.5 text-[13px] font-semibold text-[#1e2119] shadow-card transition-transform duration-200 hover:scale-[1.03] active:scale-[0.98]"
                >
                  <Play aria-hidden="true" className="size-3.5 fill-current" />
                  {done ? "Replay workflow" : playing ? "Playing" : "Play workflow"}
                </button>
              </div>
              <div className="relative mx-auto mt-4 flex w-full max-w-3xl items-center justify-between text-[12px] text-ink-3">
                <p>Illustrative tool activity. Real rigor.</p>
                <p className="hidden sm:block">Try tapping the file ↗</p>
              </div>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

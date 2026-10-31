"use client";

import * as React from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import {
  ArrowUpRight,
  Bug,
  Camera,
  Clapperboard,
  FlaskConical,
  GitPullRequest,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";
import { StaggerHeadline } from "@/components/ui/AnimatedHeadline";

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

const SCENE_MS = 2600;

const SCENES = [
  {
    icon: Bug,
    title: "A bug report arrives",
    body: "Expected vs actual, reproduction steps, the failing route.",
  },
  {
    icon: FlaskConical,
    title: "Reproduced in isolation",
    body: "Your project runs in a sandbox — never on your machine.",
  },
  {
    icon: Camera,
    title: "Every artifact captured",
    body: "Screenshots, console errors, traces, and logs, all linked.",
  },
  {
    icon: GitPullRequest,
    title: "Tested, then patched",
    body: "A regression test first — then a minimal, reviewable diff.",
  },
  {
    icon: ShieldCheck,
    title: "Verified with real runs",
    body: "You approve the exact diff. Nothing ships on vibes.",
  },
];

/**
 * Bundled motion-graphics explainer: a self-playing animated storyboard of
 * the investigation loop. Plays when scrolled into view; reduced-motion
 * users get the full storyboard statically.
 */
function ExplainerPlayer() {
  const reduceMotion = useReducedMotion();
  const frameRef = React.useRef<HTMLDivElement>(null);
  const inView = useInView(frameRef, { amount: 0.4 });
  const [scene, setScene] = React.useState(0);
  const [playing, setPlaying] = React.useState(true);
  const finished = scene === SCENES.length - 1 && !playing;

  React.useEffect(() => {
    if (reduceMotion || !playing || !inView) return;
    if (scene >= SCENES.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = setTimeout(() => setScene((s) => s + 1), SCENE_MS);
    return () => clearTimeout(timer);
  }, [reduceMotion, playing, inView, scene]);

  function replay() {
    setScene(0);
    setPlaying(true);
  }

  if (reduceMotion) {
    return (
      <div className="rounded-2xl border border-line bg-inset shadow-pop">
        <ol className="grid gap-px overflow-hidden rounded-2xl sm:grid-cols-5">
          {SCENES.map((item, i) => (
            <li key={item.title} className="flex flex-col gap-2 bg-surface-1 p-5">
              <item.icon aria-hidden="true" className="size-5 text-accent" />
              <p className="font-mono text-[11px] text-ink-3">{String(i + 1).padStart(2, "0")}</p>
              <p className="font-display font-semibold">{item.title}</p>
              <p className="text-[13px] text-ink-2">{item.body}</p>
            </li>
          ))}
        </ol>
      </div>
    );
  }

  const Current = SCENES[scene];
  return (
    <div
      ref={frameRef}
      className="relative overflow-hidden rounded-2xl border border-line bg-inset shadow-pop"
    >
      <div aria-hidden="true" className="texture-dots pointer-events-none absolute inset-0 opacity-40 [mask-image:radial-gradient(ellipse_55%_65%_at_50%_40%,black,transparent)]" />
      {/* Stage */}
      <div className="relative flex aspect-video w-full flex-col items-center justify-center px-6 text-center sm:px-12">
        {!playing && !finished && (
          <span className="absolute top-4 left-5 rounded-full border border-line bg-canvas/80 px-3 py-1 font-mono text-[11px] font-medium text-ink-3">
            paused
          </span>
        )}
        <span className="absolute top-4 right-5 font-mono text-[11px] text-ink-3">
          {String(scene + 1).padStart(2, "0")} / {String(SCENES.length).padStart(2, "0")}
        </span>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={scene}
            className="relative flex flex-col items-center"
            initial={{ opacity: 0, y: 18, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -18, filter: "blur(4px)" }}
            transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
          >
            <span className="relative flex size-20 items-center justify-center">
              <motion.span
                aria-hidden="true"
                className="absolute inset-0 rounded-full border-2 border-dashed border-accent/40"
                animate={{ rotate: 360 }}
                transition={{ duration: 14, repeat: Infinity, ease: "linear" }}
              />
              <motion.span
                aria-hidden="true"
                className="absolute inset-2 rounded-full bg-accent/15 blur-md"
                animate={{ scale: [1, 1.15, 1], opacity: [0.7, 1, 0.7] }}
                transition={{ duration: 2.6, repeat: Infinity, ease: "easeInOut" }}
              />
              <span className="relative flex size-14 items-center justify-center rounded-2xl bg-accent text-accent-ink shadow-[0_12px_28px_-10px_var(--color-accent)]">
                <Current.icon aria-hidden="true" className="size-7" />
              </span>
            </span>
            <p className="font-display mt-6 text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
              {Current.title}
            </p>
            <p className="mt-2 max-w-md text-ink-2">{Current.body}</p>
          </motion.div>
        </AnimatePresence>
        {/* End-of-reel replay */}
        <AnimatePresence>
          {finished && (
            <motion.button
              type="button"
              onClick={replay}
              className="absolute inset-x-0 bottom-16 mx-auto flex w-fit cursor-pointer items-center gap-2 rounded-full border border-line bg-canvas px-5 py-2.5 text-[13px] font-semibold text-ink shadow-pop transition-colors duration-200 hover:border-line-strong hover:text-accent"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
            >
              <RotateCcw aria-hidden="true" className="size-4" />
              Replay the loop
            </motion.button>
          )}
        </AnimatePresence>
      </div>
      {/* Transport bar */}
      <div className="relative flex items-center gap-3 border-t border-line/70 bg-surface-1/80 px-4 py-3 backdrop-blur">
        <button
          type="button"
          onClick={() => (finished ? replay() : setPlaying((p) => !p))}
          aria-label={playing ? "Pause explainer" : "Play explainer"}
          className="flex size-9 cursor-pointer items-center justify-center rounded-full bg-accent text-accent-ink transition-transform duration-200 hover:scale-105 active:scale-95"
        >
          {playing ? (
            <Pause aria-hidden="true" className="size-4 fill-current" />
          ) : (
            <Play aria-hidden="true" className="size-4 fill-current" />
          )}
        </button>
        <button
          type="button"
          onClick={replay}
          aria-label="Replay explainer"
          className="flex size-9 cursor-pointer items-center justify-center rounded-full border border-line text-ink-2 transition-colors duration-200 hover:border-line-strong hover:text-ink"
        >
          <RotateCcw aria-hidden="true" className="size-4" />
        </button>
        <div className="flex flex-1 items-center gap-1.5" role="tablist" aria-label="Explainer scenes">
          {SCENES.map((item, i) => (
            <button
              key={item.title}
              type="button"
              role="tab"
              aria-selected={i === scene}
              aria-label={`Scene ${i + 1}: ${item.title}`}
              onClick={() => {
                setScene(i);
                setPlaying(true);
              }}
              className="group flex h-6 flex-1 cursor-pointer items-center"
            >
              <span className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
                <motion.span
                  className="block h-full w-full origin-left rounded-full bg-accent"
                  initial={false}
                  animate={{ scaleX: i < scene ? 1 : i === scene ? 1 : 0 }}
                  transition={
                    i === scene && playing
                      ? { duration: SCENE_MS / 1000, ease: "linear" }
                      : { duration: 0.2 }
                  }
                />
              </span>
            </button>
          ))}
        </div>
        <span className="hidden font-mono text-[11px] text-ink-3 sm:inline">0:13</span>
      </div>
    </div>
  );
}

/** "Watch Meridian explained" landing section: real video or motion explainer. */
export function VideoSpotlight() {
  const embed = VIDEO_URL ? youtubeEmbed(VIDEO_URL) : null;
  const isMp4 = VIDEO_URL.toLowerCase().split("?")[0].endsWith(".mp4");
  return (
    <section id="demo" className="mx-auto w-full max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 md:py-24">
      <Reveal className="max-w-2xl">
        <p className="flex items-center gap-2.5 font-mono text-xs font-medium text-accent">
          <Clapperboard aria-hidden="true" className="size-3.5" />
          Watch it explained
        </p>
        <h2 className="font-display mt-5 text-3xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-4xl">
          <StaggerHeadline text="The whole loop, animated." />
        </h2>
        <p className="mt-4 max-w-xl text-[15px] leading-7 text-ink-2">
          A thirteen-second motion overview of the investigation loop — the
          narrated cut lands here when it is ready.
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
            <ExplainerPlayer />
            <p className="mt-3 text-center text-xs text-ink-3">
              Motion overview above — set{" "}
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

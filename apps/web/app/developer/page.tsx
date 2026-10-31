import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Briefcase, Code2, Sparkles } from "lucide-react";
import { MeridianLogo } from "@/components/brand/Logo";
import { DeveloperPhoto } from "@/components/landing/DeveloperPhoto";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { Badge } from "@/components/ui/Badge";
import { Reveal } from "@/components/ui/Reveal";
import { RotatingWord, StaggerHeadline } from "@/components/ui/AnimatedHeadline";
import { DEVELOPER } from "@/lib/developer";

export const metadata: Metadata = {
  title: "Developer — Meridian AI",
  description: `Meet ${DEVELOPER.name}, the developer behind Meridian AI.`,
};

const SOCIALS = [
  { label: "GitHub", href: DEVELOPER.links.github, hint: "@VivekChaurasiya95" },
  { label: "LinkedIn", href: DEVELOPER.links.linkedin, hint: "Connect" },
  { label: "Portfolio", href: DEVELOPER.links.portfolio, hint: "Selected work" },
];

const FOCUS = ["clarity.", "craft.", "evidence.", "momentum."];

export default function DeveloperPage() {
  return (
    <div className="texture-grain min-h-screen bg-canvas">
      <header className="sticky top-0 z-40 border-b border-line/70 bg-canvas/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-2 px-4 sm:px-6">
          <Link href="/" aria-label="Meridian home">
            <MeridianLogo markSize={26} />
          </Link>
          <span className="ml-auto flex items-center gap-2.5">
            <ThemeToggle />
            <Link
              href="/"
              className="group inline-flex h-9 items-center gap-1.5 rounded-[10px] border border-line bg-surface-1 px-3.5 text-[13px] font-semibold text-ink-2 transition-all duration-200 hover:border-line-strong hover:text-ink"
            >
              <ArrowLeft aria-hidden="true" className="size-3.5 transition-transform duration-200 group-hover:-translate-x-0.5" />
              Back to site
            </Link>
          </span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-4 sm:px-6">
        {/* Hero */}
        <section className="relative overflow-hidden py-14 md:py-20">
          <div aria-hidden="true" className="texture-dots pointer-events-none absolute inset-0 opacity-60 [mask-image:radial-gradient(ellipse_60%_60%_at_70%_20%,black,transparent)]" />
          <div className="relative grid gap-12 md:grid-cols-[0.85fr_1.15fr] md:items-center">
            <Reveal className="relative mx-auto w-fit">
              <div aria-hidden="true" className="absolute -inset-4 rounded-[32px] bg-accent/15 blur-2xl" />
              <DeveloperPhoto className="font-display relative size-64 text-7xl sm:size-72" />
              <span className="absolute -bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full border border-line bg-canvas px-4 py-2 shadow-pop">
                <span aria-hidden="true" className="size-2 animate-pulse-dot rounded-full bg-success" />
                <span className="font-mono text-[11px] font-medium text-ink-2">open to opportunities</span>
              </span>
            </Reveal>
            <div>
              <p className="flex items-center gap-3 font-mono text-xs font-medium text-accent">
                <span aria-hidden="true" className="h-px w-8 bg-accent" />
                Developer · Meridian AI
              </p>
              <h1 className="font-display mt-6 text-[42px] leading-[1.04] font-semibold tracking-tight text-balance sm:text-[56px]">
                <StaggerHeadline text={DEVELOPER.name} />
              </h1>
              <p className="mt-3 text-lg font-medium text-accent">
                Building with <RotatingWord words={FOCUS} />
              </p>
              <p className="mt-5 max-w-xl text-[15px] leading-7 text-ink-2">{DEVELOPER.bio}</p>
              <div className="mt-8 flex flex-wrap gap-3">
                {SOCIALS.map((social) => (
                  <a
                    key={social.label}
                    href={social.href}
                    target="_blank"
                    rel="noreferrer"
                    className="group inline-flex h-11 items-center gap-2 rounded-xl border border-line bg-surface-1 px-5 text-[15px] font-semibold text-ink-2 shadow-card transition-all duration-200 hover:border-line-strong hover:text-ink"
                  >
                    {social.label}
                    <span className="font-mono text-[11px] font-normal text-ink-3">{social.hint}</span>
                    <ArrowUpRight aria-hidden="true" className="size-4 opacity-60 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                  </a>
                ))}
              </div>
            </div>
          </div>
        </section>

        <div aria-hidden="true" className="rule-fade" />

        {/* Stack */}
        <section className="py-14 md:py-16">
          <Reveal className="max-w-2xl">
            <p className="flex items-center gap-2.5 font-mono text-xs font-medium text-accent">
              <Code2 aria-hidden="true" className="size-3.5" />
              Toolbox
            </p>
            <h2 className="font-display mt-4 text-3xl font-semibold tracking-tight">The stack behind Meridian.</h2>
          </Reveal>
          <div className="mt-8 flex flex-wrap gap-2.5">
            {DEVELOPER.stack.map((tool, i) => (
              <Reveal key={tool} delay={Math.min(i * 0.04, 0.24)}>
                <Badge dot={false} className="px-4 py-2 text-[13px]">
                  {tool}
                </Badge>
              </Reveal>
            ))}
          </div>
        </section>

        <div aria-hidden="true" className="rule-fade" />

        {/* Highlights */}
        <section className="py-14 md:py-16">
          <Reveal className="max-w-2xl">
            <p className="flex items-center gap-2.5 font-mono text-xs font-medium text-accent">
              <Briefcase aria-hidden="true" className="size-3.5" />
              Built in this project
            </p>
            <h2 className="font-display mt-4 text-3xl font-semibold tracking-tight">Shipped, not just planned.</h2>
          </Reveal>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {DEVELOPER.highlights.map((item, i) => (
              <Reveal key={item.title} delay={i * 0.08}>
                <article className="group h-full rounded-2xl border border-line bg-surface-1 p-6 shadow-card transition-all duration-200 hover:border-line-strong hover:shadow-pop">
                  <span className="font-display text-2xl font-semibold text-line-strong transition-colors duration-200 group-hover:text-accent">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h3 className="font-display mt-3 text-lg font-semibold">{item.title}</h3>
                  <p className="mt-2 text-ink-2">{item.body}</p>
                </article>
              </Reveal>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="pb-16 md:pb-24">
          <Reveal>
            <div className="relative overflow-hidden rounded-2xl border border-accent/25 bg-surface-1 px-8 py-12 text-center shadow-pop sm:px-12">
              <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-accent" />
              <Sparkles aria-hidden="true" className="mx-auto size-6 text-accent" />
              <h2 className="font-display mx-auto mt-4 max-w-xl text-3xl leading-[1.1] font-semibold tracking-tight text-balance">
                Like the craft? Come see it running.
              </h2>
              <p className="mx-auto mt-3 max-w-md text-ink-2">
                Create an account and open the live workspace — auth, teams, and roles included.
              </p>
              <div className="mt-7 flex flex-wrap justify-center gap-3">
                <Link
                  href="/app"
                  className="inline-flex h-11 items-center rounded-xl bg-accent px-5 font-semibold text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_12px_28px_-10px_var(--color-accent)] transition-all duration-200 hover:bg-accent-hover active:scale-[0.98]"
                >
                  Open the workspace
                </Link>
                <a
                  href={DEVELOPER.links.portfolio}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex h-11 items-center gap-1.5 rounded-xl border border-line bg-canvas px-5 font-semibold text-ink-2 transition-all duration-200 hover:border-line-strong hover:text-ink"
                >
                  Visit portfolio
                  <ArrowUpRight aria-hidden="true" className="size-4 opacity-70" />
                </a>
              </div>
            </div>
          </Reveal>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

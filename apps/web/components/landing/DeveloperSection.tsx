"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { DeveloperPhoto } from "@/components/landing/DeveloperPhoto";
import { Reveal } from "@/components/ui/Reveal";
import { StaggerHeadline } from "@/components/ui/AnimatedHeadline";
import { DEVELOPER } from "@/lib/developer";

const SOCIALS = [
  { label: "GitHub", href: DEVELOPER.links.github },
  { label: "LinkedIn", href: DEVELOPER.links.linkedin },
  { label: "Portfolio", href: DEVELOPER.links.portfolio },
];

/** Landing teaser for the developer behind Meridian. */
export function DeveloperSection() {
  const reduceMotion = useReducedMotion();
  return (
    <section id="developer" className="mx-auto w-full max-w-6xl scroll-mt-20 px-4 pb-16 sm:px-6 md:pb-24">
      <Reveal>
        <div className="relative overflow-hidden rounded-2xl border border-line bg-surface-1 shadow-pop">
          <div aria-hidden="true" className="texture-dots pointer-events-none absolute inset-0 opacity-50 [mask-image:radial-gradient(ellipse_60%_70%_at_85%_20%,black,transparent)]" />
          <div className="relative grid gap-10 p-8 sm:p-12 md:grid-cols-[0.9fr_1.1fr] md:items-center">
            {/* Portrait with floating chips */}
            <div className="relative mx-auto w-fit">
              <div aria-hidden="true" className="absolute -inset-3 rounded-[28px] bg-accent/15 blur-2xl" />
              <DeveloperPhoto className="relative size-56 rounded-3xl border border-line shadow-pop sm:size-64" />
              {!reduceMotion && (
                <>
                  <motion.span
                    aria-hidden="true"
                    className="absolute -top-4 -right-6 rounded-full border border-line bg-canvas px-3.5 py-1.5 font-mono text-[11px] font-medium text-accent shadow-pop"
                    animate={{ y: [0, -8, 0] }}
                    transition={{ duration: 4.5, repeat: Infinity, ease: "easeInOut" }}
                  >
                    ships real software
                  </motion.span>
                  <motion.span
                    aria-hidden="true"
                    className="absolute -bottom-4 -left-6 rounded-full border border-line bg-canvas px-3.5 py-1.5 font-mono text-[11px] font-medium text-ink-2 shadow-pop"
                    animate={{ y: [0, 8, 0] }}
                    transition={{ duration: 5.2, repeat: Infinity, ease: "easeInOut", delay: 0.8 }}
                  >
                    full-stack · design-minded
                  </motion.span>
                </>
              )}
            </div>

            <div>
              <p className="flex items-center gap-3 font-mono text-xs font-medium text-accent">
                <span aria-hidden="true" className="h-px w-8 bg-accent" />
                Meet the developer
              </p>
              <h2 className="font-display mt-5 text-3xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-4xl">
                <StaggerHeadline text={DEVELOPER.name} />
              </h2>
              <p className="mt-2 font-medium text-accent">{DEVELOPER.role}</p>
              <p className="mt-4 max-w-xl leading-7 text-ink-2">
                {DEVELOPER.tagline} Meridian is designed, built, and maintained
                end to end — interface, API, data model, and infrastructure.
              </p>
              <div className="mt-6 flex flex-wrap items-center gap-2.5">
                {SOCIALS.map((social) => (
                  <a
                    key={social.label}
                    href={social.href}
                    target="_blank"
                    rel="noreferrer"
                    className="group inline-flex h-9 items-center gap-1.5 rounded-[10px] border border-line bg-canvas px-3.5 text-[13px] font-semibold text-ink-2 transition-all duration-200 hover:border-line-strong hover:text-ink"
                  >
                    {social.label}
                    <ArrowUpRight aria-hidden="true" className="size-3.5 opacity-60 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                  </a>
                ))}
              </div>
              <Link
                href="/developer"
                className="group mt-7 inline-flex items-center gap-1.5 text-[15px] font-semibold text-accent transition-colors hover:text-accent-hover"
              >
                Full developer story
                <ArrowRight aria-hidden="true" className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
              </Link>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

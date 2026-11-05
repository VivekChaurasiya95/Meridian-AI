"use client";

import * as React from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, ArrowUpRight } from "lucide-react";
import { MeridianMark } from "@/components/brand/Logo";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { DEVELOPER } from "@/lib/developer";

const COLUMNS: { title: string; links: { label: string; href: string; external?: boolean }[] }[] = [
  {
    title: "Product",
    links: [
      { label: "Workflow", href: "/#workflow" },
      { label: "Principles", href: "/#principles" },
      { label: "Documentation", href: "/docs" },
      { label: "Demo video", href: "/#demo" },
      { label: "FAQ", href: "/#faq" },
      { label: "Platform", href: "/#status" },
    ],
  },
  {
    title: "Project",
    links: [
      { label: "Workspace", href: "/app" },
      { label: "Create account", href: "/signup" },
      { label: "Sign in", href: "/login" },
      { label: "Developer", href: "/developer" },
    ],
  },
  {
    title: "Developer",
    links: [
      { label: "GitHub", href: DEVELOPER.links.github, external: true },
      { label: "LinkedIn", href: DEVELOPER.links.linkedin, external: true },
      { label: "Portfolio", href: DEVELOPER.links.portfolio, external: true },
    ],
  },
];

/** Floating back-to-top button with a scroll-progress ring. */
function BackToTop() {
  const [progress, setProgress] = React.useState(0);
  React.useEffect(() => {
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setProgress(max > 0 ? Math.min(window.scrollY / max, 1) : 0);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const visible = progress > 0.08;
  const radius = 19;
  const circumference = 2 * Math.PI * radius;
  return (
    <AnimatePresence>
      {visible && (
        <motion.button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label="Back to top"
          className="fixed right-6 bottom-6 z-40 flex size-12 cursor-pointer items-center justify-center rounded-full border border-line bg-surface-1 text-ink-2 shadow-pop transition-colors duration-200 hover:border-line-strong hover:text-accent"
          initial={{ opacity: 0, y: 16, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 16, scale: 0.9 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
        >
          <svg aria-hidden="true" className="absolute inset-0 size-full -rotate-90" viewBox="0 0 48 48">
            <circle cx="24" cy="24" r={radius} fill="none" strokeWidth="2.5" className="stroke-surface-3" />
            <circle
              cx="24"
              cy="24"
              r={radius}
              fill="none"
              strokeWidth="2.5"
              strokeLinecap="round"
              className="stroke-accent"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - progress)}
            />
          </svg>
          <ArrowUp aria-hidden="true" className="size-5" />
        </motion.button>
      )}
    </AnimatePresence>
  );
}

/** Interactive site footer: link columns, live status, theme, back-to-top. */
export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <>
      <footer className="border-t border-line/70 bg-surface-1/40">
        <div className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6 md:py-14">
          <div className="grid gap-10 md:grid-cols-[1.2fr_2fr]">
            <div>
              <span className="inline-flex items-center gap-2.5">
                <MeridianMark size={22} className="text-accent" />
                <span className="font-display text-lg font-semibold text-ink">Meridian AI</span>
              </span>
              <p className="mt-3 max-w-xs text-ink-2">
                Clarity for complex engineering — bug reports in, verified fixes out.
              </p>
              <p className="mt-2 max-w-xs text-[13px] text-ink-3">
                Designed &amp; built by{" "}
                <Link href="/developer" className="font-semibold text-ink-2 underline decoration-sage/50 decoration-2 underline-offset-4 transition-colors hover:text-sage">
                  {DEVELOPER.name}
                </Link>
              </p>
              <div className="mt-5 flex items-center gap-2.5">
                <ThemeToggle />
                <span className="inline-flex items-center gap-2 rounded-full border border-line bg-canvas px-3 py-1.5">
                  <span aria-hidden="true" className="size-2 animate-pulse-dot rounded-full bg-success" />
                  <span className="font-mono text-[11px] font-medium text-ink-2">Milestone 3 · live</span>
                </span>
              </div>
            </div>
            <nav aria-label="Footer" className="grid grid-cols-2 gap-8 sm:grid-cols-3">
              {COLUMNS.map((column) => (
                <div key={column.title}>
                  <p className="font-mono text-[11px] font-medium tracking-[0.14em] text-ink-3 uppercase">
                    {column.title}
                  </p>
                  <ul className="mt-4 flex flex-col gap-2.5">
                    {column.links.map((link) =>
                      link.external ? (
                        <li key={link.label}>
                          <a
                            href={link.href}
                            target="_blank"
                            rel="noreferrer"
                            className="group inline-flex items-center gap-1 text-[14px] font-medium text-ink-2 transition-colors hover:text-sage"
                          >
                            {link.label}
                            <ArrowUpRight aria-hidden="true" className="size-3.5 opacity-0 transition-all duration-200 group-hover:translate-x-0.5 group-hover:opacity-100" />
                          </a>
                        </li>
                      ) : (
                        <li key={link.label}>
                          <Link
                            href={link.href}
                            className="text-[14px] font-medium text-ink-2 underline decoration-transparent decoration-2 underline-offset-4 transition-all duration-200 hover:text-sage hover:decoration-sage/60"
                          >
                            {link.label}
                          </Link>
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              ))}
            </nav>
          </div>
          <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line/70 pt-6 text-[13px] text-ink-3">
            <span>© {year} Meridian AI</span>
            <span className="font-mono text-xs">MIT License</span>
            <span className="ml-auto font-mono text-xs">Evidence over assertion.</span>
          </div>
        </div>
      </footer>
      <BackToTop />
    </>
  );
}

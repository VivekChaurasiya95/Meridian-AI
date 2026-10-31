import Link from "next/link";
import { MeridianLogo, MeridianMark } from "@/components/brand/Logo";
import { ThemeToggle } from "@/components/shell/ThemeToggle";

const PANEL_POINTS = [
  ["Evidence over assertion", "Facts, hypotheses, and verified outcomes are labeled as what they are."],
  ["Humans approve every patch", "No change is applied without explicit review of the exact diff."],
  ["Isolation by default", "Untrusted code runs in a separate, resource-limited worker."],
];

/**
 * Split-screen shell for sign-in / sign-up: form on the left, brand panel
 * on the right (desktop). The panel is static product information.
 */
export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="texture-grain grid min-h-screen bg-canvas lg:grid-cols-[1fr_1fr]">
      <div className="flex flex-col px-4 py-6 sm:px-8">
        <div className="flex items-center justify-between">
          <Link href="/" aria-label="Meridian home" className="w-fit rounded-lg outline-none">
            <MeridianLogo markSize={26} />
          </Link>
          <ThemeToggle />
        </div>
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-12">
          <h1 className="font-display text-[32px] leading-[1.15] font-semibold tracking-tight text-balance">{title}</h1>
          <div className="mt-2.5 text-[15px] text-ink-2">{subtitle}</div>
          <div className="mt-8">{children}</div>
        </div>
        <p className="mx-auto w-full max-w-sm font-mono text-xs text-ink-3">
          Protected by session authentication · idle expiry 24h
        </p>
      </div>

      <aside
        aria-label="About Meridian"
        className="relative hidden flex-col justify-between overflow-hidden border-l border-line/70 bg-surface-1 p-12 lg:flex"
      >
        <div aria-hidden="true" className="texture-dots pointer-events-none absolute inset-0 opacity-50 [mask-image:radial-gradient(ellipse_60%_50%_at_70%_30%,black,transparent)]" />
        <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-accent" />
        <div className="relative">
          <MeridianMark size={44} className="text-accent" />
          <p className="font-display mt-8 max-w-md text-[34px] leading-[1.12] font-semibold tracking-tight text-balance">
            Clarity for complex engineering.
          </p>
          <p className="mt-3 max-w-md text-[15px] leading-7 text-ink-2">
            Every bug report becomes a structured, evidence-backed investigation.
          </p>
        </div>
        <dl className="relative flex flex-col">
          {PANEL_POINTS.map(([term, definition], i) => (
            <div key={term} className="flex max-w-md gap-4 border-t border-line/70 py-5 last:border-b">
              <span aria-hidden="true" className="font-display tnum text-lg font-semibold text-accent">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <dt className="font-semibold">{term}</dt>
                <dd className="mt-0.5 text-[13px] leading-5 text-ink-2">{definition}</dd>
              </div>
            </div>
          ))}
        </dl>
        <p className="relative font-mono text-xs text-ink-3">meridian · milestone 2 · session auth</p>
      </aside>
    </div>
  );
}

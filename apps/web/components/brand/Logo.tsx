import { cn } from "@/lib/cn";

interface MarkProps {
  className?: string;
  /** Pixel size of the square mark. */
  size?: number;
  title?: string;
}

/**
 * The Meridian mark: a meridian ring with polar ticks and a center node —
 * a precision-instrument dial. Strokes use `currentColor` so it adapts to
 * any surface; pass `text-accent` (or similar) for the brand color.
 */
export function MeridianMark({ className, size = 28, title = "Meridian" }: MarkProps) {
  const decorative = title.trim() === "";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : title}
      aria-hidden={decorative || undefined}
      className={className}
    >
      <circle cx="16" cy="16" r="9.5" stroke="currentColor" strokeWidth="2.5" />
      <circle cx="16" cy="16" r="13.5" stroke="currentColor" strokeWidth="1" opacity="0.35" strokeDasharray="2 3" />
      <path
        d="M16 2.5v2.5M16 27v2.5M2.5 16h2.5M27 16h2.5"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle cx="16" cy="16" r="3" fill="currentColor" />
    </svg>
  );
}

interface LockupProps {
  className?: string;
  markSize?: number;
  /** Show the "AI" suffix after Meridian. Defaults to true. */
  withSuffix?: boolean;
}

/** Full horizontal lockup: mark in an accent tile + "Meridian AI" wordmark. */
export function MeridianLogo({ className, markSize = 26, withSuffix = true }: LockupProps) {
  return (
    <span className={cn("group inline-flex items-center gap-2.5", className)}>
      <span className="flex items-center justify-center rounded-[9px] bg-accent p-[5px] text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_4px_12px_-4px_var(--color-accent)] transition-transform duration-300 group-hover:rotate-90">
        <MeridianMark size={markSize - 10} title="" />
      </span>
      <span className="font-display text-[19px] font-semibold tracking-tight text-ink">
        Meridian
        {withSuffix && <span className="ml-1.5 font-sans text-[13px] font-semibold tracking-[0.08em] text-ink-3 uppercase">AI</span>}
      </span>
    </span>
  );
}

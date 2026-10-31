import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return (
    <>
      <span className="sr-only">Loading…</span>
      <div aria-hidden="true" className={cn("skeleton-shimmer rounded-xl", className)} />
    </>
  );
}

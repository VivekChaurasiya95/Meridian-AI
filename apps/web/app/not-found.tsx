import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { MeridianMark } from "@/components/brand/Logo";

export default function NotFound() {
  return (
    <div className="texture-grain flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas px-4 text-center">
      <MeridianMark size={40} className="text-accent" />
      <p className="font-mono text-xs font-medium tracking-[0.2em] text-ink-3 uppercase">Error 404</p>
      <h1 className="font-display max-w-md text-4xl leading-[1.1] font-semibold tracking-tight text-balance">
        This page does not exist.
      </h1>
      <p className="max-w-sm leading-6 text-ink-2">
        The address may be wrong, or the page may belong to a milestone that has not shipped yet.
      </p>
      <Link
        href="/app"
        className="group mt-2 inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 font-semibold text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_12px_28px_-10px_var(--color-accent)] transition-all duration-200 hover:bg-accent-hover active:scale-[0.98]"
      >
        Back to the workspace
        <ArrowRight aria-hidden="true" className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
      </Link>
    </div>
  );
}

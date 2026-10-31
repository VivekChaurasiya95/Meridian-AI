"use client";

import * as React from "react";
import Image from "next/image";
import { cn } from "@/lib/cn";
import { DEVELOPER } from "@/lib/developer";

/**
 * Developer portrait with a monogram fallback. If the photo file is missing
 * (save it as apps/web/public/developer-vivek.png), initials render instead
 * of a broken image.
 */
export function DeveloperPhoto({ className }: { className?: string }) {
  const [failed, setFailed] = React.useState(false);
  if (failed) {
    return (
      <span
        aria-label={DEVELOPER.photoAlt}
        role="img"
        className={cn(
          "font-display flex items-center justify-center bg-accent font-semibold text-accent-ink",
          className,
        )}
      >
        {DEVELOPER.initials}
      </span>
    );
  }
  return (
    <Image
      src={DEVELOPER.photoSrc}
      alt={DEVELOPER.photoAlt}
      width={640}
      height={640}
      className={cn("object-cover", className)}
      onError={() => setFailed(true)}
      priority={false}
    />
  );
}

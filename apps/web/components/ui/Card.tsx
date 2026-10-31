import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const cardVariants = cva("rounded-xl border bg-surface-1 shadow-card", {
  variants: {
    tone: {
      plain: "border-line",
      raised: "border-line bg-surface-1",
      inset: "border-line/70 bg-inset shadow-none",
    },
    interactive: {
      true: "transition-[border-color,box-shadow,transform] duration-200 hover:border-line-strong hover:shadow-pop",
      false: "",
    },
  },
  defaultVariants: { tone: "plain", interactive: false },
});

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

export function Card({ tone, interactive, className, children, ...rest }: CardProps) {
  return (
    <div className={cn(cardVariants({ tone, interactive }), className)} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex flex-col gap-1 border-b border-line/70 px-5 py-4 sm:px-6", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardEyebrow({ className, children, ...rest }: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn("font-mono text-[11px] font-medium tracking-[0.14em] text-accent uppercase", className)} {...rest}>
      {children}
    </p>
  );
}

export function CardTitle({ className, children, ...rest }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2 className={cn("font-display text-[19px] leading-6 font-semibold tracking-tight text-ink", className)} {...rest}>
      {children}
    </h2>
  );
}

export function CardDescription({ className, children, ...rest }: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn("text-[13px] leading-5 text-ink-2", className)} {...rest}>
      {children}
    </p>
  );
}

export function CardContent({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("px-5 py-4 sm:px-6 sm:py-5", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardFooter({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex items-center gap-3 border-t border-line/70 bg-inset/60 px-5 py-3.5 sm:px-6", className)} {...rest}>
      {children}
    </div>
  );
}

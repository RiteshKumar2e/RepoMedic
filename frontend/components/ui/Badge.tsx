import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Severity and status labels.
 *
 * Colour here is information, so every variant keeps a visible text label —
 * the hue is never the only signal (WCAG 1.4.1).
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4 whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-accent-line bg-accent-soft text-accent",
        critical: "border-critical-line bg-critical-soft text-critical",
        high: "border-high-line bg-high-soft text-high",
        medium: "border-medium-line bg-medium-soft text-medium",
        low: "border-low-line bg-low-soft text-low",
        informational: "border-info-line bg-info-soft text-info",
        success: "border-success-line bg-success-soft text-success",
        neutral: "border-line bg-surface text-ink-muted",
        outline: "border-line bg-transparent text-ink-muted",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };

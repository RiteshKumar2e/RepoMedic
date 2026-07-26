import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-sky-500/10 text-sky-400 border border-sky-500/20",
        critical: "border-transparent bg-red-500/10 text-red-400 border border-red-500/30",
        high: "border-transparent bg-orange-500/10 text-orange-400 border border-orange-500/30",
        medium: "border-transparent bg-amber-500/10 text-amber-400 border border-amber-500/30",
        low: "border-transparent bg-blue-500/10 text-blue-400 border border-blue-500/30",
        informational: "border-transparent bg-slate-500/10 text-slate-400 border border-slate-500/30",
        success: "border-transparent bg-emerald-500/10 text-emerald-400 border border-emerald-500/30",
        outline: "text-slate-300 border border-slate-700",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };

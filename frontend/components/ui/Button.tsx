import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-sky-500 text-slate-950 hover:bg-sky-400 font-semibold shadow-sm",
        secondary: "bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700",
        outline: "border border-slate-700 bg-transparent text-slate-300 hover:bg-slate-800",
        ghost: "hover:bg-slate-800 text-slate-400 hover:text-slate-200",
        destructive: "bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20",
        success: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20",
      },
      size: {
        default: "h-8 px-3 py-1.5",
        sm: "h-7 px-2.5 text-[11px]",
        lg: "h-10 px-4 text-sm",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };

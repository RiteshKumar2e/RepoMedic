import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-md border font-medium whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-55",
  {
    variants: {
      variant: {
        /** Primary action. One per view. */
        default: "border-transparent bg-accent text-white hover:bg-accent-hover",
        /** The default for most buttons: reads as a control, not a call to action. */
        secondary: "border-line bg-canvas text-ink hover:bg-surface",
        outline: "border-line bg-transparent text-ink hover:bg-surface",
        ghost: "border-transparent bg-transparent text-ink-muted hover:bg-surface hover:text-ink",
        destructive: "border-critical-line bg-canvas text-critical hover:bg-critical-soft",
        success: "border-success-line bg-canvas text-success hover:bg-success-soft",
      },
      size: {
        default: "h-8 px-3 text-[13px]",
        sm: "h-7 px-2.5 text-xs",
        lg: "h-9 px-4 text-sm",
        icon: "h-8 w-8 p-0",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
);
Button.displayName = "Button";

export { Button, buttonVariants };

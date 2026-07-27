import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Text field matching the hairline-border language used by Card and Button.
 * Invalid state is carried by `aria-invalid` so the visual and the accessible
 * name never disagree.
 */
const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full rounded-md border border-line bg-canvas px-3 text-[13px] text-ink",
        "placeholder:text-ink-subtle transition-colors",
        "hover:border-ink-subtle focus:border-accent",
        "disabled:cursor-not-allowed disabled:opacity-55",
        "aria-[invalid=true]:border-critical aria-[invalid=true]:bg-critical-soft",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

const Label = React.forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, ...props }, ref) => (
    <label
      ref={ref}
      className={cn("block text-[13px] font-medium text-ink", className)}
      {...props}
    />
  ),
);
Label.displayName = "Label";

/** Inline message tied to a field via `aria-describedby`. */
const FieldError = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, children, ...props }, ref) =>
  children ? (
    <p ref={ref} className={cn("text-[12px] text-critical", className)} {...props}>
      {children}
    </p>
  ) : null,
);
FieldError.displayName = "FieldError";

export { Input, Label, FieldError };

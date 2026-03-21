import * as React from "react"
import { cn } from "@/lib/utils"

// Since I didn't install class-variance-authority or radix-ui, I should implement a simpler version
// or install them. The prompt said "No over-engineering".
// I will implement a simple clean Button component without extra dependencies like cva/radix for now,
// unless I want to be very robust.
// Actually, I can just use standard props.

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', isLoading, children, disabled, ...props }, ref) => {
    
    const variants = {
      primary: "bg-indigo-600 text-white hover:bg-indigo-700 shadow-[0_1px_15px_-3px_rgba(79,70,229,0.3)] hover:shadow-[0_1px_20px_-3px_rgba(79,70,229,0.4)]",
      secondary: "bg-slate-900 text-slate-200 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 shadow-sm",
      ghost: "hover:bg-slate-800/50 text-slate-400 hover:text-slate-200",
      danger: "bg-red-500/10 text-red-500 hover:bg-red-500/20 border border-red-500/20"
    };

    const sizes = {
      sm: "h-9 px-4 text-[13px] rounded-lg",
      md: "h-11 px-5 py-2.5 rounded-xl",
      lg: "h-14 px-8 text-lg rounded-2xl"
    };

    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-500 disabled:pointer-events-none disabled:opacity-50",
          variants[variant],
          sizes[size],
          className
        )}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading && (
          <svg className="mr-2 h-4 w-4 animate-spin" viewBox="0 0 24 24">
             <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
             <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
        )}
        {children}
      </button>
    )
  }
)
Button.displayName = "Button"

export { Button }

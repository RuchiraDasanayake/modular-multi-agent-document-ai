import React from "react";
import { cn } from "@/lib/utils";
import { Slot } from "@radix-ui/react-slot";

// --- Components ---

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("glass-card text-text-primary rounded-xl", className)} {...props} />
  )
)

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1 p-4", className)} {...props} />
  )
)

export const CardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("font-semibold leading-none tracking-tight text-sm", className)} {...props} />
  )
)

export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-4 pt-0", className)} {...props} />
  )
)

export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'primary' | 'outline' | 'ghost' | 'destructive', size?: 'default' | 'sm' | 'icon', asChild?: boolean }>(
  ({ className, variant = 'default', size = 'default', asChild = false, ...props }, ref) => {
    const variants = {
      default: "glass-button",
      primary: "bg-gradient-to-r from-brand-500 to-cyan-400 text-white shadow-[0_0_15px_rgba(6,182,212,0.3)] hover:opacity-90 border border-brand-400/50",
      outline: "border border-white/10 bg-transparent hover:bg-white/5 text-slate-200",
      ghost: "hover:bg-white/5 hover:text-white text-slate-400",
      destructive: "bg-red-500/80 text-white shadow-sm hover:bg-red-500 border border-red-500/50"
    };

    const sizes = {
      default: "h-8 px-4 py-1.5 text-xs",
      sm: "h-7 px-3 text-[11px]",
      icon: "h-8 w-8"
    };
    
    const Comp = asChild ? Slot : "button"
    
    return (
      <Comp
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-lg font-semibold transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary disabled:pointer-events-none disabled:opacity-50",
          variants[variant],
          sizes[size],
          className
        )}
        {...props}
      />
    )
  }
)

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-8 w-full rounded-lg border border-white/10 bg-slate-900/50 backdrop-blur-sm px-3 py-1 text-sm transition-all file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-slate-500 focus-visible:outline-none focus-visible:border-brand-500 focus:ring-1 focus:ring-brand-500 text-slate-200",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)

export const Badge = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { variant?: 'default' | 'secondary' | 'outline' | 'destructive' | 'success' | 'warning' }>(
  ({ className, variant = "default", ...props }, ref) => {
    const variants = {
      default: "border-transparent bg-slate-800 text-slate-200",
      secondary: "border-white/10 bg-white/5 text-slate-300",
      outline: "text-slate-400 border-white/10",
      destructive: "border-red-500/30 bg-red-500/10 text-red-400 shadow-[0_0_10px_rgba(239,68,68,0.2)]",
      success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.2)]",
      warning: "border-amber-500/30 bg-amber-500/10 text-amber-400 shadow-[0_0_10px_rgba(245,158,11,0.2)]",
    }
    return (
      <div ref={ref} className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2", variants[variant], className)} {...props} />
    )
  }
)

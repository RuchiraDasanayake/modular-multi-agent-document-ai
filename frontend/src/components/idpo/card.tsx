import type { PropsWithChildren } from "react";
import { clsx } from "clsx";

interface CardProps extends PropsWithChildren {
  className?: string;
}

export function IdpoCard({ className, children }: CardProps) {
  return (
    <section
      className={clsx(
        "rounded-2xl border border-slate-200 bg-white/90 p-5 shadow-sm shadow-slate-200/50 dark:border-slate-800 dark:bg-slate-900/70 dark:shadow-black/20",
        className,
      )}
    >
      {children}
    </section>
  );
}

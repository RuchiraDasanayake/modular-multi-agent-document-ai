"use client";

import * as React from "react";
import { useTheme } from "next-themes";
import { Icon } from "@/components/icons";

export function ThemeToggle() {
    const { resolvedTheme, setTheme } = useTheme();
    const [mounted, setMounted] = React.useState(false);

    React.useEffect(() => {
        setMounted(true);
    }, []);

    // The theme is unknown during server rendering, so the button stays neutral until mount.
    const isDark = mounted && resolvedTheme === "dark";
    const label = isDark ? "Switch to light theme" : "Switch to dark theme";

    return (
        <button
            type="button"
            onClick={() => setTheme(isDark ? "light" : "dark")}
            disabled={!mounted}
            aria-label={label}
            title={label}
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-slate-200/70 bg-white/70 text-slate-500 shadow-sm transition-colors hover:bg-slate-100 hover:text-slate-900 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800/70 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-100"
        >
            <Icon name={isDark ? "sun" : "moon"} className="h-4 w-4" />
        </button>
    );
}

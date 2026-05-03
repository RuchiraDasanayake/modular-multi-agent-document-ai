"use client";

import * as React from "react";
import { useTheme } from "next-themes";

export function ThemeToggle() {
    const { theme, setTheme } = useTheme();
    const [mounted, setMounted] = React.useState(false);

    React.useEffect(() => {
        setMounted(true);
    }, []);

    if (!mounted) {
        return <div className="w-9 h-9 rounded-lg bg-slate-100 dark:bg-gray-800 animate-pulse" />;
    }

    return (
        <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="min-w-9 h-9 px-2 rounded-lg flex items-center justify-center text-[11px] font-semibold transition-all duration-300
                 bg-slate-100 hover:bg-slate-200 text-slate-600 hover:text-slate-900
                 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-400 dark:hover:text-gray-100
                 border border-transparent dark:border-gray-700 shadow-sm"
            aria-label="Toggle theme"
        >
            {theme === "dark" ? "Light" : "Dark"}
        </button>
    );
}

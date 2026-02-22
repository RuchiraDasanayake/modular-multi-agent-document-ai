"use client";

import Sidebar from "@/components/sidebar";
import LoadingScreen from "@/components/loading-screen";
import { useUser } from "@/hooks/use-user";
import { ThemeToggle } from "@/components/theme-toggle";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const { loading } = useUser();

    return (
        <div className="flex min-h-screen bg-slate-50 dark:bg-gray-950 relative overflow-hidden transition-colors duration-300">
            {/* Subtle Background Effects */}
            <div className="fixed top-0 left-1/4 w-[500px] h-[500px] bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-[150px] pointer-events-none" />
            <div className="fixed bottom-0 right-1/4 w-[500px] h-[500px] bg-violet-500/10 dark:bg-violet-500/5 rounded-full blur-[150px] pointer-events-none" />

            {/* Theme Toggle */}
            <div className="fixed top-6 right-8 z-50">
                <ThemeToggle />
            </div>

            {loading && <LoadingScreen />}
            <Sidebar />
            <main className="flex-1 ml-[var(--sidebar-width)] p-8 relative z-10">{children}</main>
        </div>
    );
}

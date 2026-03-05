"use client";

import Sidebar from "@/components/sidebar";
import LoadingScreen from "@/components/loading-screen";
import { useUser } from "@/hooks/use-user";
import { ThemeToggle } from "@/components/theme-toggle";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const { loading } = useUser();

    return (
        <div className="flex min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 dark:from-gray-950 dark:via-gray-950 dark:to-gray-900 relative overflow-hidden transition-colors duration-300">
            {/* Ambient Background Effects */}
            <div className="fixed inset-0 pointer-events-none overflow-hidden">
                <div className="absolute top-[-15%] left-[10%] w-[700px] h-[700px] bg-brand-500/[0.08] dark:bg-brand-500/[0.04] rounded-full blur-[200px] animate-float" />
                <div className="absolute bottom-[-15%] right-[10%] w-[600px] h-[600px] bg-violet-500/[0.07] dark:bg-violet-500/[0.03] rounded-full blur-[200px] animate-float" style={{ animationDelay: '1.5s' }} />
                <div className="absolute top-[35%] right-[5%] w-[400px] h-[400px] bg-cyan-500/[0.06] dark:bg-cyan-500/[0.03] rounded-full blur-[150px] animate-float" style={{ animationDelay: '3s' }} />
                <div className="absolute bottom-[20%] left-[5%] w-[350px] h-[350px] bg-emerald-500/[0.05] dark:bg-emerald-500/[0.02] rounded-full blur-[130px] animate-float" style={{ animationDelay: '4.5s' }} />
                {/* Subtle grid overlay */}
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,rgba(0,0,0,0.03)_1px,transparent_0)] dark:bg-[radial-gradient(circle_at_1px_1px,rgba(255,255,255,0.02)_1px,transparent_0)] bg-[length:24px_24px]" />
            </div>

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

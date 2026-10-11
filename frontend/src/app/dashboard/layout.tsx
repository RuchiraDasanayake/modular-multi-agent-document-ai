"use client";


import { useState } from "react";
import Sidebar from "@/components/sidebar";
import { Icon } from "@/components/icons";
import { ThemeToggle } from "@/components/theme-toggle";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const [sidebarOpen, setSidebarOpen] = useState(false);

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

            {/* Mobile overlay backdrop */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/40 backdrop-blur-sm z-30 lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Mobile top bar */}
            <div className="fixed top-0 left-0 right-0 h-14 z-40 flex items-center justify-between px-4 lg:hidden bg-white/80 dark:bg-gray-950/80 backdrop-blur-xl border-b border-slate-200/60 dark:border-gray-800/40 shadow-sm">
                <button
                    type="button"
                    onClick={() => setSidebarOpen(true)}
                    aria-label="Open navigation"
                    className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-600 transition-colors hover:bg-slate-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                >
                    <Icon name="menu" className="h-5 w-5" />
                </button>
                <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-cyan-500 flex items-center justify-center text-white text-[10px] font-bold shadow-md shadow-brand-500/30">
                        AI
                    </div>
                    <span className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">Modular Doc AI</span>
                </div>
                <ThemeToggle />
            </div>

            <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
            <main className="relative z-10 min-w-0 flex-1 px-4 pb-10 pt-20 sm:px-6 lg:ml-[var(--sidebar-width)] lg:p-8 3xl:p-10">{children}</main>
        </div>
    );
}

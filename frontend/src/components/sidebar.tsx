"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { removeToken } from "@/lib/auth";
import { useUser } from "@/hooks/use-user";
import { clsx } from "clsx";
import {
    FileText,
    MessageSquare,
    ShieldCheck,
    UserCheck,
    LayoutDashboard,
    SendHorizonal,
    Blocks,
    FlaskConical,
    Target,
    Snowflake,
    Waves,
    TrendingUp,
    Lock,
    Upload,
    ChevronRight,
    LogOut,
    Crown,
    Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/* ── Navigation structure ── */

interface NavItem {
    href: string;
    label: string;
    Icon: LucideIcon;
    badge?: string;
    color?: string;
}

const USER_NAV: NavItem[] = [
    { href: "/dashboard/idpo", label: "Doc Extraction", Icon: FileText, badge: "Core", color: "brand" },
    { href: "/dashboard/xai", label: "AI Q&A", Icon: MessageSquare, color: "violet" },
    { href: "/dashboard/guardrails", label: "Quality Checks", Icon: ShieldCheck, color: "emerald" },
    { href: "/dashboard/hitl", label: "Expert Review", Icon: UserCheck, color: "amber" },
];

const ADMIN_NAV: NavItem[] = [
    { href: "/dashboard", label: "Overview", Icon: LayoutDashboard, color: "brand" },
    { href: "/dashboard/submit", label: "Submit Data", Icon: SendHorizonal, color: "cyan" },
    { href: "/dashboard/architecture", label: "Architecture", Icon: Blocks, color: "violet" },
    { href: "/dashboard/experiments", label: "Experiments", Icon: FlaskConical, color: "emerald" },
    { href: "/dashboard/rabi", label: "Cold Start", Icon: Snowflake, color: "cyan" },
    { href: "/dashboard/daaf", label: "Drift Monitor", Icon: Waves, color: "violet" },
    { href: "/dashboard/results", label: "Results", Icon: TrendingUp, color: "emerald" },
    { href: "/dashboard/admin", label: "Users", Icon: Lock, color: "amber" },
];

const COLOR_MAP: Record<string, { activeBg: string; activeText: string; iconBg: string; iconBorder: string; hoverBg: string }> = {
    brand: {
        activeBg: "bg-brand-500/10 dark:bg-brand-500/15",
        activeText: "text-brand-700 dark:text-brand-300",
        iconBg: "bg-brand-500/10 dark:bg-brand-500/20",
        iconBorder: "border-brand-200/60 dark:border-brand-500/20",
        hoverBg: "hover:bg-brand-50/60 dark:hover:bg-brand-500/5",
    },
    violet: {
        activeBg: "bg-violet-500/10 dark:bg-violet-500/15",
        activeText: "text-violet-700 dark:text-violet-300",
        iconBg: "bg-violet-500/10 dark:bg-violet-500/20",
        iconBorder: "border-violet-200/60 dark:border-violet-500/20",
        hoverBg: "hover:bg-violet-50/60 dark:hover:bg-violet-500/5",
    },
    emerald: {
        activeBg: "bg-emerald-500/10 dark:bg-emerald-500/15",
        activeText: "text-emerald-700 dark:text-emerald-300",
        iconBg: "bg-emerald-500/10 dark:bg-emerald-500/20",
        iconBorder: "border-emerald-200/60 dark:border-emerald-500/20",
        hoverBg: "hover:bg-emerald-50/60 dark:hover:bg-emerald-500/5",
    },
    cyan: {
        activeBg: "bg-cyan-500/10 dark:bg-cyan-500/15",
        activeText: "text-cyan-700 dark:text-cyan-300",
        iconBg: "bg-cyan-500/10 dark:bg-cyan-500/20",
        iconBorder: "border-cyan-200/60 dark:border-cyan-500/20",
        hoverBg: "hover:bg-cyan-50/60 dark:hover:bg-cyan-500/5",
    },
    amber: {
        activeBg: "bg-amber-500/10 dark:bg-amber-500/15",
        activeText: "text-amber-700 dark:text-amber-300",
        iconBg: "bg-amber-500/10 dark:bg-amber-500/20",
        iconBorder: "border-amber-200/60 dark:border-amber-500/20",
        hoverBg: "hover:bg-amber-50/60 dark:hover:bg-amber-500/5",
    },
};

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
    const isActive =
        item.href === "/dashboard"
            ? pathname === "/dashboard"
            : pathname.startsWith(item.href);
    const colors = COLOR_MAP[item.color ?? "brand"];

    return (
        <Link
            href={item.href}
            className={clsx(
                "group relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] transition-all duration-200",
                isActive
                    ? `${colors.activeBg} ${colors.activeText} font-semibold shadow-sm`
                    : `text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white ${colors.hoverBg}`
            )}
        >
            {/* Active bar indicator */}
            {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-gradient-to-b from-brand-400 to-cyan-500" />
            )}

            {/* Icon with colored background */}
            <div className={clsx(
                "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border transition-all duration-200",
                isActive
                    ? `${colors.iconBg} ${colors.iconBorder} shadow-sm`
                    : "bg-slate-100/60 dark:bg-gray-800/50 border-slate-200/40 dark:border-gray-700/40 group-hover:border-slate-300/60 dark:group-hover:border-gray-600/60"
            )}>
                <item.Icon className={clsx(
                    "w-4 h-4 transition-all duration-200",
                    isActive
                        ? colors.activeText
                        : "text-slate-400 dark:text-gray-500 group-hover:text-slate-600 dark:group-hover:text-gray-300",
                    !isActive && "group-hover:scale-110"
                )} />
            </div>

            <span className="flex-1 truncate">{item.label}</span>

            {item.badge && (
                <span className={clsx(
                    "px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider rounded-md transition-colors",
                    isActive
                        ? "bg-brand-500/15 text-brand-600 dark:text-brand-300"
                        : "bg-slate-100 dark:bg-gray-800 text-slate-400 dark:text-gray-500 group-hover:bg-brand-50 dark:group-hover:bg-brand-500/10 group-hover:text-brand-500 dark:group-hover:text-brand-400"
                )}>
                    {item.badge}
                </span>
            )}

            {/* Subtle arrow on hover for non-active items */}
            {!isActive && (
                <ChevronRight className="w-3.5 h-3.5 text-slate-300 dark:text-gray-600 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200" />
            )}
        </Link>
    );
}

export default function Sidebar() {
    const pathname = usePathname();
    const router = useRouter();
    const { user, isAdmin } = useUser();

    const handleLogout = () => {
        removeToken();
        router.push("/login");
    };

    return (
        <aside className="fixed left-0 top-0 h-screen w-[var(--sidebar-width)] bg-white/70 dark:bg-gray-950/70 backdrop-blur-3xl border-r border-white/80 dark:border-gray-800/40 flex flex-col z-40 shadow-2xl shadow-slate-200/40 dark:shadow-black/60 transition-colors duration-300">
            {/* Subtle inner gradient overlay */}
            <div className="absolute inset-0 bg-gradient-to-b from-white/30 via-transparent to-slate-50/40 dark:from-gray-900/20 dark:via-transparent dark:to-gray-950/30 pointer-events-none rounded-r-none" />

            {/* Brand */}
            <div className="relative px-5 py-5 border-b border-slate-100/80 dark:border-gray-800/50">
                <Link href="/dashboard" className="flex items-center gap-3 group">
                    <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-brand-500/30 group-hover:shadow-brand-500/50 transition-all duration-300 group-hover:scale-105">
                        <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
                        <div className="absolute inset-0 rounded-xl bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
                    </div>
                    <div className="flex-1 min-w-0">
                        <h2 className="text-sm font-bold text-slate-900 dark:text-white tracking-tight">Modular Doc AI</h2>
                        <p className="text-[10px] font-semibold tracking-wide uppercase bg-gradient-to-r from-brand-500 to-cyan-500 bg-clip-text text-transparent">
                            {isAdmin ? "Admin Console" : "Processing Hub"}
                        </p>
                    </div>
                </Link>
            </div>

            {/* Quick Action — Primary CTA */}
            <div className="relative px-3 pt-4 pb-2">
                <Link
                    href="/dashboard/idpo"
                    className={clsx(
                        "group relative flex items-center gap-3 px-4 py-3.5 rounded-xl text-sm font-semibold transition-all duration-300 w-full overflow-hidden",
                        pathname.startsWith("/dashboard/idpo")
                            ? "bg-gradient-to-r from-brand-500 to-cyan-500 text-white shadow-lg shadow-brand-500/30"
                            : "bg-gradient-to-r from-brand-500 to-cyan-500 text-white shadow-lg shadow-brand-500/25 hover:shadow-xl hover:shadow-brand-500/40 hover:scale-[1.02] active:scale-[0.98]"
                    )}
                >
                    {/* Shimmer effect on hover */}
                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700 ease-in-out" />
                    <Upload className="w-5 h-5 relative z-10" strokeWidth={2} />
                    <span className="relative z-10">Extract Documents</span>
                    <ChevronRight className="w-4 h-4 ml-auto opacity-60 relative z-10 group-hover:translate-x-0.5 transition-transform" />
                </Link>
            </div>

            {/* Navigation */}
            <nav className="relative flex-1 px-3 py-3 overflow-y-auto scrollbar-thin">
                {/* Tools section */}
                <div className="flex items-center gap-2 px-3 mb-2">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-gray-600">
                        Tools
                    </p>
                    <div className="flex-1 h-px bg-gradient-to-r from-slate-200/60 to-transparent dark:from-gray-800/60" />
                </div>
                <div className="space-y-0.5 mb-5">
                    {USER_NAV.map((item) => (
                        <NavLink key={item.href} item={item} pathname={pathname} />
                    ))}
                </div>

                {/* Admin section */}
                {isAdmin && (
                    <>
                        <div className="flex items-center gap-2 px-3 mb-2 mt-1">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-gray-600">
                                Admin
                            </p>
                            <Crown className="w-3 h-3 text-amber-400/60" />
                            <div className="flex-1 h-px bg-gradient-to-r from-slate-200/60 to-transparent dark:from-gray-800/60" />
                        </div>
                        <div className="space-y-0.5">
                            {ADMIN_NAV.map((item) => (
                                <NavLink key={item.href} item={item} pathname={pathname} />
                            ))}
                        </div>
                    </>
                )}
            </nav>

            {/* User Profile + Logout */}
            <div className="relative px-3 pb-4 pt-3 border-t border-slate-100/80 dark:border-gray-800/50 space-y-2">
                {user && (
                    <div className="group px-3 py-3 rounded-xl bg-gradient-to-r from-slate-50/80 to-white/50 dark:from-gray-900/40 dark:to-gray-800/20 border border-slate-200/40 dark:border-gray-800/40 hover:border-brand-200/40 dark:hover:border-brand-500/15 transition-all duration-200">
                        <div className="flex items-center gap-3">
                            {/* Avatar */}
                            <div className="relative w-9 h-9 rounded-full bg-gradient-to-br from-brand-400 to-cyan-500 flex items-center justify-center text-white text-xs font-bold shadow-md shadow-brand-500/20 flex-shrink-0">
                                {user.username.charAt(0).toUpperCase()}
                                {/* Online indicator */}
                                <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-emerald-400 border-2 border-white dark:border-gray-950" />
                            </div>
                            <div className="flex-1 min-w-0">
                                <p className="text-xs font-semibold text-slate-800 dark:text-gray-200 truncate">{user.username}</p>
                                <p className="text-[10px] text-slate-400 dark:text-gray-500 font-medium">
                                    {user.role === "admin" ? "Administrator" : "Team member"}
                                </p>
                            </div>
                            <span className={clsx(
                                "px-2 py-0.5 rounded-md text-[9px] uppercase tracking-wider font-bold flex-shrink-0",
                                user.role === "admin"
                                    ? "bg-amber-50 dark:bg-amber-500/10 border border-amber-200/60 dark:border-amber-500/20 text-amber-600 dark:text-amber-400"
                                    : "bg-brand-50 dark:bg-brand-500/10 border border-brand-200/60 dark:border-brand-500/20 text-brand-600 dark:text-brand-400"
                            )}>
                                {user.role}
                            </span>
                        </div>
                    </div>
                )}
                <button
                    onClick={handleLogout}
                    className="group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-slate-400 dark:text-gray-500
                     hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50/80 dark:hover:bg-red-500/10 border border-transparent hover:border-red-200/40 dark:hover:border-red-500/15 transition-all duration-200 w-full"
                >
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-slate-100/60 dark:bg-gray-800/50 border border-slate-200/40 dark:border-gray-700/40 group-hover:bg-red-50 dark:group-hover:bg-red-500/10 group-hover:border-red-200/40 dark:group-hover:border-red-500/20 transition-all duration-200">
                        <LogOut className="w-4 h-4" />
                    </div>
                    Sign Out
                </button>
            </div>
        </aside>
    );
}

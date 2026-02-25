"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { removeToken } from "@/lib/auth";
import { useUser } from "@/hooks/use-user";
import { clsx } from "clsx";

/* ── Navigation structure ── */

interface NavItem {
    href: string;
    label: string;
    icon: string;
}

const USER_NAV: NavItem[] = [
    { href: "/dashboard/xai", label: "AI Q&A", icon: "🧠" },
    { href: "/dashboard/hitl", label: "Expert Review", icon: "👤" },
    { href: "/dashboard/guardrails", label: "Quality Checks", icon: "🛡️" },
    { href: "/dashboard/idpo", label: "Doc Processing", icon: "📄" },
];

const ADMIN_NAV: NavItem[] = [
    { href: "/dashboard", label: "Overview", icon: "📊" },
    { href: "/dashboard/submit", label: "Submit Data", icon: "📝" },
    { href: "/dashboard/architecture", label: "Architecture", icon: "🏗️" },
    { href: "/dashboard/experiments", label: "Experiments", icon: "🎯" },
    { href: "/dashboard/rabi", label: "Cold Start", icon: "🧊" },
    { href: "/dashboard/daaf", label: "Drift Monitor", icon: "🌊" },
    { href: "/dashboard/results", label: "Results", icon: "📈" },
    { href: "/dashboard/admin", label: "Users", icon: "🔐" },
];

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
    const isActive =
        item.href === "/dashboard"
            ? pathname === "/dashboard"
            : pathname.startsWith(item.href);

    return (
        <Link
            href={item.href}
            className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150",
                isActive
                    ? "bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 font-medium border border-brand-200 dark:border-brand-500/20 shadow-sm shadow-brand-500/5"
                    : "text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-gray-800 hover:border-slate-200 dark:hover:border-gray-700 border border-transparent"
            )}
        >
            <span className="text-base drop-shadow-sm">{item.icon}</span>
            {item.label}
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
        <aside className="fixed left-0 top-0 h-screen w-[var(--sidebar-width)] bg-white/80 dark:bg-gray-950/80 backdrop-blur-xl border-r border-slate-200 dark:border-gray-800 flex flex-col z-40 shadow-xl shadow-slate-200/50 dark:shadow-black/20 transition-colors duration-300">
            {/* Brand */}
            <div className="px-5 py-5 border-b border-slate-200 dark:border-gray-800">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 flex items-center justify-center shadow-sm shadow-brand-500/10">
                        <span className="text-lg">🧠</span>
                    </div>
                    <div>
                        <h2 className="text-sm font-semibold text-slate-900 dark:text-white tracking-wide">Modular Doc AI</h2>
                        <p className="text-[11px] text-brand-600 dark:text-brand-400 font-medium">
                            {isAdmin ? "Admin Dashboard" : "User Dashboard"}
                        </p>
                    </div>
                </div>
            </div>

            {/* Navigation */}
            <nav className="flex-1 px-3 py-4 overflow-y-auto">
                {/* User section — visible to everyone */}
                <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">
                    Tools
                </p>
                <div className="space-y-1 mb-6">
                    {USER_NAV.map((item) => (
                        <NavLink key={item.href} item={item} pathname={pathname} />
                    ))}
                </div>

                {/* Admin section — visible to admins only */}
                {isAdmin && (
                    <>
                        <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">
                            Admin Panel
                        </p>
                        <div className="space-y-1">
                            {ADMIN_NAV.map((item) => (
                                <NavLink key={item.href} item={item} pathname={pathname} />
                            ))}
                        </div>
                    </>
                )}
            </nav>

            {/* User info + logout */}
            <div className="px-3 pb-4 space-y-2 border-t border-slate-200 dark:border-gray-800 pt-4">
                {user && (
                    <div className="px-3 py-2 text-xs text-slate-500 dark:text-gray-400 truncate flex items-center justify-between">
                        <span className="font-medium text-slate-700 dark:text-gray-200">{user.username}</span>
                        <span className="px-2 py-0.5 bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 rounded-full text-[10px] uppercase tracking-wider shadow-sm">
                            {user.role}
                        </span>
                    </div>
                )}
                <button
                    onClick={handleLogout}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-600 dark:text-gray-400
                     hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 hover:border-red-200 dark:hover:border-red-500/20 border border-transparent transition-all duration-150 w-full"
                >
                    <span className="text-base drop-shadow-sm">🚪</span>
                    Sign Out
                </button>
            </div>
        </aside>
    );
}

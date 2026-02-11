"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { removeToken } from "@/lib/auth";
import { clsx } from "clsx";

const NAV_ITEMS = [
    { href: "/dashboard", label: "Overview", icon: "📊" },
    { href: "/dashboard/submit", label: "Submit Data", icon: "📝" },
    { href: "/dashboard/architecture", label: "Architecture", icon: "🏗️" },
    { href: "/dashboard/experiments", label: "Experiments", icon: "🎯" },
    { href: "/dashboard/rabi", label: "RABI Cold Start", icon: "🧊" },
    { href: "/dashboard/daaf", label: "DAAF Drift", icon: "🌊" },
    { href: "/dashboard/results", label: "Results", icon: "📈" },
    { href: "/dashboard/admin", label: "Admin", icon: "🔐" },
];

export default function Sidebar() {
    const pathname = usePathname();
    const router = useRouter();

    const handleLogout = () => {
        removeToken();
        router.push("/login");
    };

    return (
        <aside className="fixed left-0 top-0 h-screen w-[var(--sidebar-width)] bg-gray-900 border-r border-gray-800 flex flex-col z-40">
            {/* Brand */}
            <div className="px-5 py-5 border-b border-gray-800">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-brand-500/10 border border-brand-500/20 flex items-center justify-center">
                        <span className="text-lg">🧠</span>
                    </div>
                    <div>
                        <h2 className="text-sm font-semibold text-white">AHMN</h2>
                        <p className="text-[11px] text-gray-500">Admin Dashboard</p>
                    </div>
                </div>
            </div>

            {/* Navigation */}
            <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
                {NAV_ITEMS.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={clsx(
                                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all",
                                isActive
                                    ? "bg-brand-500/10 text-brand-400 font-medium"
                                    : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
                            )}
                        >
                            <span className="text-base">{item.icon}</span>
                            {item.label}
                        </Link>
                    );
                })}
            </nav>

            {/* Footer */}
            <div className="px-3 pb-4">
                <button
                    onClick={handleLogout}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-500
                     hover:text-red-400 hover:bg-red-500/5 transition-all w-full"
                >
                    <span className="text-base">🚪</span>
                    Sign Out
                </button>
            </div>
        </aside>
    );
}

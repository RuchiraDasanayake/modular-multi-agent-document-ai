"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ThemeToggle } from "./theme-toggle";

const navLinks = [
    { label: "Home", href: "/" },
    { label: "Features", href: "/features" },
    { label: "About", href: "/about" },
    { label: "Pricing", href: "/pricing" },
    { label: "Docs", href: "/docs" },
    { label: "Contact", href: "/contact" },
];

export function PublicNavbar() {
    const pathname = usePathname();
    const [scrolled, setScrolled] = useState(false);
    const [mobileOpen, setMobileOpen] = useState(false);

    useEffect(() => {
        const onScroll = () => setScrolled(window.scrollY > 20);
        window.addEventListener("scroll", onScroll);
        return () => window.removeEventListener("scroll", onScroll);
    }, []);

    // Close mobile menu on route change
    useEffect(() => {
        setMobileOpen(false);
    }, [pathname]);

    return (
        <>
            <nav
                className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${scrolled
                    ? "bg-white/80 dark:bg-gray-950/80 backdrop-blur-xl border-b border-slate-200/60 dark:border-white/10 shadow-sm"
                    : "bg-transparent"
                    }`}
            >
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16 lg:h-20">
                        {/* Logo */}
                        <Link href="/" className="flex items-center gap-3 group">
                            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 dark:from-brand-500 dark:to-brand-700 flex items-center justify-center text-white text-sm font-bold shadow-md shadow-brand-500/25 group-hover:shadow-lg group-hover:shadow-brand-500/40 transition-all">
                                AI
                            </div>
                            <span className="text-lg font-bold text-slate-900 dark:text-white tracking-tight">
                                Modular Doc AI
                            </span>
                        </Link>

                        {/* Desktop Nav Links */}
                        <div className="hidden lg:flex items-center gap-1">
                            {navLinks.map((link) => {
                                const isActive = pathname === link.href;
                                return (
                                    <Link
                                        key={link.href}
                                        href={link.href}
                                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${isActive
                                            ? "text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-500/10"
                                            : "text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/5"
                                            }`}
                                    >
                                        {link.label}
                                    </Link>
                                );
                            })}
                        </div>

                        {/* Desktop Actions */}
                        <div className="hidden lg:flex items-center gap-3">
                            <ThemeToggle />
                            <Link
                                href="/login"
                                className="px-4 py-2 text-sm font-medium text-slate-600 dark:text-gray-300 hover:text-slate-900 dark:hover:text-white transition-colors"
                            >
                                Sign In
                            </Link>
                            <Link
                                href="/signup"
                                className="px-5 py-2.5 glass-button rounded-xl text-sm flex items-center gap-2"
                            >
                                Get Started
                            </Link>
                        </div>

                        {/* Mobile Menu Button */}
                        <div className="flex lg:hidden items-center gap-3">
                            <ThemeToggle />
                            <button
                                onClick={() => setMobileOpen(!mobileOpen)}
                                className="px-3 h-9 rounded-lg flex items-center justify-center bg-slate-100 dark:bg-gray-800 text-xs font-semibold text-slate-600 dark:text-gray-400 hover:bg-slate-200 dark:hover:bg-gray-700 transition-colors"
                            >
                                {mobileOpen ? "Close" : "Menu"}
                            </button>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Mobile Menu */}
            <AnimatePresence>
                {mobileOpen && (
                    <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        transition={{ duration: 0.2 }}
                        className="fixed inset-x-0 top-16 z-40 bg-white/95 dark:bg-gray-950/95 backdrop-blur-xl border-b border-slate-200/60 dark:border-white/10 shadow-lg lg:hidden"
                    >
                        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 space-y-1">
                            {navLinks.map((link) => {
                                const isActive = pathname === link.href;
                                return (
                                    <Link
                                        key={link.href}
                                        href={link.href}
                                        className={`block px-4 py-3 rounded-xl text-sm font-medium transition-all ${isActive
                                            ? "text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-500/10"
                                            : "text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/5"
                                            }`}
                                    >
                                        {link.label}
                                    </Link>
                                );
                            })}
                            <div className="pt-4 border-t border-slate-200 dark:border-gray-800 flex gap-3">
                                <Link
                                    href="/login"
                                    className="flex-1 px-4 py-3 text-center text-sm font-medium text-slate-700 dark:text-gray-300 bg-slate-100 dark:bg-gray-800 rounded-xl hover:bg-slate-200 dark:hover:bg-gray-700 transition-colors"
                                >
                                    Sign In
                                </Link>
                                <Link
                                    href="/signup"
                                    className="flex-1 px-4 py-3 text-center text-sm font-medium glass-button rounded-xl flex items-center justify-center gap-2"
                                >
                                    Get Started
                                </Link>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );
}

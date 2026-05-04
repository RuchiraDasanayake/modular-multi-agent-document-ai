"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";

export default function ForgotPasswordPage() {
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [submitted, setSubmitted] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            const res = await api.forgotPassword(email);
            if (res.token) {
                // Demo mode: redirect directly with the token
                router.push(`/reset-password?token=${res.token}`);
            } else {
                setSubmitted(true);
            }
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Something went wrong");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-gray-950 px-4 relative overflow-hidden transition-colors duration-300">
            {/* Top Bar */}
            <div className="absolute top-6 left-6 z-50">
                <Link href="/login" className="text-sm text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white transition-colors font-medium">
                    Back to Login
                </Link>
            </div>
            <div className="absolute top-6 right-6 z-50">
                <ThemeToggle />
            </div>

            {/* Background Effects */}
            <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-amber-500/20 dark:bg-amber-500/10 rounded-full blur-[120px] pointer-events-none" />
            <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brand-500/20 dark:bg-brand-500/10 rounded-full blur-[120px] pointer-events-none" />

            <div className="w-full max-w-md relative z-10">
                {/* Logo */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white dark:bg-gray-900 border border-amber-500/20 dark:border-amber-500/30 mb-4 text-amber-600 dark:text-amber-300 text-lg font-bold shadow-xl shadow-slate-200/50 dark:shadow-amber-500/10 backdrop-blur-md">
                        AI
                    </div>
                    <h1 className="text-3xl font-bold text-slate-900 dark:text-white tracking-tight">Forgot Password</h1>
                    <p className="text-slate-500 dark:text-gray-400 mt-2 font-medium">
                        Enter your email to reset your password
                    </p>
                </div>

                {submitted ? (
                    <div className="glass-panel rounded-2xl p-8 text-center space-y-4">
                        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Check Your Email</h2>
                        <p className="text-slate-500 dark:text-gray-400 text-sm">
                            If an account exists with that email, we&apos;ve sent a password reset link.
                        </p>
                        <Link
                            href="/login"
                            className="inline-block mt-4 text-sm text-brand-600 dark:text-brand-400 hover:text-brand-500 font-medium transition-colors"
                        >
                            Return to Sign In
                        </Link>
                    </div>
                ) : (
                    <form onSubmit={handleSubmit} className="glass-panel rounded-2xl p-8 space-y-6">
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">Email Address</label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full px-4 py-3 glass-input rounded-xl text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-gray-500"
                                placeholder="you@example.com"
                                required
                            />
                        </div>

                        {error && (
                            <div className="bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-900/50 backdrop-blur-md rounded-xl px-4 py-3 text-red-600 dark:text-red-400 text-sm shadow-sm">
                                {error}
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full py-3 glass-button rounded-xl disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {loading ? "Sending..." : "Send Reset Link"}
                        </button>

                        <p className="text-sm text-slate-500 dark:text-gray-400 text-center pt-2">
                            Remember your password?{" "}
                            <Link href="/login" className="text-brand-600 dark:text-brand-400 hover:text-brand-500 dark:hover:text-brand-300 font-medium transition-colors">
                                Sign in
                            </Link>
                        </p>
                    </form>
                )}
            </div>
        </div>
    );
}

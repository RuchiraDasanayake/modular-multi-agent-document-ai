"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";
import { ArrowLeft, KeyRound, CheckCircle } from "lucide-react";
import Link from "next/link";

function ResetPasswordForm() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const token = searchParams.get("token") || "";

    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);

    useEffect(() => {
        if (!token) {
            setError("No reset token provided. Please request a new password reset link.");
        }
    }, [token]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");

        if (password !== confirm) {
            setError("Passwords do not match");
            return;
        }

        setLoading(true);
        try {
            await api.resetPassword(token, password);
            setSuccess(true);
            setTimeout(() => router.push("/login"), 3000);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Password reset failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="w-full max-w-md relative z-10">
            {/* Logo */}
            <div className="text-center mb-8">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white dark:bg-gray-900 border border-brand-500/20 dark:border-brand-500/30 mb-4 shadow-xl shadow-slate-200/50 dark:shadow-brand-500/10 backdrop-blur-md">
                    <KeyRound className="w-7 h-7 text-brand-500" />
                </div>
                <h1 className="text-3xl font-bold text-slate-900 dark:text-white tracking-tight">Reset Password</h1>
                <p className="text-slate-500 dark:text-gray-400 mt-2 font-medium">
                    Choose a new password for your account
                </p>
            </div>

            {success ? (
                <div className="glass-panel rounded-2xl p-8 text-center space-y-4">
                    <CheckCircle className="w-12 h-12 text-emerald-500 mx-auto" />
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Password Reset Complete</h2>
                    <p className="text-slate-500 dark:text-gray-400 text-sm">
                        Your password has been changed. Redirecting to sign in...
                    </p>
                    <Link
                        href="/login"
                        className="inline-block mt-4 text-sm text-brand-600 dark:text-brand-400 hover:text-brand-500 font-medium transition-colors"
                    >
                        Go to Sign In
                    </Link>
                </div>
            ) : (
                <form onSubmit={handleSubmit} className="glass-panel rounded-2xl p-8 space-y-6">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">New Password</label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full px-4 py-3 glass-input rounded-xl text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-gray-500"
                            placeholder="••••••••"
                            minLength={6}
                            required
                            disabled={!token}
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">Confirm New Password</label>
                        <input
                            type="password"
                            value={confirm}
                            onChange={(e) => setConfirm(e.target.value)}
                            className="w-full px-4 py-3 glass-input rounded-xl text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-gray-500"
                            placeholder="••••••••"
                            minLength={6}
                            required
                            disabled={!token}
                        />
                    </div>

                    {error && (
                        <div className="bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-900/50 backdrop-blur-md rounded-xl px-4 py-3 text-red-600 dark:text-red-400 text-sm shadow-sm">
                            {error}
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={loading || !token}
                        className="w-full py-3 glass-button rounded-xl disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {loading ? "Resetting..." : "Reset Password"}
                    </button>

                    <p className="text-sm text-slate-500 dark:text-gray-400 text-center pt-2">
                        <Link href="/forgot-password" className="text-brand-600 dark:text-brand-400 hover:text-brand-500 dark:hover:text-brand-300 font-medium transition-colors">
                            Request a new reset link
                        </Link>
                    </p>
                </form>
            )}
        </div>
    );
}

export default function ResetPasswordPage() {
    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-gray-950 px-4 relative overflow-hidden transition-colors duration-300">
            {/* Top Bar */}
            <div className="absolute top-6 left-6 z-50">
                <Link href="/login" className="flex items-center gap-2 text-sm text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white transition-colors font-medium">
                    <ArrowLeft className="w-4 h-4" />
                    Back to Login
                </Link>
            </div>
            <div className="absolute top-6 right-6 z-50">
                <ThemeToggle />
            </div>

            {/* Background Effects */}
            <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-brand-500/20 dark:bg-brand-500/10 rounded-full blur-[120px] pointer-events-none" />
            <div className="absolute bottom-1/4 left-1/4 w-96 h-96 bg-violet-500/20 dark:bg-violet-500/10 rounded-full blur-[120px] pointer-events-none" />

            <Suspense fallback={
                <div className="flex items-center justify-center h-64">
                    <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                </div>
            }>
                <ResetPasswordForm />
            </Suspense>
        </div>
    );
}

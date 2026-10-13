"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { ThemeToggle } from "@/components/theme-toggle";
import { useSignupOpen } from "@/components/signup-link";

export default function SignupPage() {
    const router = useRouter();
    const signupOpen = useSignupOpen();
    const [email, setEmail] = useState("");
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");

        if (password !== confirm) {
            setError("Passwords do not match");
            return;
        }

        setLoading(true);
        try {
            const { access_token } = await api.signup(email, username, password);
            setToken(access_token);
            router.push("/dashboard");
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Registration failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-gray-950 px-4 relative overflow-hidden transition-colors duration-300">
            {/* Top Bar */}
            <div className="absolute top-6 left-6 z-50">
                <Link href="/" className="text-sm text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white transition-colors font-medium">
                    Back to Home
                </Link>
            </div>
            <div className="absolute top-6 right-6 z-50">
                <ThemeToggle />
            </div>

            {/* Background Effects */}
            <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-brand-500/20 dark:bg-brand-500/10 rounded-full blur-[120px] pointer-events-none" />
            <div className="absolute bottom-1/4 left-1/4 w-96 h-96 bg-cyan-500/20 dark:bg-cyan-500/10 rounded-full blur-[120px] pointer-events-none" />

            <div className="w-full max-w-md relative z-10">
                {/* Logo */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white dark:bg-gray-900 border border-brand-500/20 dark:border-brand-500/30 mb-4 text-brand-600 dark:text-brand-300 text-lg font-bold shadow-xl shadow-slate-200/50 dark:shadow-brand-500/10 backdrop-blur-md">
                        AI
                    </div>
                    <h1 className="text-3xl font-bold text-slate-900 dark:text-white tracking-tight">
                        {signupOpen ? "Create Account" : "Sign-up is closed"}
                    </h1>
                    <p className="text-slate-500 dark:text-gray-400 mt-2 font-medium">Modular Document AI Platform</p>
                </div>

                {signupOpen ? (
                    <form onSubmit={handleSubmit} className="glass-panel rounded-2xl p-8 space-y-6">
                        <div>
                            <label htmlFor="signup-email" className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">Email</label>
                            <input
                                id="signup-email"
                                name="email"
                                autoComplete="email"
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full px-4 py-3 glass-input rounded-xl text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-gray-500"
                                placeholder="you@example.com"
                                required
                            />
                        </div>

                        <div>
                            <label htmlFor="signup-username" className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">Username</label>
                            <input
                                id="signup-username"
                                name="username"
                                autoComplete="username"
                                type="text"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                className="w-full px-4 py-3 glass-input rounded-xl text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-gray-500"
                                placeholder="johndoe"
                                minLength={3}
                                maxLength={32}
                                required
                            />
                        </div>

                        <div>
                            <label htmlFor="signup-password" className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">Password</label>
                            <input
                                id="signup-password"
                                name="password"
                                autoComplete="new-password"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full px-4 py-3 glass-input rounded-xl text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-gray-500"
                                placeholder="••••••••"
                                minLength={6}
                                required
                            />
                        </div>

                        <div>
                            <label htmlFor="signup-confirm-password" className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">Confirm Password</label>
                            <input
                                id="signup-confirm-password"
                                name="confirm_password"
                                autoComplete="new-password"
                                type="password"
                                value={confirm}
                                onChange={(e) => setConfirm(e.target.value)}
                                className="w-full px-4 py-3 glass-input rounded-xl text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-gray-500"
                                placeholder="••••••••"
                                minLength={6}
                                required
                            />
                        </div>

                        {error && (
                            <div role="alert" className="bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-900/50 backdrop-blur-md rounded-xl px-4 py-3 text-red-600 dark:text-red-400 text-sm shadow-sm">
                                {error}
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full py-3 glass-button rounded-xl disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {loading ? "Creating account..." : "Create Account"}
                        </button>

                        <p className="text-sm text-slate-500 dark:text-gray-400 text-center pt-2">
                            Already have an account?{" "}
                            <Link href="/login" className="text-brand-600 dark:text-brand-400 hover:text-brand-500 dark:hover:text-brand-300 font-medium transition-colors">
                                Sign in
                            </Link>
                        </p>
                    </form>
                ) : (
                    <div className="glass-panel rounded-2xl p-8 space-y-6 text-center">
                        <p className="text-sm text-slate-600 dark:text-gray-300">
                            Accounts on this site are created by an administrator. If you were given one, sign in.
                        </p>
                        <Link href="/login" className="block w-full py-3 glass-button rounded-xl">
                            Sign in
                        </Link>
                    </div>
                )}
            </div>
        </div>
    );
}

import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";

export default function ResetPasswordPage() {
    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-gray-950 px-4 relative overflow-hidden transition-colors duration-300">
            <div className="absolute top-6 left-6 z-50">
                <Link href="/login" className="text-sm text-slate-500 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white transition-colors font-medium">
                    Back to Login
                </Link>
            </div>
            <div className="absolute top-6 right-6 z-50"><ThemeToggle /></div>
            <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-500/20 dark:bg-brand-500/10 rounded-full blur-[120px] pointer-events-none" />
            <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-violet-500/20 dark:bg-violet-500/10 rounded-full blur-[120px] pointer-events-none" />

            <main className="w-full max-w-md relative z-10">
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white dark:bg-gray-900 border border-brand-500/20 dark:border-brand-500/30 mb-4 text-brand-600 dark:text-brand-300 text-lg font-bold shadow-xl shadow-slate-200/50 dark:shadow-brand-500/10 backdrop-blur-md">AI</div>
                    <h1 className="text-3xl font-bold text-slate-900 dark:text-white tracking-tight">Reset link unavailable</h1>
                </div>
                <div className="glass-panel rounded-2xl p-8 space-y-5 text-center">
                    <p className="text-sm text-slate-600 dark:text-gray-300">
                        This reset link cannot be used while self-service password recovery is disabled. Contact an administrator for account recovery.
                    </p>
                    <Link href="/contact" className="block w-full py-3 glass-button rounded-xl">Contact support</Link>
                    <Link href="/login" className="inline-block text-sm text-brand-600 dark:text-brand-400 hover:underline">Return to Sign In</Link>
                </div>
            </main>
        </div>
    );
}

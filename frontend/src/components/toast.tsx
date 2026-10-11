"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/icons";

export type ToastType = "success" | "error" | "info" | "warning";

interface Toast {
    id: string;
    type: ToastType;
    title: string;
    message?: string;
    duration?: number;
}

interface ToastContextValue {
    toasts: Toast[];
    addToast: (toast: Omit<Toast, "id">) => void;
    removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error("useToast must be used within ToastProvider");
    return ctx;
}

const TOAST_ICONS: Record<ToastType, IconName> = {
    success: "check",
    error: "close",
    info: "info",
    warning: "alert",
};

const TOAST_COLORS: Record<ToastType, { bg: string; border: string; icon: string; text: string }> = {
    success: {
        bg: "bg-emerald-50 dark:bg-emerald-500/10",
        border: "border-emerald-200 dark:border-emerald-500/20",
        icon: "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
        text: "text-emerald-800 dark:text-emerald-300",
    },
    error: {
        bg: "bg-red-50 dark:bg-red-500/10",
        border: "border-red-200 dark:border-red-500/20",
        icon: "bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400",
        text: "text-red-800 dark:text-red-300",
    },
    info: {
        bg: "bg-blue-50 dark:bg-blue-500/10",
        border: "border-blue-200 dark:border-blue-500/20",
        icon: "bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400",
        text: "text-blue-800 dark:text-blue-300",
    },
    warning: {
        bg: "bg-amber-50 dark:bg-amber-500/10",
        border: "border-amber-200 dark:border-amber-500/20",
        icon: "bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400",
        text: "text-amber-800 dark:text-amber-300",
    },
};

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
    const colors = TOAST_COLORS[toast.type];
    return (
        <div
            className={`flex items-start gap-3 px-4 py-3 rounded-xl border ${colors.bg} ${colors.border} backdrop-blur-xl shadow-lg animate-slide-in-right w-full sm:w-auto sm:min-w-[320px] max-w-[420px]`}
            role={toast.type === "error" || toast.type === "warning" ? "alert" : "status"}
        >
            <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${colors.icon}`}>
                <Icon name={TOAST_ICONS[toast.type]} className="h-3.5 w-3.5" />
            </div>
            <div className="flex-1 min-w-0">
                <p className={`text-sm font-semibold ${colors.text}`}>{toast.title}</p>
                {toast.message && (
                    <p className="text-xs text-slate-600 dark:text-gray-400 mt-0.5 leading-relaxed">{toast.message}</p>
                )}
            </div>
            <button
                type="button"
                onClick={onDismiss}
                aria-label="Dismiss"
                className="text-slate-500 dark:text-gray-400 hover:text-slate-700 dark:hover:text-gray-200 transition-colors shrink-0 mt-0.5"
            >
                <Icon name="close" className="h-4 w-4" />
            </button>
        </div>
    );
}

export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const removeToast = useCallback((id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const addToast = useCallback(
        (toast: Omit<Toast, "id">) => {
            const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
            setToasts((prev) => [...prev, { ...toast, id }]);
            const duration = toast.duration ?? 4000;
            if (duration > 0) {
                setTimeout(() => removeToast(id), duration);
            }
        },
        [removeToast]
    );

    return (
        <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
            {children}
            {/* Toast container */}
            <div className="fixed top-4 left-4 right-4 sm:left-auto sm:top-6 sm:right-6 z-[9999] flex flex-col items-end gap-2 pointer-events-none">
                {toasts.map((toast) => (
                    <div key={toast.id} className="pointer-events-auto">
                        <ToastItem toast={toast} onDismiss={() => removeToast(toast.id)} />
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
}

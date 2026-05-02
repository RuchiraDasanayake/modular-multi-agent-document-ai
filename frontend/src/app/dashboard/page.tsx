"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import StatCard from "@/components/stat-card";
import { useUser } from "@/hooks/use-user";

interface Stats {
    total_advice: number;
    total_outcomes: number;
    total_ltm_policies: number;
    total_experiments: number;
    total_users: number;
}

interface ServiceHealth {
    name: string;
    status: "healthy" | "degraded" | "offline";
    latency?: number;
}

const SERVICES = [
    { key: "gateway", label: "API Gateway", icon: "🔀" },
    { key: "ahmn", label: "AHMN Core", icon: "🎯" },
    { key: "guardrails", label: "Guardrails", icon: "🛡️" },
    { key: "xai", label: "XAI Engine", icon: "🔍" },
];

function HealthDot({ status }: { status: ServiceHealth["status"] }) {
    const color = status === "healthy" ? "bg-emerald-500" : status === "degraded" ? "bg-amber-500" : "bg-red-500";
    return (
        <span className="relative flex h-2.5 w-2.5">
            {status === "healthy" && <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${color} opacity-40`} />}
            <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${color}`} />
        </span>
    );
}

const ALGO_COLOR_MAP: Record<string, { border: string; bg: string; glow: string }> = {
    emerald: {
        border: "border-emerald-200/60 dark:border-emerald-500/15",
        bg: "bg-gradient-to-br from-emerald-50/50 to-white dark:from-emerald-500/5 dark:to-gray-900/50",
        glow: "bg-emerald-400/10",
    },
    cyan: {
        border: "border-cyan-200/60 dark:border-cyan-500/15",
        bg: "bg-gradient-to-br from-cyan-50/50 to-white dark:from-cyan-500/5 dark:to-gray-900/50",
        glow: "bg-cyan-400/10",
    },
    violet: {
        border: "border-violet-200/60 dark:border-violet-500/15",
        bg: "bg-gradient-to-br from-violet-50/50 to-white dark:from-violet-500/5 dark:to-gray-900/50",
        glow: "bg-violet-400/10",
    },
};

const PIPELINE_STEPS = [
    { icon: "📥", label: "Upload", desc: "Drag & drop files" },
    { icon: "🎯", label: "AHMN", desc: "Adaptive top-1 advice" },
    { icon: "📄", label: "IDPO", desc: "Safe execution layer" },
    { icon: "🛡️", label: "Validate", desc: "Fallback and rollback" },
    { icon: "🔍", label: "XAI", desc: "Transparency and tracing" },
    { icon: "📊", label: "HITL", desc: "Expert feedback loop" },
];

export default function DashboardOverview() {
    const { isAdmin } = useUser();
    const [stats, setStats] = useState<Stats | null>(null);
    const [activity, setActivity] = useState<{ type: string; detail: string; metric: string; created_at: string }[]>([]);
    const [health, setHealth] = useState<ServiceHealth[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([api.getStats(), api.getActivity()])
            .then(([s, a]) => {
                setStats(s);
                setActivity(a as typeof activity);
            })
            .catch((err) => { console.error("Dashboard stats fetch failed:", err); })
            .finally(() => setLoading(false));

        async function checkHealth() {
            try {
                const data = await api.request<{ services: ServiceHealth[] }>("/api/services/health");
                setHealth(data.services.map(s => ({
                    name: s.name,
                    status: s.status,
                    latency: s.latency,
                })));
            } catch {
                // If the unified endpoint fails, mark all as offline except gateway
                setHealth(SERVICES.map(s => ({
                    name: s.key,
                    status: "offline" as const,
                })));
            }
        }
        checkHealth();
        const interval = setInterval(checkHealth, 30000);
        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    const healthyCount = health.filter((h) => h.status === "healthy").length;

    return (
        <div className="max-w-7xl 3xl:max-w-[1800px] mx-auto space-y-4 sm:space-y-6">
            {/* ── Hero: Document Extraction CTA ── */}
            <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-brand-500 via-cyan-500 to-brand-600 dark:from-brand-600 dark:via-cyan-600 dark:to-brand-700 p-5 sm:p-8 shadow-2xl shadow-brand-500/25 border border-white/10">
                {/* Background pattern */}
                <div className="absolute inset-0 opacity-10">
                    <div className="absolute top-0 right-0 w-96 h-96 bg-white rounded-full blur-3xl -translate-y-1/2 translate-x-1/3" />
                    <div className="absolute bottom-0 left-0 w-64 h-64 bg-white rounded-full blur-3xl translate-y-1/3 -translate-x-1/4" />
                    <svg className="absolute inset-0 w-full h-full" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                            <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
                                <path d="M 32 0 L 0 0 0 32" fill="none" stroke="white" strokeWidth="0.5" opacity="0.3" />
                            </pattern>
                        </defs>
                        <rect width="100%" height="100%" fill="url(#grid)" />
                    </svg>
                </div>

                <div className="relative z-10 flex flex-col lg:flex-row items-center justify-between gap-6">
                    <div className="flex-1">
                        <div className="flex items-center gap-2 mb-3">
                            {health.length > 0 && (
                                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/20 backdrop-blur-sm">
                                    <span className={`w-2 h-2 rounded-full ${healthyCount === SERVICES.length ? "bg-emerald-300 animate-pulse" : "bg-amber-300"}`} />
                                    <span className="text-[10px] font-semibold text-white/90">{healthyCount}/{SERVICES.length} Online</span>
                                </div>
                            )}
                        </div>
                        <h1 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-white tracking-tight leading-tight">
                            Integrated Research<br />Document System
                        </h1>
                        <p className="text-white/75 mt-3 max-w-lg text-sm leading-relaxed">
                            The full system combines AHMN, IDPO, XAI, and HITL. The main runtime path focuses on fixed AHMN advice plus safe IDPO execution.
                        </p>

                        {/* Inline pipeline mini-viz */}
                        <div className="flex items-center gap-1 mt-5 overflow-x-auto pb-1">
                            {PIPELINE_STEPS.map((step, i) => (
                                <div key={step.label} className="flex items-center gap-1 flex-shrink-0">
                                    <div className="flex flex-col items-center gap-0.5">
                                        <div className="w-8 h-8 rounded-lg bg-white/20 backdrop-blur-sm flex items-center justify-center text-sm border border-white/20">
                                            {step.icon}
                                        </div>
                                        <span className="text-[8px] text-white/70 font-medium">{step.label}</span>
                                    </div>
                                    {i < PIPELINE_STEPS.length - 1 && (
                                        <svg className="w-3 h-3 text-white/40 flex-shrink-0 -mt-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                                        </svg>
                                    )}
                                </div>
                            ))}
                            <div className="flex items-center -mt-3 ml-0.5">
                                <svg className="w-4 h-4 text-white/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                            </div>
                        </div>
                    </div>

                    {/* CTA */}
                    <div className="flex flex-col items-center gap-3 flex-shrink-0 w-full sm:w-auto">
                        <Link
                            href="/dashboard/idpo"
                            className="group flex items-center gap-3 px-6 sm:px-8 py-3 sm:py-4 rounded-2xl bg-white/95 backdrop-blur-md text-brand-700 font-bold text-sm sm:text-base shadow-xl shadow-black/10 hover:shadow-2xl hover:shadow-brand-500/20 hover:scale-105 active:scale-100 transition-all duration-200 border border-white/60 w-full sm:w-auto justify-center"
                        >
                            <svg className="w-6 h-6 text-brand-500 group-hover:rotate-6 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                            </svg>
                            Extract Documents
                            <svg className="w-5 h-5 opacity-50 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                            </svg>
                        </Link>
                        <span className="text-[10px] text-white/50 font-medium">PDF, PNG, JPG, TIFF, TXT, JSON</span>
                    </div>
                </div>
            </div>

            {/* ── Stat Cards ── */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 3xl:gap-4">
                <StatCard icon="📄" label="Documents Processed" value={stats?.total_outcomes ?? 0} />
                <StatCard icon="🎯" label="Learned Policies" value={stats?.total_ltm_policies ?? 0} />
                <StatCard icon="🧪" label="Experiments" value={stats?.total_experiments ?? 0} />
                <StatCard icon="👥" label="Total Users" value={stats?.total_users ?? 0} />
                <StatCard icon="⚡" label="Active Sessions" value={stats?.total_advice ?? 0} />
            </div>

            {/* ── Quick Actions Grid + Service Health ── */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 sm:gap-5 3xl:gap-6">
                <div className="xl:col-span-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    <Link href="/dashboard/idpo" className="group glass-card-glow rounded-2xl p-5 flex flex-col gap-3 hover:border-brand-300 dark:hover:border-brand-500/30">
                        <div className="w-11 h-11 rounded-xl bg-brand-50 dark:bg-brand-500/10 border border-brand-200/60 dark:border-brand-500/20 flex items-center justify-center text-xl group-hover:scale-110 transition-transform">
                            📄
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">IDPO Runtime</h3>
                            <p className="text-xs text-slate-500 dark:text-gray-400 mt-0.5">Run the live document pipeline in static or adaptive_safe mode</p>
                        </div>
                    </Link>
                    <Link href="/dashboard/idpo/benchmark" className="group glass-card-glow rounded-2xl p-5 flex flex-col gap-3 hover:border-cyan-300 dark:hover:border-cyan-500/30">
                        <div className="w-11 h-11 rounded-xl bg-cyan-50 dark:bg-cyan-500/10 border border-cyan-200/60 dark:border-cyan-500/20 flex items-center justify-center text-xl group-hover:scale-110 transition-transform">
                            📊
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Benchmark Results</h3>
                            <p className="text-xs text-slate-500 dark:text-gray-400 mt-0.5">Review static versus adaptive_safe performance and quality reports</p>
                        </div>
                    </Link>
                    <Link href="/dashboard/xai" className="group glass-card-glow rounded-2xl p-5 flex flex-col gap-3 hover:border-violet-300 dark:hover:border-violet-500/30">
                        <div className="w-11 h-11 rounded-xl bg-violet-50 dark:bg-violet-500/10 border border-violet-200/60 dark:border-violet-500/20 flex items-center justify-center text-xl group-hover:scale-110 transition-transform">
                            💬
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">AI Q&A</h3>
                            <p className="text-xs text-slate-500 dark:text-gray-400 mt-0.5">Ask questions about any document context with DistilBERT explainability</p>
                        </div>
                    </Link>
                    <Link href="/dashboard/guardrails" className="group glass-card-glow rounded-2xl p-5 flex flex-col gap-3 hover:border-emerald-300 dark:hover:border-emerald-500/30">
                        <div className="w-11 h-11 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200/60 dark:border-emerald-500/20 flex items-center justify-center text-xl group-hover:scale-110 transition-transform">
                            🛡️
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Quality Checks</h3>
                            <p className="text-xs text-slate-500 dark:text-gray-400 mt-0.5">5-layer validation: schema, semantic, faithfulness, bias, PII</p>
                        </div>
                    </Link>
                    <Link href="/dashboard/hitl" className="group glass-card-glow rounded-2xl p-5 flex flex-col gap-3 hover:border-amber-300 dark:hover:border-amber-500/30">
                        <div className="w-11 h-11 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200/60 dark:border-amber-500/20 flex items-center justify-center text-xl group-hover:scale-110 transition-transform">
                            👤
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Expert Review</h3>
                            <p className="text-xs text-slate-500 dark:text-gray-400 mt-0.5">Submit human feedback to improve AI accuracy over time</p>
                        </div>
                    </Link>
                </div>

                {/* Service Health Panel */}
                <div className="glass-panel rounded-2xl p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-sm font-bold text-slate-900 dark:text-white">Service Health</h2>
                        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-100 dark:bg-gray-800 border border-slate-200/60 dark:border-gray-700">
                            <HealthDot status={healthyCount === SERVICES.length ? "healthy" : healthyCount > 0 ? "degraded" : "offline"} />
                            <span className="text-[10px] font-medium text-slate-500 dark:text-gray-400">
                                {healthyCount}/{SERVICES.length}
                            </span>
                        </div>
                    </div>
                    {health.length === 0 ? (
                        <div className="space-y-2">
                            {SERVICES.map((s) => (
                                <div key={s.key} className="flex items-center gap-3 p-2.5 rounded-xl bg-slate-50 dark:bg-gray-800/50 animate-pulse">
                                    <div className="w-7 h-7 rounded-lg bg-slate-200 dark:bg-gray-700" />
                                    <div className="flex-1">
                                        <div className="h-2.5 w-20 bg-slate-200 dark:bg-gray-700 rounded" />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="space-y-1.5">
                            {SERVICES.map((svc) => {
                                const h = health.find((s) => s.name === svc.key);
                                return (
                                    <div key={svc.key} className="flex items-center gap-3 p-2.5 rounded-xl bg-slate-50/60 dark:bg-gray-800/30 border border-slate-100/80 dark:border-gray-800/80 hover:bg-slate-100/60 dark:hover:bg-gray-800/50 transition-colors">
                                        <span className="text-sm">{svc.icon}</span>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs font-medium text-slate-700 dark:text-gray-300">{svc.label}</p>
                                            {h?.latency && (
                                                <p className="text-[9px] text-slate-400 dark:text-gray-500">{h.latency}ms</p>
                                            )}
                                        </div>
                                        <HealthDot status={h?.status || "offline"} />
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>

            {/* ── AI Capabilities + Recent Activity ── */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 sm:gap-5 3xl:gap-6">
                <div className="xl:col-span-2 glass-panel rounded-2xl p-5 sm:p-6 relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-40 h-40 bg-gradient-to-br from-brand-500/5 to-cyan-500/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/4 pointer-events-none" />
                    <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-1 relative z-10">Research Modules</h2>
                    <p className="text-xs text-slate-500 dark:text-gray-500 mb-4 relative z-10">AHMN, IDPO, XAI, and HITL remain part of one integrated research system</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {[
                            {
                                icon: "🎯",
                                title: "Thompson Sampling",
                                desc: "Bayesian bandit for automatic strategy selection with principled exploration-exploitation.",
                                color: "emerald",
                            },
                            {
                                icon: "🧊",
                                title: "RABI Cold Start",
                                desc: "Retrieval-Augmented Bayesian Inference transfers prior distributions from similar document types.",
                                color: "cyan",
                            },
                            {
                                icon: "🌊",
                                title: "DAAF Drift Detection",
                                desc: "Drift-Aware Adaptive Forgetting detects format changes and adjusts memory accordingly.",
                                color: "violet",
                            },
                        ].map((item) => {
                            const colors = ALGO_COLOR_MAP[item.color];
                            return (
                                <div
                                    key={item.title}
                                    className={`group relative p-4 rounded-xl border overflow-hidden transition-all duration-200 hover:-translate-y-0.5 cursor-default
                                    ${colors.border} ${colors.bg}`}
                                >
                                    <div className={`absolute top-0 right-0 w-20 h-20 ${colors.glow} rounded-full blur-2xl -translate-y-6 translate-x-6 group-hover:scale-150 transition-transform duration-500`} />
                                    <span className="text-2xl relative z-10">{item.icon}</span>
                                    <h3 className="font-semibold text-slate-900 dark:text-white text-sm mt-2.5 relative z-10">{item.title}</h3>
                                    <p className="text-[11px] text-slate-600 dark:text-gray-400 mt-1.5 leading-relaxed relative z-10">{item.desc}</p>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Recent Activity */}
                <div className="glass-panel rounded-2xl p-5">
                    <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-3">Recent Activity</h2>
                    {activity.length === 0 ? (
                        <div className="text-center py-8">
                            <div className="w-14 h-14 rounded-2xl bg-slate-100 dark:bg-gray-800 mx-auto flex items-center justify-center mb-3">
                                <span className="text-2xl">📭</span>
                            </div>
                            <p className="text-xs font-medium text-slate-500 dark:text-gray-400">No activity yet</p>
                            <p className="text-[10px] text-slate-400 dark:text-gray-600 mt-1">Process documents to see activity here</p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {activity.slice(0, 8).map((a, i) => (
                                <div key={i} className="flex items-center gap-2.5 p-2 rounded-lg hover:bg-slate-50/60 dark:hover:bg-gray-800/30 transition-colors animate-fade-in" style={{ animationDelay: `${i * 50}ms` }}>
                                    <div className="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0" />
                                    <span className="text-slate-700 dark:text-gray-300 text-[11px] truncate flex-1">{a.detail}</span>
                                    <span className="text-slate-400 dark:text-gray-500 text-[10px] font-mono flex-shrink-0">F1: {a.metric}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* ── Memory Architecture ── */}
            <div className="glass-panel rounded-2xl p-5 sm:p-6 relative overflow-hidden">
                <div className="absolute bottom-0 left-0 w-40 h-40 bg-gradient-to-br from-brand-500/5 to-cyan-500/5 rounded-full blur-3xl translate-y-1/2 -translate-x-1/4 pointer-events-none" />
                <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-1 relative z-10">Memory Architecture</h2>
                <p className="text-xs text-slate-500 dark:text-gray-500 mb-4 relative z-10">Three-tier adaptive memory system (STM → MTM → LTM)</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {[
                        { tier: "STM", store: "Redis Cache", ttl: "30 min", desc: "Transient advice context during processing", color: "red", icon: "⚡" },
                        { tier: "MTM", store: "PostgreSQL", ttl: "90 days", desc: "Raw outcome logs and processing history", color: "yellow", icon: "📋" },
                        { tier: "LTM", store: "pgvector", ttl: "Permanent", desc: "Validated policies with Beta distributions", color: "green", icon: "🎯" },
                    ].map((m, i) => (
                        <div key={m.tier} className="relative group">
                            <div className="p-4 rounded-xl border border-white/50 dark:border-white/[0.06] bg-white/50 dark:bg-gray-800/30 backdrop-blur-lg hover:shadow-lg hover:shadow-brand-500/5 hover:bg-white/70 dark:hover:bg-gray-800/50 transition-all duration-300">
                                <div className="flex items-center gap-2 mb-2.5">
                                    <span className="text-lg">{m.icon}</span>
                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${m.color === "red" ? "bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400" :
                                        m.color === "yellow" ? "bg-yellow-100 dark:bg-yellow-500/20 text-yellow-600 dark:text-yellow-400" :
                                            "bg-green-100 dark:bg-green-500/20 text-green-600 dark:text-green-400"
                                        }`}>
                                        {m.tier}
                                    </span>
                                    <span className="text-[9px] text-slate-400 dark:text-gray-500 ml-auto font-mono">{m.store}</span>
                                </div>
                                <p className="text-xs text-slate-700 dark:text-gray-300 leading-relaxed">{m.desc}</p>
                                <div className="flex items-center gap-1.5 mt-2">
                                    <span className="text-[9px] text-slate-400 dark:text-gray-500">TTL:</span>
                                    <span className="text-[9px] font-semibold text-slate-600 dark:text-gray-300">{m.ttl}</span>
                                </div>
                            </div>
                            {i < 2 && (
                                <div className="hidden md:flex absolute -right-2.5 top-1/2 -translate-y-1/2 z-10">
                                    <svg className="w-4 h-4 text-slate-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                                    </svg>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

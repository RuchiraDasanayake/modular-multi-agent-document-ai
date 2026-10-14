"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import StatCard from "@/components/stat-card";
import { Icon, type IconName } from "@/components/icons";

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

interface ActivityItem {
    type: string;
    detail: string | null;
    metric: string | null;
    created_at: string | null;
}

const SERVICES: { key: string; label: string; icon: IconName }[] = [
    { key: "gateway", label: "API Gateway", icon: "layers" },
    { key: "ahmn", label: "AHMN Core", icon: "activity" },
    { key: "guardrails", label: "Guardrails", icon: "shield" },
    { key: "xai", label: "XAI Engine", icon: "chat" },
];

const PIPELINE_STEPS: { icon: IconName; label: string }[] = [
    { icon: "upload", label: "Upload" },
    { icon: "activity", label: "Route" },
    { icon: "document", label: "Extract" },
    { icon: "shield", label: "Validate" },
    { icon: "userCheck", label: "Review" },
];

const QUICK_ACTIONS: { href: string; title: string; description: string; icon: IconName; tone: string }[] = [
    {
        href: "/dashboard/idpo",
        title: "Research pipeline",
        description: "Inspect experimental policy-routing jobs in the separately configured research runtime.",
        icon: "document",
        tone: "bg-brand-50 text-brand-600 border-brand-200/60 dark:bg-brand-500/10 dark:text-brand-300 dark:border-brand-500/20",
    },
    {
        href: "/dashboard/idpo/benchmark",
        title: "Benchmark results",
        description: "Compare static and adaptive runs on the same documents.",
        icon: "chart",
        tone: "bg-cyan-50 text-cyan-600 border-cyan-200/60 dark:bg-cyan-500/10 dark:text-cyan-300 dark:border-cyan-500/20",
    },
    {
        href: "/dashboard/xai",
        title: "AI Q&A",
        description: "Ask a question about a passage and see which words drove the answer.",
        icon: "chat",
        tone: "bg-violet-50 text-violet-600 border-violet-200/60 dark:bg-violet-500/10 dark:text-violet-300 dark:border-violet-500/20",
    },
    {
        href: "/dashboard/guardrails",
        title: "Quality checks",
        description: "Check an extraction for schema errors, inconsistencies, rule breaks, PII and unsupported values.",
        icon: "shield",
        tone: "bg-emerald-50 text-emerald-600 border-emerald-200/60 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20",
    },
    {
        href: "/dashboard/hitl",
        title: "Expert review",
        description: "Rate AI answers and record corrections as feedback.",
        icon: "userCheck",
        tone: "bg-amber-50 text-amber-600 border-amber-200/60 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20",
    },
];

const RESEARCH_COMPONENTS: { title: string; description: string; live: boolean }[] = [
    {
        title: "Thompson sampling",
        description: "Experimental policy selection from Beta posteriors with a default-policy safety gate. Not used by the confirmed-schema workspace.",
        live: true,
    },
    {
        title: "RABI cold start",
        description: "Transfers priors from similar document types. Evaluated in the simulator only; not used by the document pipeline.",
        live: false,
    },
    {
        title: "DAAF drift detection",
        description: "Detects drift and down-weights stale evidence. Evaluated in the simulator only; not used by the document pipeline.",
        live: false,
    },
];

const MEMORY_TIERS = [
    { tier: "STM", store: "Redis", retention: "Kept for 30 minutes", desc: "Advice context while a document is processed" },
    { tier: "MTM", store: "PostgreSQL", retention: "Kept for 90 days", desc: "Outcome logs and processing history" },
    { tier: "LTM", store: "pgvector", retention: "Kept permanently", desc: "Validated policies with Beta posteriors" },
];

function HealthDot({ status }: { status: ServiceHealth["status"] }) {
    const color = status === "healthy" ? "bg-emerald-500" : status === "degraded" ? "bg-amber-500" : "bg-red-500";
    return (
        <span className="relative flex h-2.5 w-2.5" aria-label={status} title={status}>
            {status === "healthy" && <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${color} opacity-40`} />}
            <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${color}`} />
        </span>
    );
}

function formatRelativeTime(value: string | null): string {
    if (!value) {
        return "";
    }
    const time = new Date(value).getTime();
    if (Number.isNaN(time)) {
        return "";
    }
    const minutes = Math.round((Date.now() - time) / 60000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} h ago`;
    return `${Math.round(hours / 24)} d ago`;
}

function formatReward(value: string | null): string | null {
    const parsed = value === null ? Number.NaN : Number(value);
    return Number.isFinite(parsed) ? parsed.toFixed(2) : null;
}

export default function DashboardOverview() {
    const [stats, setStats] = useState<Stats | null>(null);
    const [activity, setActivity] = useState<ActivityItem[]>([]);
    const [health, setHealth] = useState<ServiceHealth[]>([]);
    const [loading, setLoading] = useState(true);
    const [statsError, setStatsError] = useState(false);

    const loadStats = useCallback(() => {
        setLoading(true);
        setStatsError(false);
        Promise.all([api.getStats(), api.getActivity()])
            .then(([s, a]) => {
                setStats(s as unknown as Stats);
                setActivity(a as ActivityItem[]);
            })
            .catch((err) => {
                console.error("Dashboard stats fetch failed:", err);
                setStatsError(true);
            })
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        loadStats();

        async function checkHealth() {
            try {
                const data = await api.request<{ services: ServiceHealth[] }>("/api/services/health");
                setHealth(data.services.map(s => ({
                    name: s.name,
                    status: s.status,
                    latency: s.latency,
                })));
            } catch {
                setHealth(SERVICES.map(s => ({
                    name: s.key,
                    status: "offline" as const,
                })));
            }
        }
        checkHealth();
        const interval = setInterval(checkHealth, 30000);
        return () => clearInterval(interval);
    }, [loadStats]);

    const visibleHealth = SERVICES.map((service) => health.find((entry) => entry.name === service.key)).filter(
        (entry): entry is ServiceHealth => Boolean(entry),
    );
    const healthyCount = visibleHealth.filter((entry) => entry.status === "healthy").length;

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
                        <div className="flex items-center gap-2 mb-3 min-h-[22px]">
                            {health.length > 0 && (
                                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/20 backdrop-blur-sm">
                                    <span className={`w-2 h-2 rounded-full ${healthyCount === SERVICES.length ? "bg-emerald-300 animate-pulse" : "bg-amber-300"}`} />
                                    <span className="text-[11px] font-semibold text-white/90">{healthyCount} of {SERVICES.length} research services online</span>
                                </div>
                            )}
                        </div>
                        <h1 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-white tracking-tight leading-tight">
                            Research overview
                        </h1>
                        <p className="text-white/85 mt-3 max-w-xl text-sm leading-relaxed">
                            These experiments and services are separate from the extraction workspace. Use the workspace to confirm fields, preview files and review results before export.
                        </p>

                        {/* Inline pipeline mini-viz */}
                        <ol className="flex items-center gap-1 mt-5 overflow-x-auto pb-1" aria-label="Pipeline steps">
                            {PIPELINE_STEPS.map((step, i) => (
                                <li key={step.label} className="flex items-center gap-1 flex-shrink-0">
                                    <div className="flex flex-col items-center gap-1">
                                        <div className="w-9 h-9 rounded-lg bg-white/20 backdrop-blur-sm flex items-center justify-center text-white border border-white/20">
                                            <Icon name={step.icon} className="h-4 w-4" />
                                        </div>
                                        <span className="text-[10px] text-white/80 font-medium">{step.label}</span>
                                    </div>
                                    {i < PIPELINE_STEPS.length - 1 && (
                                        <Icon name="arrowRight" className="w-3 h-3 text-white/50 flex-shrink-0 -mt-4 mx-0.5" />
                                    )}
                                </li>
                            ))}
                        </ol>
                    </div>

                    {/* CTA */}
                    <div className="flex flex-col items-center gap-3 flex-shrink-0 w-full sm:w-auto">
                        <Link
                            href="/dashboard/idpo/jobs"
                            className="group flex items-center gap-3 px-6 sm:px-8 py-3 sm:py-4 rounded-2xl bg-white/95 backdrop-blur-md text-brand-700 font-bold text-sm sm:text-base shadow-xl shadow-black/10 hover:shadow-2xl hover:shadow-brand-500/20 hover:scale-105 active:scale-100 transition-all duration-200 border border-white/60 w-full sm:w-auto justify-center"
                        >
                            <Icon name="upload" className="w-5 h-5 text-brand-500" />
                            Extract documents
                            <Icon name="arrowRight" className="w-4 h-4 opacity-60 group-hover:translate-x-1 transition-transform" />
                        </Link>
                        <span className="text-[11px] text-white/70 font-medium">PDF, images, text, office documents and email</span>
                    </div>
                </div>
            </div>

            {/* ── Stat Cards ── */}
            {statsError && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200">
                    <span>Statistics are unavailable because AHMN Core did not respond.</span>
                    <button
                        type="button"
                        onClick={loadStats}
                        className="rounded-lg border border-amber-300 px-3 py-1 text-xs font-semibold hover:bg-amber-100 dark:border-amber-500/30 dark:hover:bg-amber-500/10"
                    >
                        Try again
                    </button>
                </div>
            )}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 3xl:gap-4">
                <StatCard loading={loading} icon={<Icon name="document" className="h-5 w-5" />} label="Outcomes logged" hint="Documents reported back to AHMN" value={stats?.total_outcomes ?? "—"} />
                <StatCard loading={loading} icon={<Icon name="layers" className="h-5 w-5" />} label="Validated policies" hint="Long-term memory" value={stats?.total_ltm_policies ?? "—"} />
                <StatCard loading={loading} icon={<Icon name="flask" className="h-5 w-5" />} label="Experiment runs" hint="Stored simulator runs" value={stats?.total_experiments ?? "—"} />
                <StatCard loading={loading} icon={<Icon name="users" className="h-5 w-5" />} label="Users" hint="Accounts on this system" value={stats?.total_users ?? "—"} />
                <StatCard loading={loading} icon={<Icon name="activity" className="h-5 w-5" />} label="Live advice" hint="Short-term memory, 30-minute expiry" value={stats?.total_advice ?? "—"} />
            </div>

            {/* ── Quick Actions Grid + Service Health ── */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 sm:gap-5 3xl:gap-6">
                <div className="xl:col-span-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {QUICK_ACTIONS.map((action) => (
                        <Link key={action.href} href={action.href} className="group glass-card-glow rounded-2xl p-5 flex flex-col gap-3">
                            <div className={`w-11 h-11 rounded-xl border flex items-center justify-center group-hover:scale-110 transition-transform ${action.tone}`}>
                                <Icon name={action.icon} className="h-5 w-5" />
                            </div>
                            <div>
                                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{action.title}</h3>
                                <p className="text-xs text-slate-500 dark:text-gray-400 mt-1 leading-relaxed">{action.description}</p>
                            </div>
                        </Link>
                    ))}
                </div>

                {/* Service Health Panel */}
                <div className="glass-panel rounded-2xl p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-sm font-bold text-slate-900 dark:text-white">Research service health</h2>
                        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-100 dark:bg-gray-800 border border-slate-200/60 dark:border-gray-700">
                            <HealthDot status={healthyCount === SERVICES.length ? "healthy" : healthyCount > 0 ? "degraded" : "offline"} />
                            <span className="text-[11px] font-medium text-slate-500 dark:text-gray-400">
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
                                const status = h?.status ?? "offline";
                                return (
                                    <div key={svc.key} className="flex items-center gap-3 p-2.5 rounded-xl bg-slate-50/60 dark:bg-gray-800/30 border border-slate-100/80 dark:border-gray-800/80">
                                        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-white text-slate-500 shadow-sm dark:bg-gray-800 dark:text-gray-400">
                                            <Icon name={svc.icon} className="h-4 w-4" />
                                        </span>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs font-medium text-slate-700 dark:text-gray-300">{svc.label}</p>
                                            <p className="text-[11px] text-slate-400 dark:text-gray-500">
                                                {status === "healthy"
                                                    ? typeof h?.latency === "number" && h.latency > 0
                                                        ? `Responding in ${Math.round(h.latency)} ms`
                                                        : "Responding"
                                                    : status === "degraded"
                                                        ? "Responding with errors"
                                                        : "Not reachable"}
                                            </p>
                                        </div>
                                        <HealthDot status={status} />
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>

            {/* ── Research components + Recent Activity ── */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 sm:gap-5 3xl:gap-6">
                <div className="xl:col-span-2 glass-panel rounded-2xl p-5 sm:p-6">
                    <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Research components</h2>
                    <p className="text-xs text-slate-500 dark:text-gray-400 mb-4">Components of the experimental pipeline and simulator. These are separate from the confirmed-schema extraction workspace.</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {RESEARCH_COMPONENTS.map((item) => (
                            <div key={item.title} className="rounded-xl border border-slate-200/70 bg-white/60 p-4 dark:border-gray-800 dark:bg-gray-900/40">
                                <span
                                    className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${item.live
                                        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
                                        : "bg-slate-100 text-slate-600 dark:bg-gray-800 dark:text-gray-300"
                                        }`}
                                >
                                    {item.live ? "Research pipeline" : "Simulation"}
                                </span>
                                <h3 className="font-semibold text-slate-900 dark:text-white text-sm mt-2.5">{item.title}</h3>
                                <p className="text-xs text-slate-600 dark:text-gray-400 mt-1.5 leading-relaxed">{item.description}</p>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Recent Activity */}
                <div className="glass-panel rounded-2xl p-5">
                    <h2 className="text-sm font-bold text-slate-900 dark:text-white">AHMN research outcomes</h2>
                    <p className="text-xs text-slate-500 dark:text-gray-400 mb-3">Policy used and the label-free reward sent to AHMN.</p>
                    {loading ? (
                        <div className="space-y-2">
                            {[0, 1, 2].map((i) => (
                                <div key={i} className="h-7 rounded-lg bg-slate-100 dark:bg-gray-800/60 animate-pulse" />
                            ))}
                        </div>
                    ) : statsError ? (
                        <div className="py-8 text-center">
                            <p className="text-xs font-medium text-slate-500 dark:text-gray-400">Research outcomes unavailable</p>
                            <p className="mt-1 text-[11px] text-slate-400 dark:text-gray-500">View document reviews in the extraction workspace.</p>
                        </div>
                    ) : activity.length === 0 ? (
                        <div className="text-center py-8">
                            <p className="text-xs font-medium text-slate-500 dark:text-gray-400">No outcomes yet</p>
                            <p className="text-[11px] text-slate-400 dark:text-gray-500 mt-1">Outcomes from the research pipeline appear here.</p>
                        </div>
                    ) : (
                        <ul className="space-y-1">
                            {activity.slice(0, 8).map((a, i) => {
                                const reward = formatReward(a.metric);
                                return (
                                    <li key={`${a.created_at ?? "item"}-${i}`} className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-slate-50/60 dark:hover:bg-gray-800/30">
                                        <span className="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0" />
                                        <span className="text-slate-700 dark:text-gray-300 text-xs truncate flex-1">{a.detail || "Unknown policy"}</span>
                                        {reward && (
                                            <span className="text-slate-500 dark:text-gray-400 text-[11px] font-mono flex-shrink-0" title="Label-free reward, not exact F1">
                                                reward {reward}
                                            </span>
                                        )}
                                        <span className="text-slate-400 dark:text-gray-500 text-[11px] flex-shrink-0 w-16 text-right">{formatRelativeTime(a.created_at)}</span>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>
            </div>

            {/* ── Memory Architecture ── */}
            <div className="glass-panel rounded-2xl p-5 sm:p-6">
                <h2 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Memory tiers</h2>
                <p className="text-xs text-slate-500 dark:text-gray-400 mb-4">Where AHMN keeps advice, outcomes and validated policies.</p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {MEMORY_TIERS.map((m) => (
                        <div key={m.tier} className="rounded-xl border border-slate-200/70 bg-white/60 p-4 dark:border-gray-800 dark:bg-gray-900/40">
                            <div className="flex items-center gap-2 mb-2">
                                <span className="rounded-md bg-brand-50 px-2 py-0.5 text-[11px] font-bold text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">{m.tier}</span>
                                <span className="text-[11px] text-slate-500 dark:text-gray-400 ml-auto">{m.store}</span>
                            </div>
                            <p className="text-xs text-slate-700 dark:text-gray-300 leading-relaxed">{m.desc}</p>
                            <p className="mt-2 text-[11px] text-slate-500 dark:text-gray-400">{m.retention}</p>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

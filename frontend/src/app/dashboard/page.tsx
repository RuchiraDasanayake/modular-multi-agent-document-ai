"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import StatCard from "@/components/stat-card";

interface Stats {
    total_advice: number;
    total_outcomes: number;
    total_ltm_policies: number;
    total_experiments: number;
    total_users: number;
}

export default function DashboardOverview() {
    const [stats, setStats] = useState<Stats | null>(null);
    const [activity, setActivity] = useState<{ type: string; detail: string; metric: string; created_at: string }[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([api.getStats(), api.getActivity()])
            .then(([s, a]) => {
                setStats(s);
                setActivity(a as typeof activity);
            })
            .catch(() => { })
            .finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Dashboard</h1>
                <p className="text-slate-500 dark:text-gray-400 mt-1">AHMN system overview — live data from PostgreSQL &amp; Redis</p>
            </div>

            {/* Stat Cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <StatCard icon="⚡" label="Active STM (Redis)" value={stats?.total_advice ?? 0} />
                <StatCard icon="📋" label="MTM Outcomes" value={stats?.total_outcomes ?? 0} />
                <StatCard icon="🧠" label="LTM Policies" value={stats?.total_ltm_policies ?? 0} />
                <StatCard icon="🧪" label="Experiment Runs" value={stats?.total_experiments ?? 0} />
                <StatCard icon="👥" label="Users" value={stats?.total_users ?? 0} />
            </div>

            {/* Architecture Quick View */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Innovations */}
                <div className="lg:col-span-2 glass-panel rounded-xl p-6">
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Core Innovations</h2>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {[
                            {
                                title: "Thompson Sampling",
                                desc: "Beta-Bernoulli bandit for policy selection with principled exploration-exploitation balance.",
                                bgLight: "bg-emerald-50",
                                bgDark: "dark:bg-emerald-500/10",
                                borderLight: "border-emerald-200",
                                borderDark: "dark:border-emerald-500/20",
                                hoverLight: "hover:bg-emerald-100",
                                hoverDark: "dark:hover:bg-emerald-500/20",
                            },
                            {
                                title: "RABI",
                                desc: "Retrieval-Augmented Bandit Initialization — solves cold-start via similarity-weighted knowledge transfer.",
                                bgLight: "bg-cyan-50",
                                bgDark: "dark:bg-cyan-500/10",
                                borderLight: "border-cyan-200",
                                borderDark: "dark:border-cyan-500/20",
                                hoverLight: "hover:bg-cyan-100",
                                hoverDark: "dark:hover:bg-cyan-500/20",
                            },
                            {
                                title: "DAAF",
                                desc: "Drift-Aware Adaptive Forgetting — separates noise from drift using γ* = √(Δ²/ln(t)).",
                                bgLight: "bg-violet-50",
                                bgDark: "dark:bg-violet-500/10",
                                borderLight: "border-violet-200",
                                borderDark: "dark:border-violet-500/20",
                                hoverLight: "hover:bg-violet-100",
                                hoverDark: "dark:hover:bg-violet-500/20",
                            },
                        ].map((item) => (
                            <div
                                key={item.title}
                                className={`p-4 rounded-lg border ${item.borderLight} ${item.borderDark} ${item.bgLight} ${item.bgDark} backdrop-blur-sm transition-all ${item.hoverLight} ${item.hoverDark}`}
                            >
                                <h3 className="font-medium text-slate-900 dark:text-white text-sm">{item.title}</h3>
                                <p className="text-xs text-slate-600 dark:text-gray-400 mt-1.5 leading-relaxed">{item.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Recent Activity */}
                <div className="glass-panel rounded-xl p-6">
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Recent Activity</h2>
                    {activity.length === 0 ? (
                        <p className="text-slate-500 dark:text-gray-500 text-sm">No activity yet. Use the API to generate data.</p>
                    ) : (
                        <div className="space-y-3">
                            {activity.slice(0, 8).map((a, i) => (
                                <div key={i} className="flex items-center gap-3 text-sm">
                                    <div className="w-2 h-2 rounded-full bg-brand-500" />
                                    <span className="text-slate-700 dark:text-gray-300 font-mono text-xs">{a.detail}</span>
                                    <span className="text-slate-500 dark:text-gray-500 ml-auto">F1: {a.metric}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Memory tier diagram */}
            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6 transition-colors duration-300">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Memory Architecture</h2>
                <div className="grid grid-cols-3 gap-4">
                    {[
                        { tier: "STM", store: "Redis", ttl: "30 min", desc: "Active request context", color: "red" },
                        { tier: "MTM", store: "PostgreSQL", ttl: "90 days", desc: "Raw outcome logs", color: "yellow" },
                        { tier: "LTM", store: "pgvector", ttl: "Permanent", desc: "Validated policies + embeddings", color: "green" },
                    ].map((m) => (
                        <div key={m.tier} className="p-4 rounded-lg border border-slate-200 dark:border-gray-700 bg-slate-50 dark:bg-gray-800">
                            <div className="flex items-center gap-2 mb-2">
                                <span className={`text-xs font-bold px-2 py-0.5 rounded ${m.color === 'red' ? 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400' :
                                        m.color === 'yellow' ? 'bg-yellow-100 dark:bg-yellow-500/20 text-yellow-600 dark:text-yellow-400' :
                                            'bg-green-100 dark:bg-green-500/20 text-green-600 dark:text-green-400'
                                    }`}>
                                    {m.tier}
                                </span>
                                <span className="text-xs text-slate-500 dark:text-gray-500">{m.store}</span>
                            </div>
                            <p className="text-sm text-slate-700 dark:text-gray-300">{m.desc}</p>
                            <p className="text-xs text-slate-500 dark:text-gray-500 mt-1">TTL: {m.ttl}</p>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

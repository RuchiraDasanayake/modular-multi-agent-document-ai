"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    BarChart, Bar, Cell, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from "recharts";

/* ─── Types ─── */
interface ResultEntry {
    method: string;
    scenario: string;
    seed: number;
    cumulative_regret: number;
    convergence_round: number | null;
    final_avg_reward: number;
    policy_accuracy: number;
}

interface ExperimentData {
    experiment_config: {
        n_seeds: number;
        methods: string[];
        scenarios: string[];
        total_time_seconds: number;
    };
    main_results: ResultEntry[];
    ablation_rabi_temperature?: Record<string, { mean_regret: number; std_regret: number; mean_f1: number }>;
    ablation_daaf_window?: Record<string, { mean_regret: number; std_regret: number; mean_f1: number }>;
    ablation_similarity_threshold?: Record<string, { mean_regret: number; std_regret: number; mean_f1: number }>;
}

interface ComparisonResult {
    ts_cumulative_regret: number[];
    daaf_cumulative_regret: number[];
    ts_rolling_reward: number[];
    daaf_rolling_reward: number[];
    rolling_start: number;
    total_ts_regret: number;
    total_daaf_regret: number;
    improvement_pct: number;
}

/* ─── Color palette ─── */
const METHOD_COLORS: Record<string, string> = {
    "Random": "#94a3b8",
    "ε-Greedy": "#f59e0b",
    "UCB1": "#06b6d4",
    "TS (base)": "#10b981",
    "AHMN-RABI": "#8b5cf6",
    "AHMN-DAAF": "#ef4444",
    "AHMN-Full": "#3b82f6",
};

const SCENARIO_LABELS: Record<string, string> = {
    stationary: "Stationary",
    cold_start: "Cold Start",
    concept_drift: "Concept Drift",
    combined: "Combined",
};

/* ─── Helpers ─── */
function avg(arr: number[]): number {
    return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
}

function std(arr: number[]): number {
    if (arr.length < 2) return 0;
    const m = avg(arr);
    return Math.sqrt(arr.reduce((s, v) => s + (v - m) ** 2, 0) / (arr.length - 1));
}

function Badge({ children, color = "gray" }: { children: React.ReactNode; color?: string }) {
    const colors: Record<string, string> = {
        green: "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20",
        red: "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20",
        blue: "bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-500/20",
        amber: "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/20",
        violet: "bg-violet-50 dark:bg-violet-500/10 text-violet-700 dark:text-violet-400 border-violet-200 dark:border-violet-500/20",
        gray: "bg-slate-50 dark:bg-gray-800 text-slate-600 dark:text-gray-400 border-slate-200 dark:border-gray-700",
    };
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${colors[color] || colors.gray}`}>
            {children}
        </span>
    );
}

/* ─── Aggregation ─── */
function aggregateResults(results: ResultEntry[]) {
    const groups: Record<string, ResultEntry[]> = {};
    for (const r of results) {
        const key = `${r.method}|${r.scenario}`;
        (groups[key] = groups[key] || []).push(r);
    }

    return Object.entries(groups).map(([key, entries]) => {
        const [method, scenario] = key.split("|");
        const regrets = entries.map(e => e.cumulative_regret);
        const rewards = entries.map(e => e.final_avg_reward);
        const accuracies = entries.map(e => e.policy_accuracy);
        return {
            method,
            scenario,
            seeds: entries.length,
            mean_regret: avg(regrets),
            std_regret: std(regrets),
            mean_reward: avg(rewards),
            mean_accuracy: avg(accuracies),
        };
    });
}

/* ─── Component ─── */
export default function ExperimentsPage() {
    const [data, setData] = useState<ExperimentData | null>(null);
    const [comparison, setComparison] = useState<ComparisonResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [compLoading, setCompLoading] = useState(false);
    const [error, setError] = useState("");
    const [driftMag, setDriftMag] = useState(0.2);
    const [seeds, setSeeds] = useState(10);
    const [selectedScenario, setSelectedScenario] = useState<string>("all");

    const loadResults = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const res = (await api.getResults()) as unknown as ExperimentData;
            setData(res);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load results");
        }
        setLoading(false);
    }, []);

    useEffect(() => { loadResults(); }, [loadResults]);

    const runComparison = async () => {
        setCompLoading(true);
        setError("");
        try {
            const res = (await api.runComparison({ drift_magnitude: driftMag, seeds })) as unknown as ComparisonResult;
            setComparison(res);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to run comparison");
        }
        setCompLoading(false);
    };

    const aggregated = data ? aggregateResults(data.main_results) : [];
    const filtered = selectedScenario === "all" ? aggregated : aggregated.filter(a => a.scenario === selectedScenario);

    const methodSummary = data
        ? data.experiment_config.methods.map(method => {
            const entries = (selectedScenario === "all" ? aggregated : filtered).filter(a => a.method === method);
            return {
                method,
                mean_regret: avg(entries.map(e => e.mean_regret)),
                mean_reward: avg(entries.map(e => e.mean_reward)),
                mean_accuracy: avg(entries.map(e => e.mean_accuracy)),
            };
        })
        : [];

    const radarData = data
        ? data.experiment_config.scenarios.map(sc => {
            const row: Record<string, string | number> = { scenario: SCENARIO_LABELS[sc] || sc };
            for (const m of ["TS (base)", "AHMN-RABI", "AHMN-DAAF", "AHMN-Full"]) {
                const entry = aggregated.find(a => a.method === m && a.scenario === sc);
                row[m] = entry ? Math.round(entry.mean_accuracy * 100) : 0;
            }
            return row;
        })
        : [];

    const chartData = comparison
        ? comparison.ts_cumulative_regret.map((ts, i) => ({
            round: i,
            "TS (no forgetting)": Math.round(ts * 100) / 100,
            "Adaptive Forgetting": Math.round(comparison.daaf_cumulative_regret[i] * 100) / 100,
        }))
        : [];

    const bestMethod = methodSummary.length
        ? methodSummary.reduce((best, m) => m.mean_regret < best.mean_regret ? m : best)
        : null;

    return (
        <div className="max-w-7xl 3xl:max-w-full mx-auto space-y-6">
            {/* Header */}
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6">
                <div className="absolute inset-0 bg-gradient-to-r from-blue-500/5 to-cyan-500/5 dark:from-blue-500/[0.03] dark:to-cyan-500/[0.03]" />
                <div className="relative">
                    <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-400 to-cyan-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                            <span className="text-white text-lg">📊</span>
                        </div>
                        AHMN Experiment Suite
                    </h1>
                    <p className="text-slate-500 dark:text-gray-400 mt-1.5 text-sm">
                        Empirical evaluation: 7 bandit strategies × 4 scenarios × 30 seeds = 840 runs
                    </p>
                </div>
            </div>

            {error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 text-sm text-red-700 dark:text-red-400">
                    {error}
                </div>
            )}

            {loading ? (
                <div className="flex items-center justify-center h-48">
                    <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                </div>
            ) : data ? (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="glass-panel rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500 uppercase tracking-wider font-semibold">Total Runs</p>
                            <p className="text-3xl font-black text-slate-900 dark:text-white mt-1">{data.main_results.length}</p>
                            <p className="text-[10px] text-slate-400 dark:text-gray-600 mt-0.5">{data.experiment_config.n_seeds} seeds each</p>
                        </div>
                        <div className="glass-panel rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500 uppercase tracking-wider font-semibold">Methods</p>
                            <p className="text-3xl font-black text-slate-900 dark:text-white mt-1">{data.experiment_config.methods.length}</p>
                            <p className="text-[10px] text-slate-400 dark:text-gray-600 mt-0.5">Bandit strategies</p>
                        </div>
                        <div className="glass-panel rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500 uppercase tracking-wider font-semibold">Best Method</p>
                            <p className="text-lg font-black text-blue-600 dark:text-blue-400 mt-1">{bestMethod?.method || "—"}</p>
                            <p className="text-[10px] text-slate-400 dark:text-gray-600 mt-0.5">Lowest avg regret</p>
                        </div>
                        <div className="glass-panel rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500 uppercase tracking-wider font-semibold">Compute Time</p>
                            <p className="text-3xl font-black text-slate-900 dark:text-white mt-1">{data.experiment_config.total_time_seconds.toFixed(0)}<span className="text-sm">s</span></p>
                            <p className="text-[10px] text-slate-400 dark:text-gray-600 mt-0.5">Full suite</p>
                        </div>
                    </div>

                    {/* Scenario Filter */}
                    <div className="flex flex-wrap gap-2">
                        {["all", ...data.experiment_config.scenarios].map(sc => (
                            <button
                                key={sc}
                                onClick={() => setSelectedScenario(sc)}
                                className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${selectedScenario === sc
                                    ? "bg-brand-500/10 dark:bg-brand-500/15 text-brand-700 dark:text-brand-300 border border-brand-200/60 dark:border-brand-500/20 shadow-sm"
                                    : "text-slate-600 dark:text-gray-400 hover:bg-slate-100 dark:hover:bg-gray-800 border border-transparent"
                                    }`}
                            >
                                {sc === "all" ? "All Scenarios" : SCENARIO_LABELS[sc] || sc}
                            </button>
                        ))}
                    </div>

                    {/* Regret Bar Chart */}
                    <div className="glass-panel rounded-2xl p-6">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Mean Cumulative Regret by Method</h2>
                        <p className="text-xs text-slate-500 dark:text-gray-500 mb-4">Lower is better — averaged across {selectedScenario === "all" ? "all scenarios" : SCENARIO_LABELS[selectedScenario]}</p>
                        <ResponsiveContainer width="100%" height={320}>
                            <BarChart data={methodSummary} layout="vertical" margin={{ left: 100 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                                <XAxis type="number" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                                <YAxis dataKey="method" type="category" stroke="#94a3b8" tick={{ fontSize: 12 }} width={100} />
                                <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "8px", fontSize: "13px" }} />
                                <Bar dataKey="mean_regret" name="Mean Regret" radius={[0, 6, 6, 0]} barSize={28}>
                                    {methodSummary.map((entry) => (
                                        <Cell key={entry.method} fill={METHOD_COLORS[entry.method] || "#94a3b8"} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Radar: Policy Accuracy */}
                        <div className="glass-panel rounded-2xl p-6">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Policy Selection Accuracy (%)</h2>
                            <p className="text-xs text-slate-500 dark:text-gray-500 mb-4">How often each method picks the optimal policy</p>
                            <ResponsiveContainer width="100%" height={300}>
                                <RadarChart data={radarData}>
                                    <PolarGrid stroke="#e2e8f0" />
                                    <PolarAngleAxis dataKey="scenario" tick={{ fontSize: 11 }} />
                                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
                                    <Radar name="TS (base)" dataKey="TS (base)" stroke="#10b981" fill="#10b981" fillOpacity={0.15} strokeWidth={2} />
                                    <Radar name="AHMN-RABI" dataKey="AHMN-RABI" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.15} strokeWidth={2} />
                                    <Radar name="AHMN-DAAF" dataKey="AHMN-DAAF" stroke="#ef4444" fill="#ef4444" fillOpacity={0.15} strokeWidth={2} />
                                    <Radar name="AHMN-Full" dataKey="AHMN-Full" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} strokeWidth={2} />
                                    <Legend />
                                    <Tooltip />
                                </RadarChart>
                            </ResponsiveContainer>
                        </div>

                        {/* Detailed Results Table */}
                        <div className="glass-panel rounded-2xl p-6 overflow-hidden">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Detailed Results</h2>
                            <p className="text-xs text-slate-500 dark:text-gray-500 mb-4">Per method-scenario averages over {data.experiment_config.n_seeds} seeds</p>
                            <div className="overflow-auto max-h-[320px]">
                                <table className="min-w-full text-xs">
                                    <thead className="bg-slate-50 dark:bg-gray-900/50 sticky top-0">
                                        <tr>
                                            <th className="px-3 py-2 text-left font-semibold text-slate-500 dark:text-gray-500 uppercase tracking-wider">Method</th>
                                            <th className="px-3 py-2 text-left font-semibold text-slate-500 dark:text-gray-500 uppercase tracking-wider">Scenario</th>
                                            <th className="px-3 py-2 text-right font-semibold text-slate-500 dark:text-gray-500 uppercase tracking-wider">Regret</th>
                                            <th className="px-3 py-2 text-right font-semibold text-slate-500 dark:text-gray-500 uppercase tracking-wider">Reward</th>
                                            <th className="px-3 py-2 text-right font-semibold text-slate-500 dark:text-gray-500 uppercase tracking-wider">Accuracy</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100 dark:divide-gray-800">
                                        {filtered.sort((a, b) => a.mean_regret - b.mean_regret).map((row, i) => (
                                            <tr key={i} className="hover:bg-slate-50/50 dark:hover:bg-gray-800/20">
                                                <td className="px-3 py-2">
                                                    <div className="flex items-center gap-2">
                                                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: METHOD_COLORS[row.method] || "#94a3b8" }} />
                                                        <span className="font-medium text-slate-700 dark:text-gray-300">{row.method}</span>
                                                    </div>
                                                </td>
                                                <td className="px-3 py-2 text-slate-500 dark:text-gray-400">{SCENARIO_LABELS[row.scenario] || row.scenario}</td>
                                                <td className="px-3 py-2 text-right font-mono font-semibold text-slate-700 dark:text-gray-300">
                                                    {row.mean_regret.toFixed(1)} <span className="text-slate-400 dark:text-gray-600">±{row.std_regret.toFixed(1)}</span>
                                                </td>
                                                <td className="px-3 py-2 text-right font-mono text-slate-700 dark:text-gray-300">{row.mean_reward.toFixed(3)}</td>
                                                <td className="px-3 py-2 text-right">
                                                    <Badge color={row.mean_accuracy >= 0.7 ? "green" : row.mean_accuracy >= 0.5 ? "amber" : "red"}>
                                                        {(row.mean_accuracy * 100).toFixed(1)}%
                                                    </Badge>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    {/* Ablation Studies */}
                    {(data.ablation_daaf_window || data.ablation_rabi_temperature || data.ablation_similarity_threshold) && (
                        <div className="glass-panel rounded-2xl p-6">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Ablation Studies</h2>
                            <p className="text-xs text-slate-500 dark:text-gray-500 mb-4">Sensitivity analysis of key hyperparameters</p>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                {data.ablation_daaf_window && (
                                    <div>
                                        <h3 className="text-sm font-semibold text-slate-700 dark:text-gray-300 mb-2">DAAF Window Size</h3>
                                        <div className="space-y-1">
                                            {Object.entries(data.ablation_daaf_window).map(([k, v]) => (
                                                <div key={k} className="flex items-center justify-between text-xs">
                                                    <span className="text-slate-500 dark:text-gray-400">w={k}</span>
                                                    <div className="flex items-center gap-3">
                                                        <span className="font-mono text-slate-700 dark:text-gray-300">{v.mean_regret.toFixed(1)}±{v.std_regret.toFixed(1)}</span>
                                                        <Badge color={v.mean_f1 >= 0.9 ? "green" : "amber"}>F1: {v.mean_f1.toFixed(3)}</Badge>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {data.ablation_rabi_temperature && (
                                    <div>
                                        <h3 className="text-sm font-semibold text-slate-700 dark:text-gray-300 mb-2">RABI Temperature</h3>
                                        <div className="space-y-1">
                                            {Object.entries(data.ablation_rabi_temperature).map(([k, v]) => (
                                                <div key={k} className="flex items-center justify-between text-xs">
                                                    <span className="text-slate-500 dark:text-gray-400">τ={k}</span>
                                                    <div className="flex items-center gap-3">
                                                        <span className="font-mono text-slate-700 dark:text-gray-300">{v.mean_regret.toFixed(1)}±{v.std_regret.toFixed(1)}</span>
                                                        <Badge color={v.mean_f1 >= 0.9 ? "green" : "amber"}>F1: {v.mean_f1.toFixed(3)}</Badge>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {data.ablation_similarity_threshold && (
                                    <div>
                                        <h3 className="text-sm font-semibold text-slate-700 dark:text-gray-300 mb-2">RABI Similarity Threshold</h3>
                                        <div className="space-y-1">
                                            {Object.entries(data.ablation_similarity_threshold).map(([k, v]) => (
                                                <div key={k} className="flex items-center justify-between text-xs">
                                                    <span className="text-slate-500 dark:text-gray-400">θ={k}</span>
                                                    <div className="flex items-center gap-3">
                                                        <span className="font-mono text-slate-700 dark:text-gray-300">{v.mean_regret.toFixed(1)}±{v.std_regret.toFixed(1)}</span>
                                                        <Badge color={v.mean_f1 >= 0.85 ? "green" : "amber"}>F1: {v.mean_f1.toFixed(3)}</Badge>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </>
            ) : null}

            {/* Interactive Comparison */}
            <div className="glass-panel rounded-2xl p-6">
                <div className="flex items-center gap-3 mb-1">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-red-400 to-emerald-500 flex items-center justify-center">
                        <span className="text-white text-sm">⚡</span>
                    </div>
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white">Live: Thompson Sampling vs Adaptive Forgetting</h2>
                </div>
                <p className="text-xs text-slate-500 dark:text-gray-500 mb-4 ml-11">Run a real-time comparison with custom drift parameters</p>

                <div className="flex flex-wrap items-end gap-6 mb-6">
                    <div>
                        <label className="text-xs text-slate-500 dark:text-gray-500 block mb-1 font-medium">Drift Magnitude</label>
                        <div className="flex items-center gap-2">
                            <input
                                type="range" min={0.05} max={0.35} step={0.05} value={driftMag}
                                onChange={(e) => setDriftMag(parseFloat(e.target.value))}
                                className="accent-brand-500 w-32"
                            />
                            <span className="text-sm font-mono font-semibold text-slate-700 dark:text-gray-300 w-10">{driftMag.toFixed(2)}</span>
                        </div>
                    </div>
                    <div>
                        <label className="text-xs text-slate-500 dark:text-gray-500 block mb-1 font-medium">Seeds</label>
                        <div className="flex items-center gap-2">
                            <input
                                type="range" min={5} max={30} step={5} value={seeds}
                                onChange={(e) => setSeeds(parseInt(e.target.value))}
                                className="accent-brand-500 w-32"
                            />
                            <span className="text-sm font-mono font-semibold text-slate-700 dark:text-gray-300 w-6">{seeds}</span>
                        </div>
                    </div>
                    <button
                        onClick={runComparison}
                        disabled={compLoading}
                        className="px-6 py-2.5 glass-button rounded-xl disabled:opacity-50 text-sm font-semibold flex items-center gap-2"
                    >
                        {compLoading ? (
                            <>
                                <div className="w-4 h-4 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                                Running...
                            </>
                        ) : (
                            <>▶ Run Comparison</>
                        )}
                    </button>
                </div>

                {comparison && (
                    <>
                        <div className="grid grid-cols-3 gap-4 mb-6">
                            <div className="bg-slate-50 dark:bg-gray-800/50 rounded-xl p-4 text-center border border-slate-200/60 dark:border-gray-700">
                                <p className="text-xs text-slate-500 dark:text-gray-500 uppercase tracking-wider font-semibold">TS Regret</p>
                                <p className="text-2xl font-black text-emerald-500 mt-1">{comparison.total_ts_regret.toFixed(1)}</p>
                            </div>
                            <div className="bg-slate-50 dark:bg-gray-800/50 rounded-xl p-4 text-center border border-slate-200/60 dark:border-gray-700">
                                <p className="text-xs text-slate-500 dark:text-gray-500 uppercase tracking-wider font-semibold">Adaptive Regret</p>
                                <p className="text-2xl font-black text-red-500 mt-1">{comparison.total_daaf_regret.toFixed(1)}</p>
                            </div>
                            <div className="bg-slate-50 dark:bg-gray-800/50 rounded-xl p-4 text-center border border-slate-200/60 dark:border-gray-700">
                                <p className="text-xs text-slate-500 dark:text-gray-500 uppercase tracking-wider font-semibold">DAAF Improvement</p>
                                <p className={`text-2xl font-black mt-1 ${comparison.improvement_pct > 0 ? "text-blue-500" : "text-amber-500"}`}>
                                    {comparison.improvement_pct > 0 ? "+" : ""}{comparison.improvement_pct.toFixed(1)}%
                                </p>
                            </div>
                        </div>

                        <ResponsiveContainer width="100%" height={380}>
                            <LineChart data={chartData.filter((_, i) => i % 5 === 0)}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                                <XAxis dataKey="round" stroke="#94a3b8" tick={{ fontSize: 11 }} label={{ value: "Round", position: "insideBottom", offset: -5 }} />
                                <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} label={{ value: "Cumulative Regret", angle: -90, position: "insideLeft" }} />
                                <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "8px", fontSize: "12px" }} />
                                <Legend />
                                <Line type="monotone" dataKey="TS (no forgetting)" stroke="#10b981" strokeWidth={2.5} dot={false} />
                                <Line type="monotone" dataKey="Adaptive Forgetting" stroke="#ef4444" strokeWidth={2.5} dot={false} />
                            </LineChart>
                        </ResponsiveContainer>
                    </>
                )}
            </div>
        </div>
    );
}

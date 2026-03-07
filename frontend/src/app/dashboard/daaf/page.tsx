"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import {
    LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
    Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";

interface DAAFResult {
    rewards: number[];
    recent_means: number[];
    drift_magnitudes: number[];
    gammas: number[];
    drift_types: string[];
    detection_delay: number | null;
    peak_gamma: number;
}

export default function DAAFPage() {
    const [result, setResult] = useState<DAAFResult | null>(null);
    const [loading, setLoading] = useState(false);

    // Production parameters from jobs/forgetting.py + drift_forgetting.py
    const windowSize = 50;           // Detection window size
    const baseDecayRate = 0.05;      // Base forgetting rate
    const threshold = 0.4;           // Drift threshold
    const driftRound = 150;          // Demo: when to trigger drift
    const postMean = 0.55;           // Quality after drift (fixed)
    const [preMean, setPreMean] = useState(0.85);

    const [error, setError] = useState("");

    const run = async () => {
        setLoading(true);
        setError("");
        try {
            const res = (await api.runDAAFDemo({
                pre_drift_mean: preMean,
                post_drift_mean: 0.55,        // Fixed: quality after drift
                noise_std: 0.06,              // Fixed: inherent noise
                drift_round: driftRound,
                window_size: windowSize,
                n_rounds: 300,
            })) as DAAFResult;
            setResult(res);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to run DAAF demo");
        }
        setLoading(false);
    };

    // Chart data — sample every 2 rounds for performance
    const rewardData = result
        ? result.rewards.map((r, i) => ({
            round: i,
            reward: Math.round(r * 1000) / 1000,
            mean: Math.round(result.recent_means[i] * 1000) / 1000,
        })).filter((_, i) => i % 2 === 0)
        : [];

    const driftData = result
        ? result.drift_magnitudes.map((d, i) => ({
            round: i,
            delta: Math.round(d * 1000) / 1000,
            gamma: Math.round(result.gammas[i] * 10000) / 10000,
        })).filter((_, i) => i % 2 === 0)
        : [];

    const typeMap: Record<string, number> = { none: 0, gradual: 1, abrupt: 2 };
    const typeColorMap: Record<string, string> = { none: "#22c55e", gradual: "#f59e0b", abrupt: "#ef4444" };
    const typeData = result
        ? result.drift_types.map((t, i) => ({
            round: i,
            type: typeMap[t] ?? 0,
            fill: typeColorMap[t] ?? "#22c55e",
        }))
        : [];

    return (
        <div className="max-w-7xl 3xl:max-w-[1800px] mx-auto space-y-6">
            {/* Header */}
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6 animate-fade-in-up">
                <div className="absolute inset-0 bg-gradient-to-r from-amber-500/5 to-orange-500/5 dark:from-amber-500/[0.03] dark:to-orange-500/[0.03]" />
                <div className="relative">
                    <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-lg shadow-amber-500/20">
                            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                            </svg>
                        </div>
                        Drift Detection
                        <span className="ml-2 px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-200/60 dark:border-amber-500/20">Simulated</span>
                    </h1>
                    <p className="text-slate-500 dark:text-gray-400 mt-1.5 text-sm">
                        Monitors changes in document quality over time and automatically adjusts learning speed to adapt
                    </p>
                </div>
            </div>

            {error && (
                <div className="glass-panel rounded-2xl p-4 text-sm text-red-700 dark:text-red-400 border-red-200 dark:border-red-800">
                    {error}
                </div>
            )}

            {/* Concept */}
            <div className="glass-panel rounded-2xl p-6 animate-fade-in-up" style={{ animationDelay: '60ms' }}>
                <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-3">Why Drift Detection Matters</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-slate-600 dark:text-gray-300">
                    <div className="space-y-2">
                        <p>
                            When a vendor changes their document template, the best extraction strategy shifts.
                            Without drift detection, the system clings to outdated knowledge — taking hundreds of rounds to catch up.
                        </p>
                        <p className="text-xs text-slate-500 dark:text-gray-500">
                            This module automatically detects when quality drops and speeds up re-learning.
                        </p>
                    </div>
                    <div className="bg-slate-50/80 dark:bg-gray-800/60 backdrop-blur-sm rounded-xl p-4 font-mono text-xs text-slate-700 dark:text-gray-200 border border-slate-200/60 dark:border-white/[0.06]">
                        <p className="text-slate-500 dark:text-gray-400 mb-2 font-sans text-[10px] uppercase tracking-wider font-semibold">Core Formulas</p>
                        <p>Drift Δ = |mean(recent) - mean(older)|</p>
                        <p>γ* = √(Δ² / ln(t))</p>
                        <p>α_new = 1 + (1-γ)(α - 1)</p>
                        <p className="text-brand-400 mt-2">Key: measures actual shift, not noise</p>
                    </div>
                </div>
            </div>

            {/* Controls */}
            <div className="glass-panel rounded-2xl p-6 animate-fade-in-up" style={{ animationDelay: '120ms' }}>
                <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Configuration</h2>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6 stagger-children">
                    <div className="glass-stat p-4">
                        <div className="relative z-10">
                            <div className="flex items-center gap-2 mb-2">
                                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-50 to-cyan-50 dark:from-brand-500/10 dark:to-cyan-500/10 border border-brand-100/60 dark:border-brand-500/15 flex items-center justify-center">
                                    <span className="text-xs">🪟</span>
                                </div>
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Detection Window</p>
                            </div>
                            <p className="text-2xl font-extrabold text-slate-900 dark:text-white">{windowSize}</p>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">How many recent documents to compare against older ones</p>
                        </div>
                    </div>
                    <div className="glass-stat p-4">
                        <div className="relative z-10">
                            <div className="flex items-center gap-2 mb-2">
                                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-50 to-cyan-50 dark:from-brand-500/10 dark:to-cyan-500/10 border border-brand-100/60 dark:border-brand-500/15 flex items-center justify-center">
                                    <span className="text-xs">📉</span>
                                </div>
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Base Decay Rate</p>
                            </div>
                            <p className="text-2xl font-extrabold text-slate-900 dark:text-white">{baseDecayRate}</p>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Normal forgetting speed when no drift is detected (5% per cycle)</p>
                        </div>
                    </div>
                    <div className="glass-stat p-4">
                        <div className="relative z-10">
                            <div className="flex items-center gap-2 mb-2">
                                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-50 to-cyan-50 dark:from-brand-500/10 dark:to-cyan-500/10 border border-brand-100/60 dark:border-brand-500/15 flex items-center justify-center">
                                    <span className="text-xs">🎚️</span>
                                </div>
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Drift Threshold</p>
                            </div>
                            <p className="text-2xl font-extrabold text-slate-900 dark:text-white">{threshold}</p>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Minimum quality change needed to trigger drift detection</p>
                        </div>
                    </div>
                    <div className="glass-stat p-4">
                        <div className="relative z-10">
                            <div className="flex items-center gap-2 mb-2">
                                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-50 to-cyan-50 dark:from-brand-500/10 dark:to-cyan-500/10 border border-brand-100/60 dark:border-brand-500/15 flex items-center justify-center">
                                    <span className="text-xs">⏱️</span>
                                </div>
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Drift Round</p>
                            </div>
                            <p className="text-2xl font-extrabold text-slate-900 dark:text-white">{driftRound}</p>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Demo only: simulated round when the environment changes</p>
                        </div>
                    </div>
                </div>
                <div className="space-y-3 mb-5">
                    <div className="flex items-center justify-between">
                        <label className="text-xs font-medium text-slate-600 dark:text-gray-400">Pre-drift quality level</label>
                        <span className="text-sm font-mono font-bold text-brand-500">{preMean.toFixed(2)}</span>
                    </div>
                    <input type="range" min={0.3} max={0.95} step={0.05} value={preMean}
                        onChange={(e) => setPreMean(parseFloat(e.target.value))} className="w-full accent-brand-500" />
                    <p className="text-[11px] text-slate-500 dark:text-gray-500">Slide to set how good the extraction quality is before the simulated drift event</p>
                </div>
                <button onClick={run} disabled={loading}
                    className="glass-button px-6 py-3 rounded-xl text-sm flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] transition-all duration-200">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {loading ? "Running Simulation..." : "Run Drift Detection"}
                </button>
            </div>

            {result && (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 stagger-children">
                        <div className="glass-stat p-5">
                            <div className="relative z-10 text-center">
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider mb-1">True Drift Magnitude</p>
                                <p className="text-2xl font-extrabold text-slate-900 dark:text-white">{Math.abs(preMean - postMean).toFixed(3)}</p>
                                <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Actual quality drop between pre/post drift</p>
                            </div>
                        </div>
                        <div className="glass-stat p-5">
                            <div className="relative z-10 text-center">
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider mb-1">Detection Delay</p>
                                <p className="text-2xl font-extrabold text-amber-500 dark:text-amber-400">
                                    {result.detection_delay !== null ? `${result.detection_delay} rounds` : "Not detected"}
                                </p>
                                <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Rounds until the system noticed the change</p>
                            </div>
                        </div>
                        <div className="glass-stat p-5">
                            <div className="relative z-10 text-center">
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider mb-1">Peak Forgetting Rate</p>
                                <p className="text-2xl font-extrabold text-violet-500 dark:text-violet-400">{result.peak_gamma.toFixed(4)}</p>
                                <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Maximum speed the system forgot old beliefs</p>
                            </div>
                        </div>
                    </div>

                    {/* Charts */}
                    <div className="space-y-6">
                        {/* Reward Stream */}
                        <div className="glass-panel rounded-2xl p-6">
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Reward Stream</h3>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-3">Extraction quality score over time — the red line shows the moving average</p>
                            <ResponsiveContainer width="100%" height={250}>
                                <LineChart data={rewardData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="round" stroke="#6b7280" tick={{ fontSize: 10 }} />
                                    <YAxis stroke="#6b7280" tick={{ fontSize: 10 }} domain={[0, 1]} />
                                    <Tooltip contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }} />
                                    <Legend />
                                    <ReferenceLine x={driftRound} stroke="#ef4444" strokeDasharray="5 5" label="Drift" />
                                    <Line type="monotone" dataKey="reward" stroke="#3b82f6" strokeWidth={1} dot={false} opacity={0.4} />
                                    <Line type="monotone" dataKey="mean" stroke="#ef4444" strokeWidth={2} dot={false} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>

                        {/* Drift Magnitude & Gamma */}
                        <div className="grid grid-cols-2 gap-6">
                            <div className="glass-panel rounded-2xl p-6">
                                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Drift Magnitude (Δ)</h3>
                                <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-3">How much recent quality differs from earlier — spikes indicate drift</p>
                                <ResponsiveContainer width="100%" height={200}>
                                    <LineChart data={driftData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                        <XAxis dataKey="round" stroke="#6b7280" tick={{ fontSize: 10 }} />
                                        <YAxis stroke="#6b7280" tick={{ fontSize: 10 }} />
                                        <Tooltip contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }} />
                                        <ReferenceLine x={driftRound} stroke="#ef4444" strokeDasharray="5 5" />
                                        <ReferenceLine y={0.05} stroke="#f59e0b" strokeDasharray="3 3" label="Gradual" />
                                        <ReferenceLine y={0.15} stroke="#ef4444" strokeDasharray="3 3" label="Abrupt" />
                                        <Line type="monotone" dataKey="delta" stroke="#ef4444" strokeWidth={2} dot={false} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>

                            <div className="glass-panel rounded-2xl p-6">
                                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Forgetting Rate (γ*)</h3>
                                <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-3">How fast the system discards old knowledge — higher means faster adaptation</p>
                                <ResponsiveContainer width="100%" height={200}>
                                    <LineChart data={driftData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                        <XAxis dataKey="round" stroke="#6b7280" tick={{ fontSize: 10 }} />
                                        <YAxis stroke="#6b7280" tick={{ fontSize: 10 }} />
                                        <Tooltip contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }} />
                                        <ReferenceLine x={driftRound} stroke="#ef4444" strokeDasharray="5 5" />
                                        <Line type="monotone" dataKey="gamma" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>

                    {/* Noise vs Drift explainer */}
                    <div className="glass-panel rounded-2xl p-6">
                        <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Why Noise ≠ Drift</h3>
                        <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-4">The system distinguishes random quality fluctuations from real environment changes</p>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 stagger-children">
                            <div className="bg-emerald-50/50 dark:bg-emerald-500/5 backdrop-blur-sm rounded-xl p-4 border border-emerald-200/40 dark:border-emerald-500/10">
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                                    <p className="text-emerald-600 dark:text-emerald-400 font-semibold text-xs">Noisy but stable</p>
                                </div>
                                <p className="text-xs text-slate-600 dark:text-gray-400">Quality varies a lot, but the average stays the same — system stays calm, no unnecessary forgetting</p>
                            </div>
                            <div className="bg-amber-50/50 dark:bg-amber-500/5 backdrop-blur-sm rounded-xl p-4 border border-amber-200/40 dark:border-amber-500/10">
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="w-2 h-2 rounded-full bg-amber-500" />
                                    <p className="text-amber-600 dark:text-amber-400 font-semibold text-xs">Clean drift</p>
                                </div>
                                <p className="text-xs text-slate-600 dark:text-gray-400">Low noise but the average shifts — system quickly detects the change and speeds up learning</p>
                            </div>
                            <div className="bg-red-50/50 dark:bg-red-500/5 backdrop-blur-sm rounded-xl p-4 border border-red-200/40 dark:border-red-500/10">
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="w-2 h-2 rounded-full bg-red-500" />
                                    <p className="text-red-600 dark:text-red-400 font-semibold text-xs">Noisy + drifting</p>
                                </div>
                                <p className="text-xs text-slate-600 dark:text-gray-400">Both noise and drift are high — system responds to the real shift, not the noise</p>
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}

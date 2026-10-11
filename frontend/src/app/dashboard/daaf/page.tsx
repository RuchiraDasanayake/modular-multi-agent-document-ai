"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Icon, type IconName } from "@/components/icons";
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
    Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";

const GRID_STROKE = "rgba(148, 163, 184, 0.3)";
const TOOLTIP_STYLE = {
    background: "rgba(255, 255, 255, 0.97)",
    border: "1px solid #e2e8f0",
    borderRadius: "8px",
    color: "#0f172a",
    fontSize: "12px",
};

function SettingTile({ icon, label, value, hint }: { icon: IconName; label: string; value: number; hint: string }) {
    return (
        <div className="glass-stat p-4">
            <div className="relative z-10">
                <div className="flex items-center gap-2 mb-2">
                    <span className="w-7 h-7 rounded-lg bg-brand-50 dark:bg-brand-500/10 border border-brand-100/60 dark:border-brand-500/15 flex items-center justify-center text-brand-700 dark:text-brand-300">
                        <Icon name={icon} className="h-3.5 w-3.5" />
                    </span>
                    <p className="text-xs text-slate-600 dark:text-gray-300 font-semibold">{label}</p>
                </div>
                <p className="text-2xl font-extrabold text-slate-900 dark:text-white tabular-nums">{value}</p>
                <p className="text-xs text-slate-500 dark:text-gray-400 mt-1">{hint}</p>
            </div>
        </div>
    );
}

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

    return (
        <div className="max-w-7xl 3xl:max-w-[1800px] mx-auto space-y-6">
            {/* Header */}
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6 animate-fade-in-up">
                <div className="absolute inset-0 bg-gradient-to-r from-amber-500/5 to-orange-500/5 dark:from-amber-500/[0.03] dark:to-orange-500/[0.03]" />
                <div className="relative">
                    <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex flex-wrap items-center gap-3">
                        <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-lg shadow-amber-500/20 text-white">
                            <Icon name="bolt" className="h-5 w-5" />
                        </span>
                        Drift detection (DAAF)
                        <span className="px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-200/60 dark:border-amber-500/20">Simulated</span>
                    </h1>
                    <p className="text-slate-600 dark:text-gray-300 mt-1.5 text-sm max-w-3xl">
                        Watches a stream of rewards for a lasting change in the average and, when it finds one, makes the
                        bandit forget old evidence faster.
                    </p>
                    <p className="text-slate-500 dark:text-gray-400 mt-1 text-xs">
                        This page runs DAAF in the simulator. The document pipeline and the benchmark do not use it; only
                        the separate AHMN service does, when it records an outcome and in a six-hourly clean-up of stale
                        stored policies.
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
                <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-3">Why drift matters</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-slate-600 dark:text-gray-300">
                    <div className="space-y-2">
                        <p>
                            If a vendor changes its document template, the best extraction policy can change too. A bandit
                            that never forgets keeps trusting evidence from before the change and is slow to switch.
                        </p>
                        <p className="text-xs text-slate-500 dark:text-gray-400">
                            DAAF compares recent rewards with older ones and raises the forgetting rate only when the
                            average moves.
                        </p>
                    </div>
                    <div className="bg-slate-50/80 dark:bg-gray-800/60 rounded-xl p-4 font-mono text-xs text-slate-700 dark:text-gray-200 border border-slate-200/60 dark:border-white/[0.06]">
                        <p className="text-slate-500 dark:text-gray-400 mb-2 font-sans text-xs font-semibold">Formulas</p>
                        <p>Drift Δ = |mean(recent) − mean(older)|</p>
                        <p>γ* = √(Δ² / ln(t))</p>
                        <p>α_new = 1 + (1 − γ)(α − 1)</p>
                        <p className="text-slate-600 dark:text-gray-300 mt-2 font-sans">Δ measures a shift in the average, not single noisy rewards.</p>
                    </div>
                </div>
            </div>

            {/* Controls */}
            <div className="glass-panel rounded-2xl p-6 animate-fade-in-up" style={{ animationDelay: '120ms' }}>
                <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Settings</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
                    <SettingTile icon="window" label="Detection window" value={windowSize} hint="Recent rewards compared with older ones" />
                    <SettingTile icon="trendDown" label="Base forgetting rate" value={baseDecayRate} hint="Forgetting per round when no drift is found" />
                    <SettingTile icon="sliders" label="Drift threshold" value={threshold} hint="Smallest change in the average that counts as drift" />
                    <SettingTile icon="clock" label="Drift round" value={driftRound} hint="Round at which the simulation changes the reward average" />
                </div>
                <div className="space-y-2 mb-5">
                    <div className="flex items-center justify-between">
                        <label htmlFor="daaf-pre-mean" className="text-xs font-semibold text-slate-700 dark:text-gray-200">
                            Average reward before the drift
                        </label>
                        <span className="text-sm font-mono font-bold text-brand-700 dark:text-brand-300">{preMean.toFixed(2)}</span>
                    </div>
                    <input id="daaf-pre-mean" type="range" min={0.3} max={0.95} step={0.05} value={preMean}
                        onChange={(e) => setPreMean(parseFloat(e.target.value))} className="w-full accent-brand-500" />
                    <p className="text-xs text-slate-500 dark:text-gray-400">After the drift the average falls to {postMean.toFixed(2)}.</p>
                </div>
                <button onClick={run} disabled={loading}
                    className="glass-button px-6 py-3 rounded-xl text-sm flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] transition-all duration-200">
                    <Icon name="play" className="h-4 w-4" />
                    {loading ? "Running…" : "Run simulation"}
                </button>
            </div>

            {result && (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="glass-stat p-5">
                            <div className="relative z-10 text-center">
                                <p className="text-xs text-slate-600 dark:text-gray-300 font-semibold mb-1">Size of the drift</p>
                                <p className="text-2xl font-extrabold text-slate-900 dark:text-white tabular-nums">{Math.abs(preMean - postMean).toFixed(3)}</p>
                                <p className="text-xs text-slate-500 dark:text-gray-400 mt-1">Fall in the reward average set for this run</p>
                            </div>
                        </div>
                        <div className="glass-stat p-5">
                            <div className="relative z-10 text-center">
                                <p className="text-xs text-slate-600 dark:text-gray-300 font-semibold mb-1">Detection delay</p>
                                <p className="text-2xl font-extrabold text-amber-700 dark:text-amber-400 tabular-nums">
                                    {result.detection_delay !== null ? `${result.detection_delay} rounds` : "Not detected"}
                                </p>
                                <p className="text-xs text-slate-500 dark:text-gray-400 mt-1">Rounds between the drift and its detection</p>
                            </div>
                        </div>
                        <div className="glass-stat p-5">
                            <div className="relative z-10 text-center">
                                <p className="text-xs text-slate-600 dark:text-gray-300 font-semibold mb-1">Peak forgetting rate (γ*)</p>
                                <p className="text-2xl font-extrabold text-violet-700 dark:text-violet-400 tabular-nums">{result.peak_gamma.toFixed(4)}</p>
                                <p className="text-xs text-slate-500 dark:text-gray-400 mt-1">Highest forgetting rate during the run</p>
                            </div>
                        </div>
                    </div>

                    <div className="space-y-6">
                        <div className="glass-panel rounded-2xl p-6">
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Rewards</h3>
                            <p className="text-xs text-slate-500 dark:text-gray-400 mb-3">Simulated reward per round, with the moving average. The dashed line marks the drift.</p>
                            <ResponsiveContainer width="100%" height={250}>
                                <LineChart data={rewardData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                                    <XAxis dataKey="round" stroke="#94a3b8" tick={{ fontSize: 10 }} />
                                    <YAxis stroke="#94a3b8" tick={{ fontSize: 10 }} domain={[0, 1]} />
                                    <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(round) => `Round ${round}`} />
                                    <Legend />
                                    <ReferenceLine x={driftRound} stroke="#ef4444" strokeDasharray="5 5" label="Drift" />
                                    <Line type="monotone" dataKey="reward" name="Reward" stroke="#3b82f6" strokeWidth={1} dot={false} opacity={0.4} />
                                    <Line type="monotone" dataKey="mean" name="Moving average" stroke="#ef4444" strokeWidth={2} dot={false} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            <div className="glass-panel rounded-2xl p-6">
                                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Drift size (Δ)</h3>
                                <p className="text-xs text-slate-500 dark:text-gray-400 mb-3">Difference between recent and older rewards. A spike means drift.</p>
                                <ResponsiveContainer width="100%" height={200}>
                                    <LineChart data={driftData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                                        <XAxis dataKey="round" stroke="#94a3b8" tick={{ fontSize: 10 }} />
                                        <YAxis stroke="#94a3b8" tick={{ fontSize: 10 }} />
                                        <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(round) => `Round ${round}`} />
                                        <ReferenceLine x={driftRound} stroke="#ef4444" strokeDasharray="5 5" />
                                        <ReferenceLine y={0.05} stroke="#f59e0b" strokeDasharray="3 3" label="Gradual" />
                                        <ReferenceLine y={0.15} stroke="#ef4444" strokeDasharray="3 3" label="Abrupt" />
                                        <Line type="monotone" dataKey="delta" name="Δ" stroke="#ef4444" strokeWidth={2} dot={false} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>

                            <div className="glass-panel rounded-2xl p-6">
                                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Forgetting rate (γ*)</h3>
                                <p className="text-xs text-slate-500 dark:text-gray-400 mb-3">How quickly old evidence is discarded. Higher means faster adaptation.</p>
                                <ResponsiveContainer width="100%" height={200}>
                                    <LineChart data={driftData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                                        <XAxis dataKey="round" stroke="#94a3b8" tick={{ fontSize: 10 }} />
                                        <YAxis stroke="#94a3b8" tick={{ fontSize: 10 }} />
                                        <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(round) => `Round ${round}`} />
                                        <ReferenceLine x={driftRound} stroke="#ef4444" strokeDasharray="5 5" />
                                        <Line type="monotone" dataKey="gamma" name="γ*" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>

                    <div className="glass-panel rounded-2xl p-6">
                        <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Noise is not drift</h3>
                        <p className="text-xs text-slate-500 dark:text-gray-400 mb-4">How DAAF is meant to tell random variation from a real change</p>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            <div className="bg-emerald-50/60 dark:bg-emerald-500/5 rounded-xl p-4 border border-emerald-200/60 dark:border-emerald-500/10">
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                                    <p className="text-emerald-800 dark:text-emerald-400 font-semibold text-xs">Noisy but stable</p>
                                </div>
                                <p className="text-xs text-slate-600 dark:text-gray-400">Rewards vary a lot but the average holds, so there is no extra forgetting.</p>
                            </div>
                            <div className="bg-amber-50/60 dark:bg-amber-500/5 rounded-xl p-4 border border-amber-200/60 dark:border-amber-500/10">
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="w-2 h-2 rounded-full bg-amber-500" />
                                    <p className="text-amber-800 dark:text-amber-400 font-semibold text-xs">Clean drift</p>
                                </div>
                                <p className="text-xs text-slate-600 dark:text-gray-400">Little noise and the average moves, so the change is caught quickly.</p>
                            </div>
                            <div className="bg-red-50/60 dark:bg-red-500/5 rounded-xl p-4 border border-red-200/60 dark:border-red-500/10">
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="w-2 h-2 rounded-full bg-red-500" />
                                    <p className="text-red-800 dark:text-red-400 font-semibold text-xs">Noisy and drifting</p>
                                </div>
                                <p className="text-xs text-slate-600 dark:text-gray-400">Both are high; the forgetting rate should follow the shift, not the noise.</p>
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}

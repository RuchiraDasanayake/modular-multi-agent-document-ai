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

    const [preMean, setPreMean] = useState(0.85);
    const [postMean, setPostMean] = useState(0.55);
    const [noiseStd, setNoiseStd] = useState(0.06);
    const [driftRound, setDriftRound] = useState(150);
    const [windowSize, setWindowSize] = useState(50);

    const [error, setError] = useState("");

    const run = async () => {
        setLoading(true);
        setError("");
        try {
            const res = (await api.runDAAFDemo({
                pre_drift_mean: preMean,
                post_drift_mean: postMean,
                noise_std: noiseStd,
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
        <div className="max-w-6xl 3xl:max-w-7xl mx-auto space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Drift Detection</h1>
                <p className="text-slate-500 dark:text-gray-500 mt-1">
                    Adaptive forgetting — watch real-time drift detection
                </p>
            </div>

            {error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 text-sm text-red-700 dark:text-red-400">
                    {error}
                </div>
            )}

            {/* Concept */}
            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">The Concept Drift Problem</h2>
                <div className="grid grid-cols-2 gap-4 text-sm text-slate-600 dark:text-gray-300">
                    <div>
                        <p>
                            When a vendor changes their document template, the best OCR policy shifts.
                            Standard TS has strong beliefs from old data — takes hundreds of rounds to adapt.
                        </p>
                    </div>
                    <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3 font-mono text-xs text-slate-700 dark:text-gray-200">
                        <p>Drift Δ = |mean(recent) - mean(older)|</p>
                        <p>γ* = √(Δ² / ln(t))</p>
                        <p>α_new = 1 + (1-γ)(α - 1)</p>
                        <p className="text-brand-400 mt-1">Key: use Δ, NOT σ²</p>
                    </div>
                </div>
            </div>

            {/* Controls */}
            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Interactive Controls</h2>
                <div className="grid grid-cols-5 gap-4 mb-4">
                    <div>
                        <label className="text-xs text-slate-500 dark:text-gray-500 block mb-1">Pre-drift mean: {preMean}</label>
                        <input type="range" min={0.3} max={0.95} step={0.05} value={preMean}
                            onChange={(e) => setPreMean(parseFloat(e.target.value))} className="w-full accent-brand-500" />
                    </div>
                    <div>
                        <label className="text-xs text-slate-500 dark:text-gray-500 block mb-1">Post-drift mean: {postMean}</label>
                        <input type="range" min={0.3} max={0.95} step={0.05} value={postMean}
                            onChange={(e) => setPostMean(parseFloat(e.target.value))} className="w-full accent-brand-500" />
                    </div>
                    <div>
                        <label className="text-xs text-slate-500 dark:text-gray-500 block mb-1">Noise σ: {noiseStd}</label>
                        <input type="range" min={0.01} max={0.2} step={0.01} value={noiseStd}
                            onChange={(e) => setNoiseStd(parseFloat(e.target.value))} className="w-full accent-brand-500" />
                    </div>
                    <div>
                        <label className="text-xs text-slate-500 dark:text-gray-500 block mb-1">Drift at round: {driftRound}</label>
                        <input type="range" min={50} max={250} step={10} value={driftRound}
                            onChange={(e) => setDriftRound(parseInt(e.target.value))} className="w-full accent-brand-500" />
                    </div>
                    <div>
                        <label className="text-xs text-slate-500 dark:text-gray-500 block mb-1">Window: {windowSize}</label>
                        <input type="range" min={10} max={100} step={5} value={windowSize}
                            onChange={(e) => setWindowSize(parseInt(e.target.value))} className="w-full accent-brand-500" />
                    </div>
                </div>
                <button onClick={run} disabled={loading}
                    className="px-5 py-2.5 bg-brand-600 hover:bg-brand-500 disabled:bg-slate-200 dark:bg-gray-700 rounded-lg text-sm text-slate-900 dark:text-white transition-colors">
                    {loading ? "Running..." : "▶ Run Drift Detection"}
                </button>
            </div>

            {result && (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-3 gap-4">
                        <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500">True Drift Magnitude</p>
                            <p className="text-xl font-bold text-slate-900 dark:text-white">{Math.abs(preMean - postMean).toFixed(3)}</p>
                        </div>
                        <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500">Detection Delay</p>
                            <p className="text-xl font-bold text-yellow-400">
                                {result.detection_delay !== null ? `${result.detection_delay} rounds` : "Not detected"}
                            </p>
                        </div>
                        <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500">Peak γ*</p>
                            <p className="text-xl font-bold text-violet-400">{result.peak_gamma.toFixed(4)}</p>
                        </div>
                    </div>

                    {/* Charts */}
                    <div className="space-y-6">
                        {/* Reward Stream */}
                        <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-3">Reward Stream</h3>
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
                            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                                <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-3">Drift Magnitude (Δ)</h3>
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

                            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                                <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-3">Forgetting Rate (γ*)</h3>
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
                    <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-3">Why Noise ≠ Drift</h3>
                        <div className="grid grid-cols-3 gap-4 text-xs text-slate-500 dark:text-gray-400">
                            <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3">
                                <p className="text-emerald-400 font-medium mb-1">High noise + no drift</p>
                                <p>σ² high, Δ ≈ 0 → γ* stays small → no unnecessary forgetting</p>
                            </div>
                            <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3">
                                <p className="text-yellow-400 font-medium mb-1">Low noise + drift</p>
                                <p>σ² low, Δ high → γ* increases → fast adaptation</p>
                            </div>
                            <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3">
                                <p className="text-red-400 font-medium mb-1">High noise + drift</p>
                                <p>σ² high, Δ high → γ* scales with Δ not σ² → correct response</p>
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}

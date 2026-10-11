"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Icon } from "@/components/icons";
import {
    LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
    Legend, ResponsiveContainer,
} from "recharts";

interface RABIResult {
    prior: { alpha: number; beta: number; mean: number; confidence: number; n_neighbors: number };
    neighbors: { hash: string; similarity: number; alpha: number; beta: number; mean: number }[];
    weights: number[];
    distribution: { x: number[]; flat_pdf: number[]; rabi_pdf: number[] };
}

export default function RABIPage() {
    const [result, setResult] = useState<RABIResult | null>(null);
    const [loading, setLoading] = useState(false);
    // Production parameters from main.py
    const temperature = 0.5;  // Softmax scaling for neighbor weights
    const threshold = 0.4;    // Min cosine similarity to accept neighbor
    const k = 5;              // Number of neighbors to retrieve

    const [error, setError] = useState("");

    const run = async () => {
        setLoading(true);
        setError("");
        try {
            const res = (await api.runRABIDemo({ temperature, threshold, k })) as RABIResult;
            setResult(res);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to run RABI demo");
        }
        setLoading(false);
    };

    // Distribution chart data
    const distData = result
        ? result.distribution.x
            .filter((_, i) => i % 4 === 0)
            .map((x, i) => ({
                x: x.toFixed(2),
                "Flat Prior Beta(1,1)": result.distribution.flat_pdf[i * 4]?.toFixed(3) || 0,
                "Smart Prior": result.distribution.rabi_pdf[i * 4]?.toFixed(3) || 0,
            }))
        : [];

    // Weights chart
    const weightsData = result
        ? result.neighbors.map((n, i) => ({
            neighbor: n.hash,
            similarity: n.similarity,
            weight: result.weights[i],
            mean: n.mean,
        }))
        : [];

    return (
        <div className="max-w-7xl 3xl:max-w-[1800px] mx-auto space-y-6">
            {/* Header */}
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6 animate-fade-in-up">
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/5 to-brand-500/5 dark:from-cyan-500/[0.03] dark:to-brand-500/[0.03]" />
                <div className="relative">
                    <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex flex-wrap items-center gap-3">
                        <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-brand-500 flex items-center justify-center shadow-lg shadow-cyan-500/20 text-white">
                            <Icon name="seedling" className="h-5 w-5" />
                        </span>
                        Cold start (RABI)
                        <span className="px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-200/60 dark:border-amber-500/20">Simulated</span>
                    </h1>
                    <p className="text-slate-600 dark:text-gray-300 mt-1.5 max-w-3xl text-sm">
                        When a new vendor appears, RABI builds its starting belief about a policy from similar vendors it
                        has already seen, instead of starting from a flat prior.
                    </p>
                    <p className="text-slate-500 dark:text-gray-400 mt-1 text-xs">
                        This page runs RABI in the simulator. The document pipeline and the benchmark do not use it; only
                        the separate AHMN service (see Policy check) uses it for cold starts.
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
                <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-3">Why cold start matters</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="rounded-xl p-4 border border-slate-200 bg-slate-50/60 dark:border-gray-700 dark:bg-gray-800/40">
                        <div className="flex items-center gap-2 mb-2">
                            <span className="w-2 h-2 rounded-full bg-slate-400" />
                            <p className="font-semibold text-slate-700 dark:text-gray-200 text-xs">Flat prior</p>
                        </div>
                        <p className="text-sm text-slate-600 dark:text-gray-300">A new vendor starts with no knowledge, so the router has to find a good policy by trial and error.</p>
                    </div>
                    <div className="rounded-xl p-4 border border-cyan-200 bg-cyan-50/60 dark:border-cyan-500/20 dark:bg-cyan-500/5">
                        <div className="flex items-center gap-2 mb-2">
                            <span className="w-2 h-2 rounded-full bg-cyan-500" />
                            <p className="font-semibold text-cyan-800 dark:text-cyan-300 text-xs">Borrowed prior</p>
                        </div>
                        <p className="text-sm text-slate-600 dark:text-gray-300">A new vendor starts from the outcomes of the most similar known vendors, weighted by similarity.</p>
                    </div>
                </div>
            </div>

            {/* Production Config */}
            <div className="glass-panel rounded-2xl p-6 animate-fade-in-up" style={{ animationDelay: '120ms' }}>
                <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Configuration</h2>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6 stagger-children">
                    <div className="glass-stat p-4">
                        <div className="relative z-10">
                            <p className="mb-2 text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Temperature (τ)</p>
                            <p className="text-2xl font-extrabold text-slate-900 dark:text-white">{temperature}</p>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Lower values give the most similar neighbour more weight</p>
                        </div>
                    </div>
                    <div className="glass-stat p-4">
                        <div className="relative z-10">
                            <p className="mb-2 text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Minimum similarity</p>
                            <p className="text-2xl font-extrabold text-slate-900 dark:text-white">{threshold}</p>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Known vendors below this cosine similarity are ignored</p>
                        </div>
                    </div>
                    <div className="glass-stat p-4">
                        <div className="relative z-10">
                            <p className="mb-2 text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Neighbours (k)</p>
                            <p className="text-2xl font-extrabold text-slate-900 dark:text-white">{k}</p>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Number of most-similar known document types to learn from</p>
                        </div>
                    </div>
                </div>
                <button
                    onClick={run}
                    disabled={loading}
                    className="glass-button px-6 py-3 rounded-xl text-sm flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] transition-all duration-200"
                >
                    <Icon name="play" />
                    {loading ? "Computing..." : "Run simulation"}
                </button>
            </div>

            {result && (
                <>
                    {/* Prior Result */}
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 stagger-children">
                        <div className="glass-stat p-5">
                            <div className="relative z-10 text-center">
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider mb-1">Prior α</p>
                                <p className="text-2xl font-extrabold text-cyan-500 dark:text-cyan-400">{result.prior.alpha.toFixed(2)}</p>
                                <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Strength of belief that the policy works well</p>
                            </div>
                        </div>
                        <div className="glass-stat p-5">
                            <div className="relative z-10 text-center">
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider mb-1">Prior β</p>
                                <p className="text-2xl font-extrabold text-cyan-500 dark:text-cyan-400">{result.prior.beta.toFixed(2)}</p>
                                <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Strength of belief that the policy does not work</p>
                            </div>
                        </div>
                        <div className="glass-stat p-5">
                            <div className="relative z-10 text-center">
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider mb-1">Expected Reward</p>
                                <p className="text-2xl font-extrabold text-slate-900 dark:text-white">{result.prior.mean.toFixed(3)}</p>
                                <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">Predicted extraction quality (α / (α+β))</p>
                            </div>
                        </div>
                        <div className="glass-stat p-5">
                            <div className="relative z-10 text-center">
                                <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider mb-1">Confidence</p>
                                <p className="text-2xl font-extrabold text-emerald-500 dark:text-emerald-400">{(result.prior.confidence * 100).toFixed(1)}%</p>
                                <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-1">How certain the system is about this prediction</p>
                            </div>
                        </div>
                    </div>

                    {/* Charts */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Distribution */}
                        <div className="glass-panel rounded-2xl p-6">
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Prior Distribution</h3>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-3">Compares the smart prior (from neighbors) vs. a flat uninformed prior</p>
                            <ResponsiveContainer width="100%" height={300}>
                                <LineChart data={distData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="x" stroke="#6b7280" tick={{ fontSize: 10 }} />
                                    <YAxis stroke="#6b7280" tick={{ fontSize: 10 }} />
                                    <Tooltip contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }} />
                                    <Legend />
                                    <Line type="monotone" dataKey="Flat Prior Beta(1,1)" stroke="#6b7280" strokeDasharray="5 5" dot={false} />
                                    <Line type="monotone" dataKey="Smart Prior" stroke="#06b6d4" strokeWidth={2} dot={false} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>

                        {/* Weights */}
                        <div className="glass-panel rounded-2xl p-6">
                            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Neighbor Weights</h3>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-3">How much each similar document type contributes to the smart prior</p>
                            <ResponsiveContainer width="100%" height={300}>
                                <BarChart data={weightsData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                    <XAxis dataKey="neighbor" stroke="#6b7280" tick={{ fontSize: 10 }} />
                                    <YAxis stroke="#6b7280" tick={{ fontSize: 10 }} />
                                    <Tooltip contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }} />
                                    <Bar dataKey="weight" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                                    <Bar dataKey="similarity" fill="#6366f1" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}

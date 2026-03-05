"use client";

import { useState } from "react";
import { api } from "@/lib/api";
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
    const [temperature, setTemperature] = useState(0.5);
    const [threshold, setThreshold] = useState(0.3);
    const [k, setK] = useState(5);

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
        <div className="max-w-6xl 3xl:max-w-7xl mx-auto space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Cold-Start Solution</h1>
                <p className="text-slate-500 dark:text-gray-500 mt-1">
                    Smart initialization — transfer knowledge from similar contexts
                </p>
            </div>

            {error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 text-sm text-red-700 dark:text-red-400">
                    {error}
                </div>
            )}

            {/* Concept */}
            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">The Cold-Start Problem</h2>
                <div className="grid grid-cols-2 gap-4 text-sm text-slate-600 dark:text-gray-300">
                    <div>
                        <p className="font-medium text-red-400 mb-1">Without Smart Prior</p>
                        <p>New vendor → flat prior Beta(1,1) → needs ~50 rounds of random exploration to learn.</p>
                    </div>
                    <div>
                        <p className="font-medium text-cyan-400 mb-1">With Smart Prior</p>
                        <p>New vendor → find similar vendors → transfer their learned priors → near-optimal from round 1.</p>
                    </div>
                </div>
            </div>

            {/* Controls */}
            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Interactive Parameters</h2>
                <div className="grid grid-cols-3 gap-6 mb-4">
                    <div>
                        <label className="text-xs text-slate-500 dark:text-gray-500 block mb-1">
                            Temperature (τ) = {temperature.toFixed(2)}
                        </label>
                        <input
                            type="range" min={0.1} max={2} step={0.1} value={temperature}
                            onChange={(e) => setTemperature(parseFloat(e.target.value))}
                            className="w-full accent-brand-500"
                        />
                        <p className="text-xs text-slate-600 dark:text-gray-600 mt-1">Lower = sharper focus on most similar neighbors</p>
                    </div>
                    <div>
                        <label className="text-xs text-slate-500 dark:text-gray-500 block mb-1">
                            Similarity Threshold = {threshold.toFixed(2)}
                        </label>
                        <input
                            type="range" min={0.1} max={0.8} step={0.05} value={threshold}
                            onChange={(e) => setThreshold(parseFloat(e.target.value))}
                            className="w-full accent-brand-500"
                        />
                        <p className="text-xs text-slate-600 dark:text-gray-600 mt-1">Minimum cosine similarity to accept neighbor</p>
                    </div>
                    <div>
                        <label className="text-xs text-slate-500 dark:text-gray-500 block mb-1">Neighbors (k) = {k}</label>
                        <input
                            type="range" min={1} max={10} step={1} value={k}
                            onChange={(e) => setK(parseInt(e.target.value))}
                            className="w-full accent-brand-500"
                        />
                        <p className="text-xs text-slate-600 dark:text-gray-600 mt-1">Number of nearest neighbors to retrieve</p>
                    </div>
                </div>
                <button
                    onClick={run}
                    disabled={loading}
                    className="px-5 py-2.5 bg-brand-600 hover:bg-brand-500 disabled:bg-slate-200 dark:bg-gray-700 rounded-lg text-sm text-slate-900 dark:text-white transition-colors"
                >
                    {loading ? "Computing..." : "▶ Run Demo"}
                </button>
            </div>

            {result && (
                <>
                    {/* Prior Result */}
                    <div className="grid grid-cols-4 gap-4">
                        <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500">Prior α</p>
                            <p className="text-xl font-bold text-cyan-400">{result.prior.alpha.toFixed(2)}</p>
                        </div>
                        <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500">Prior β</p>
                            <p className="text-xl font-bold text-cyan-400">{result.prior.beta.toFixed(2)}</p>
                        </div>
                        <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500">Expected Reward</p>
                            <p className="text-xl font-bold text-slate-900 dark:text-white">{result.prior.mean.toFixed(3)}</p>
                        </div>
                        <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 dark:text-gray-500">Confidence</p>
                            <p className="text-xl font-bold text-emerald-400">{(result.prior.confidence * 100).toFixed(1)}%</p>
                        </div>
                    </div>

                    {/* Charts */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Distribution */}
                        <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-3">Prior Distribution</h3>
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
                        <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-3">Neighbor Weights (softmax)</h3>
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

"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

export default function ExperimentsPage() {
    const [data, setData] = useState<Record<string, unknown> | null>(null);
    const [comparison, setComparison] = useState<{
        ts_cumulative_regret: number[];
        daaf_cumulative_regret: number[];
        total_ts_regret: number;
        total_daaf_regret: number;
        improvement_pct: number;
    } | null>(null);
    const [loading, setLoading] = useState(false);
    const [driftMag, setDriftMag] = useState(0.2);
    const [seeds, setSeeds] = useState(10);

    const loadResults = async () => {
        setLoading(true);
        try {
            const res = await api.getResults();
            setData(res);
        } catch {
            /* empty */
        }
        setLoading(false);
    };

    const runComparison = async () => {
        setLoading(true);
        try {
            const res = (await api.runComparison({ drift_magnitude: driftMag, seeds })) as typeof comparison;
            setComparison(res);
        } catch {
            /* empty */
        }
        setLoading(false);
    };

    // Format cumulative regret for chart
    const chartData = comparison
        ? comparison.ts_cumulative_regret.map((ts, i) => ({
            round: i,
            "TS (no forgetting)": Math.round(ts * 100) / 100,
            "AHMN-DAAF": Math.round(comparison.daaf_cumulative_regret[i] * 100) / 100,
        }))
        : [];

    return (
        <div className="max-w-6xl mx-auto space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-white">Live Experiments</h1>
                <p className="text-gray-500 mt-1">Run comparisons and view pre-computed results from 840 experiment runs</p>
            </div>

            {/* Pre-computed results */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-white">Pre-Computed Results (30 seeds × 7 methods × 4 scenarios)</h2>
                    <button
                        onClick={loadResults}
                        disabled={loading}
                        className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:bg-gray-700 rounded-lg text-sm text-white transition-colors"
                    >
                        {loading ? "Loading..." : "Load Results"}
                    </button>
                </div>
                {data && (
                    <div className="text-sm text-gray-300">
                        <p>
                            ✅ Loaded {((data as Record<string, unknown[]>).main_results || []).length} result entries
                        </p>
                        <p className="text-gray-500 text-xs mt-1">
                            Config: {JSON.stringify((data as Record<string, unknown>).experiment_config)}
                        </p>
                    </div>
                )}
            </div>

            {/* Interactive Comparison */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-white mb-4">TS vs DAAF – Live Comparison</h2>
                <div className="flex items-center gap-4 mb-4">
                    <div>
                        <label className="text-xs text-gray-500 block mb-1">Drift Magnitude</label>
                        <input
                            type="range"
                            min={0.05}
                            max={0.35}
                            step={0.05}
                            value={driftMag}
                            onChange={(e) => setDriftMag(parseFloat(e.target.value))}
                            className="accent-brand-500"
                        />
                        <span className="text-sm text-gray-300 ml-2">{driftMag.toFixed(2)}</span>
                    </div>
                    <div>
                        <label className="text-xs text-gray-500 block mb-1">Seeds</label>
                        <input
                            type="range"
                            min={5}
                            max={30}
                            step={5}
                            value={seeds}
                            onChange={(e) => setSeeds(parseInt(e.target.value))}
                            className="accent-brand-500"
                        />
                        <span className="text-sm text-gray-300 ml-2">{seeds}</span>
                    </div>
                    <button
                        onClick={runComparison}
                        disabled={loading}
                        className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:bg-gray-700 rounded-lg text-sm text-white transition-colors ml-auto"
                    >
                        {loading ? "Running..." : "▶ Run Comparison"}
                    </button>
                </div>

                {comparison && (
                    <>
                        {/* Metric cards */}
                        <div className="grid grid-cols-3 gap-4 mb-6">
                            <div className="bg-gray-800 rounded-lg p-4 text-center">
                                <p className="text-sm text-gray-500">TS Regret</p>
                                <p className="text-xl font-bold text-emerald-400">{comparison.total_ts_regret.toFixed(1)}</p>
                            </div>
                            <div className="bg-gray-800 rounded-lg p-4 text-center">
                                <p className="text-sm text-gray-500">DAAF Regret</p>
                                <p className="text-xl font-bold text-red-400">{comparison.total_daaf_regret.toFixed(1)}</p>
                            </div>
                            <div className="bg-gray-800 rounded-lg p-4 text-center">
                                <p className="text-sm text-gray-500">Improvement</p>
                                <p className="text-xl font-bold text-brand-400">{comparison.improvement_pct.toFixed(1)}%</p>
                            </div>
                        </div>

                        {/* Chart */}
                        <ResponsiveContainer width="100%" height={400}>
                            <LineChart data={chartData.filter((_, i) => i % 5 === 0)}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                <XAxis dataKey="round" stroke="#6b7280" tick={{ fontSize: 12 }} />
                                <YAxis stroke="#6b7280" tick={{ fontSize: 12 }} />
                                <Tooltip
                                    contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }}
                                    labelStyle={{ color: "#9ca3af" }}
                                />
                                <Legend />
                                <Line type="monotone" dataKey="TS (no forgetting)" stroke="#10b981" strokeWidth={2} dot={false} />
                                <Line type="monotone" dataKey="AHMN-DAAF" stroke="#ef4444" strokeWidth={2} dot={false} />
                            </LineChart>
                        </ResponsiveContainer>
                    </>
                )}
            </div>
        </div>
    );
}

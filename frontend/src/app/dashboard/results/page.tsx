"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
    Legend, ResponsiveContainer,
} from "recharts";

interface MainResult {
    method: string;
    scenario: string;
    seed: number;
    total_regret: number;
    final_accuracy: number;
    convergence_round: number | null;
}

export default function ResultsPage() {
    const [results, setResults] = useState<MainResult[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.getResults()
            .then((data) => {
                setResults((data as { main_results: MainResult[] }).main_results || []);
            })
            .catch((err) => { console.error("Results fetch failed:", err); })
            .finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    // Aggregate by method — mean across all scenarios and seeds
    const methods = [...new Set(results.map((r) => r.method))];
    const scenarios = [...new Set(results.map((r) => r.scenario))];

    const aggregated = methods.map((method) => {
        const entries = results.filter((r) => r.method === method);
        return {
            method,
            avg_regret: Math.round((entries.reduce((s, e) => s + e.total_regret, 0) / entries.length) * 10) / 10,
            avg_accuracy: Math.round((entries.reduce((s, e) => s + e.final_accuracy, 0) / entries.length) * 1000) / 1000,
            count: entries.length,
        };
    }).sort((a, b) => a.avg_regret - b.avg_regret);

    // Per-scenario breakdown
    const scenarioData = scenarios.map((scenario) => {
        const row: Record<string, string | number> = { scenario };
        methods.forEach((method) => {
            const entries = results.filter((r) => r.method === method && r.scenario === scenario);
            row[method] = entries.length > 0
                ? Math.round((entries.reduce((s, e) => s + e.total_regret, 0) / entries.length) * 10) / 10
                : 0;
        });
        return row;
    });

    const COLORS = ["#10b981", "#06b6d4", "#8b5cf6", "#f59e0b", "#ef4444", "#ec4899", "#6b7280"];

    return (
        <div className="max-w-7xl 3xl:max-w-[1800px] mx-auto space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Experiment Results</h1>
                <p className="text-slate-500 dark:text-gray-500 mt-1">
                    {results.length} runs — {methods.length} methods × {scenarios.length} scenarios × 30 seeds
                </p>
            </div>

            {/* Overall Rankings */}
            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Method Ranking — Average Total Regret</h2>
                <ResponsiveContainer width="100%" height={350}>
                    <BarChart data={aggregated} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis type="number" stroke="#6b7280" tick={{ fontSize: 12 }} />
                        <YAxis dataKey="method" type="category" stroke="#6b7280" tick={{ fontSize: 11 }} width={120} />
                        <Tooltip contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }} />
                        <Bar dataKey="avg_regret" fill="#06b6d4" radius={[0, 4, 4, 0]} />
                    </BarChart>
                </ResponsiveContainer>
            </div>

            {/* Accuracy table */}
            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Summary Table</h2>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-slate-200 dark:border-gray-800">
                                <th className="text-left py-2 px-3 text-slate-500 dark:text-gray-400 font-medium">Rank</th>
                                <th className="text-left py-2 px-3 text-slate-500 dark:text-gray-400 font-medium">Method</th>
                                <th className="text-right py-2 px-3 text-slate-500 dark:text-gray-400 font-medium">Avg Regret ↓</th>
                                <th className="text-right py-2 px-3 text-slate-500 dark:text-gray-400 font-medium">Avg Accuracy</th>
                                <th className="text-right py-2 px-3 text-slate-500 dark:text-gray-400 font-medium">Runs</th>
                            </tr>
                        </thead>
                        <tbody>
                            {aggregated.map((row, i) => (
                                <tr key={row.method} className="border-b border-slate-200 dark:border-gray-800/50 hover:bg-slate-100 dark:hover:bg-gray-800/30">
                                    <td className="py-2 px-3 text-slate-500 dark:text-gray-500">{i + 1}</td>
                                    <td className="py-2 px-3 text-slate-900 dark:text-white font-medium">
                                        {row.method}
                                        {i === 0 && <span className="ml-2 text-xs text-brand-400">🏆 Best</span>}
                                    </td>
                                    <td className="py-2 px-3 text-right text-slate-600 dark:text-gray-300">{row.avg_regret}</td>
                                    <td className="py-2 px-3 text-right text-slate-600 dark:text-gray-300">{row.avg_accuracy}</td>
                                    <td className="py-2 px-3 text-right text-slate-500 dark:text-gray-500">{row.count}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Per-scenario chart */}
            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Regret by Scenario</h2>
                <ResponsiveContainer width="100%" height={400}>
                    <BarChart data={scenarioData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="scenario" stroke="#6b7280" tick={{ fontSize: 11 }} />
                        <YAxis stroke="#6b7280" tick={{ fontSize: 12 }} />
                        <Tooltip contentStyle={{ background: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }} />
                        <Legend />
                        {methods.map((m, i) => (
                            <Bar key={m} dataKey={m} fill={COLORS[i % COLORS.length]} radius={[2, 2, 0, 0]} />
                        ))}
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}

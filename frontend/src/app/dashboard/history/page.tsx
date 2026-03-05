"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/toast";
import type { IDPORun } from "@/types";
import {
    History,
    FileText,
    Clock,
    CheckCircle2,
    XCircle,
    Download,
    RefreshCw,
    ChevronRight,
    AlertTriangle,
    Timer,
    Files,
    Search,
    Filter,
    BarChart3,
} from "lucide-react";

/* ── helpers ── */

function formatDate(iso?: string): string {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleString(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return "—";
    }
}

function formatDuration(ms?: number): string {
    if (!ms && ms !== 0) return "—";
    if (ms < 1000) return `${ms}ms`;
    const sec = ms / 1000;
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const min = Math.floor(sec / 60);
    const rem = Math.round(sec % 60);
    return `${min}m ${rem}s`;
}

function statusColor(status: string) {
    switch (status) {
        case "completed":
            return "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20";
        case "failed":
            return "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20";
        case "running":
            return "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20";
        default:
            return "text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-500/10 border-slate-200 dark:border-slate-500/20";
    }
}

function StatusIcon({ status }: { status: string }) {
    switch (status) {
        case "completed":
            return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
        case "failed":
            return <XCircle className="w-4 h-4 text-red-500" />;
        case "running":
            return <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />;
        default:
            return <Clock className="w-4 h-4 text-slate-400" />;
    }
}

/* ── page ── */

export default function HistoryPage() {
    const { addToast } = useToast();
    const [runs, setRuns] = useState<IDPORun[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState<string>("all");
    const [expandedRun, setExpandedRun] = useState<string | null>(null);

    const fetchRuns = useCallback(async () => {
        setLoading(true);
        try {
            const data = await api.getIDPORuns();
            setRuns(data.runs ?? []);
        } catch (err) {
            console.error("Failed to load runs:", err);
            addToast({ type: "error", title: "Failed to load processing history" });
            setRuns([]);
        } finally {
            setLoading(false);
        }
    }, [addToast]);

    useEffect(() => {
        fetchRuns();
    }, [fetchRuns]);

    /* Computed stats */
    const totalRuns = runs.length;
    const completedRuns = runs.filter((r) => r.status === "completed").length;
    const failedRuns = runs.filter((r) => r.status === "failed").length;
    const totalDocs = runs.reduce((acc, r) => acc + (r.doc_count ?? 0), 0);

    /* Filter logic */
    const filtered = runs.filter((r) => {
        if (statusFilter !== "all" && r.status !== statusFilter) return false;
        if (searchQuery) {
            const q = searchQuery.toLowerCase();
            return (
                r.run_id.toLowerCase().includes(q) ||
                (r.config_path ?? "").toLowerCase().includes(q) ||
                (r.started_at ?? "").toLowerCase().includes(q)
            );
        }
        return true;
    });

    /* Download handler */
    const handleDownload = async (runId: string, type: "docs" | "entities") => {
        try {
            const url = `/api/idpo/runs/${runId}/${type}.xlsx`;
            const res = await fetch(url, {
                headers: { Authorization: `Bearer ${localStorage.getItem("token") ?? ""}` },
            });
            if (!res.ok) throw new Error("Download failed");
            const blob = await res.blob();
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = `${runId}_${type}.xlsx`;
            a.click();
            URL.revokeObjectURL(a.href);
            addToast({ type: "success", title: `Downloaded ${type}.xlsx` });
        } catch {
            addToast({ type: "error", title: `Failed to download ${type}.xlsx` });
        }
    };

    return (
        <div className="space-y-6">
            {/* ── Header ── */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-500 to-brand-500 flex items-center justify-center shadow-lg shadow-cyan-500/25">
                        <History className="w-6 h-6 text-white" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                            Processing History
                        </h1>
                        <p className="text-sm text-slate-500 dark:text-gray-400">
                            View past document extraction runs and download results
                        </p>
                    </div>
                </div>
                <button
                    onClick={fetchRuns}
                    disabled={loading}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-700 text-sm font-medium text-slate-700 dark:text-gray-300 hover:bg-slate-50 dark:hover:bg-gray-800 transition-all shadow-sm disabled:opacity-50"
                >
                    <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </button>
            </div>

            {/* ── Stats Cards ── */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                    { label: "Total Runs", value: totalRuns, icon: BarChart3, color: "brand" },
                    { label: "Completed", value: completedRuns, icon: CheckCircle2, color: "emerald" },
                    { label: "Failed", value: failedRuns, icon: AlertTriangle, color: "red" },
                    { label: "Docs Processed", value: totalDocs, icon: Files, color: "cyan" },
                ].map((stat) => (
                    <div
                        key={stat.label}
                        className="relative overflow-hidden rounded-2xl bg-white/80 dark:bg-gray-900/60 backdrop-blur-xl border border-white/60 dark:border-gray-800/40 shadow-lg shadow-slate-200/30 dark:shadow-black/20 p-5"
                    >
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">
                                    {stat.label}
                                </p>
                                <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
                                    {stat.value}
                                </p>
                            </div>
                            <div
                                className={`w-10 h-10 rounded-xl flex items-center justify-center bg-${stat.color}-500/10 dark:bg-${stat.color}-500/20`}
                            >
                                <stat.icon className={`w-5 h-5 text-${stat.color}-500`} />
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* ── Filters ── */}
            <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input
                        type="text"
                        placeholder="Search by run ID or config..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-700 text-sm text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-brand-500/30 focus:border-brand-400 transition-all"
                    />
                </div>
                <div className="flex items-center gap-2">
                    <Filter className="w-4 h-4 text-slate-400" />
                    {["all", "completed", "failed", "running"].map((s) => (
                        <button
                            key={s}
                            onClick={() => setStatusFilter(s)}
                            className={`px-3 py-2 rounded-lg text-xs font-semibold capitalize transition-all ${
                                statusFilter === s
                                    ? "bg-brand-500 text-white shadow-sm"
                                    : "bg-white dark:bg-gray-900 text-slate-500 dark:text-gray-400 border border-slate-200 dark:border-gray-700 hover:bg-slate-50 dark:hover:bg-gray-800"
                            }`}
                        >
                            {s}
                        </button>
                    ))}
                </div>
            </div>

            {/* ── Runs List ── */}
            <div className="space-y-3">
                {loading ? (
                    <div className="flex items-center justify-center py-20">
                        <RefreshCw className="w-6 h-6 text-brand-500 animate-spin" />
                        <span className="ml-3 text-sm text-slate-500">Loading runs...</span>
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-center">
                        <div className="w-16 h-16 rounded-2xl bg-slate-100 dark:bg-gray-800 flex items-center justify-center mb-4">
                            <FileText className="w-8 h-8 text-slate-300 dark:text-gray-600" />
                        </div>
                        <h3 className="text-lg font-semibold text-slate-700 dark:text-gray-300 mb-1">
                            {runs.length === 0 ? "No processing runs yet" : "No matching runs"}
                        </h3>
                        <p className="text-sm text-slate-400 dark:text-gray-500 max-w-sm">
                            {runs.length === 0
                                ? "Head over to Doc Extraction to process your first documents."
                                : "Try adjusting your search or filter criteria."}
                        </p>
                    </div>
                ) : (
                    filtered.map((run) => {
                        const isExpanded = expandedRun === run.run_id;
                        return (
                            <div
                                key={run.run_id}
                                className="group rounded-2xl bg-white/80 dark:bg-gray-900/60 backdrop-blur-xl border border-white/60 dark:border-gray-800/40 shadow-lg shadow-slate-200/20 dark:shadow-black/10 overflow-hidden transition-all hover:shadow-xl hover:border-slate-200 dark:hover:border-gray-700"
                            >
                                {/* Run Header */}
                                <button
                                    onClick={() => setExpandedRun(isExpanded ? null : run.run_id)}
                                    className="w-full flex items-center gap-4 px-5 py-4 text-left"
                                >
                                    <StatusIcon status={run.status} />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="text-sm font-semibold text-slate-900 dark:text-white font-mono truncate">
                                                {run.run_id.substring(0, 12)}...
                                            </span>
                                            <span
                                                className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider border ${statusColor(run.status)}`}
                                            >
                                                {run.status}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-4 text-xs text-slate-400 dark:text-gray-500">
                                            <span className="flex items-center gap-1">
                                                <Clock className="w-3 h-3" />
                                                {formatDate(run.started_at)}
                                            </span>
                                            {run.doc_count != null && (
                                                <span className="flex items-center gap-1">
                                                    <Files className="w-3 h-3" />
                                                    {run.doc_count} doc{run.doc_count !== 1 ? "s" : ""}
                                                </span>
                                            )}
                                            {run.duration_ms != null && (
                                                <span className="flex items-center gap-1">
                                                    <Timer className="w-3 h-3" />
                                                    {formatDuration(run.duration_ms)}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <ChevronRight
                                        className={`w-4 h-4 text-slate-300 dark:text-gray-600 transition-transform duration-200 ${
                                            isExpanded ? "rotate-90" : ""
                                        }`}
                                    />
                                </button>

                                {/* Expanded Details */}
                                {isExpanded && (
                                    <div className="border-t border-slate-100 dark:border-gray-800/60 px-5 py-4 bg-slate-50/50 dark:bg-gray-950/30">
                                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                                            <div>
                                                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">
                                                    Run ID
                                                </p>
                                                <p className="text-xs font-mono text-slate-700 dark:text-gray-300 break-all">
                                                    {run.run_id}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">
                                                    Started At
                                                </p>
                                                <p className="text-xs text-slate-700 dark:text-gray-300">
                                                    {formatDate(run.started_at)}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">
                                                    Documents
                                                </p>
                                                <p className="text-xs text-slate-700 dark:text-gray-300">
                                                    {run.doc_count ?? 0} processed
                                                    {(run.failed_count ?? 0) > 0 && (
                                                        <span className="text-red-500 ml-1">
                                                            ({run.failed_count} failed)
                                                        </span>
                                                    )}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">
                                                    Duration
                                                </p>
                                                <p className="text-xs text-slate-700 dark:text-gray-300">
                                                    {formatDuration(run.duration_ms)}
                                                </p>
                                            </div>
                                        </div>

                                        {run.config_path && (
                                            <div className="mb-4">
                                                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">
                                                    Config
                                                </p>
                                                <p className="text-xs font-mono text-slate-500 dark:text-gray-400 bg-white dark:bg-gray-900 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-gray-700 inline-block">
                                                    {run.config_path}
                                                </p>
                                            </div>
                                        )}

                                        {/* Download Buttons */}
                                        <div className="flex flex-wrap gap-2">
                                            {run.has_docs_export && (
                                                <button
                                                    onClick={() => handleDownload(run.run_id, "docs")}
                                                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-500 text-white text-xs font-semibold hover:bg-brand-600 transition-colors shadow-sm"
                                                >
                                                    <Download className="w-3.5 h-3.5" />
                                                    Download Documents
                                                </button>
                                            )}
                                            {run.has_entities_export && (
                                                <button
                                                    onClick={() => handleDownload(run.run_id, "entities")}
                                                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 text-white text-xs font-semibold hover:bg-emerald-600 transition-colors shadow-sm"
                                                >
                                                    <Download className="w-3.5 h-3.5" />
                                                    Download Entities
                                                </button>
                                            )}
                                            {!run.has_docs_export && !run.has_entities_export && (
                                                <p className="text-xs text-slate-400 dark:text-gray-500 italic">
                                                    No exports available for this run.
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })
                )}
            </div>

            {/* ── Footer Summary ── */}
            {!loading && filtered.length > 0 && (
                <div className="flex items-center justify-between px-4 py-3 rounded-xl bg-white/60 dark:bg-gray-900/40 border border-slate-200/40 dark:border-gray-800/40 text-xs text-slate-400 dark:text-gray-500">
                    <span>
                        Showing {filtered.length} of {totalRuns} run{totalRuns !== 1 ? "s" : ""}
                    </span>
                    <span>
                        {totalDocs} total document{totalDocs !== 1 ? "s" : ""} processed
                    </span>
                </div>
            )}
        </div>
    );
}

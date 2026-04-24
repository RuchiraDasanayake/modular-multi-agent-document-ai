"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";
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
    ChevronDown,
    ChevronUp,
    AlertTriangle,
    Timer,
    Files,
    Search,
    ArrowUpDown,
    BarChart3,
    Package,
    Loader2,
    CalendarDays,
    ArrowDownWideNarrow,
    ArrowUpWideNarrow,
} from "lucide-react";

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  Helpers                                                                  */
/* ═══════════════════════════════════════════════════════════════════════════ */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatDate(raw?: string | number): string {
    if (!raw && raw !== 0) return "—";
    try {
        const d = typeof raw === "number"
            ? new Date(raw * 1000)
            : new Date(
                /^\d{10,}(\.\d+)?$/.test(String(raw))
                    ? parseFloat(String(raw)) * 1000
                    : raw
            );
        if (isNaN(d.getTime())) return "—";
        return d.toLocaleString(undefined, {
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

function parseTimestamp(raw?: string | number): number {
    if (!raw && raw !== 0) return 0;
    if (typeof raw === "number") return raw;
    if (/^\d{10,}(\.\d+)?$/.test(String(raw))) return parseFloat(String(raw));
    const d = new Date(raw);
    return isNaN(d.getTime()) ? 0 : d.getTime() / 1000;
}

function formatDuration(ms?: number): string {
    if (!ms && ms !== 0) return "—";
    if (ms < 1000) return `${Math.round(ms)}ms`;
    const sec = ms / 1000;
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const min = Math.floor(sec / 60);
    const rem = Math.round(sec % 60);
    return `${min}m ${rem}s`;
}

function relativeTime(raw?: string | number): string {
    const ts = parseTimestamp(raw);
    if (!ts) return "";
    const diffMs = Date.now() - ts * 1000;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay}d ago`;
    return `${Math.floor(diffDay / 30)}mo ago`;
}

type SortField = "date" | "docs" | "duration" | "status";
type SortDir = "asc" | "desc";

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  Status Components                                                        */
/* ═══════════════════════════════════════════════════════════════════════════ */

function StatusBadge({ status }: { status: string }) {
    const cfg = {
        completed: { icon: CheckCircle2, bg: "bg-emerald-50 dark:bg-emerald-500/10", text: "text-emerald-700 dark:text-emerald-400", border: "border-emerald-200 dark:border-emerald-500/20" },
        failed: { icon: XCircle, bg: "bg-red-50 dark:bg-red-500/10", text: "text-red-700 dark:text-red-400", border: "border-red-200 dark:border-red-500/20" },
        running: { icon: Loader2, bg: "bg-blue-50 dark:bg-blue-500/10", text: "text-blue-700 dark:text-blue-400", border: "border-blue-200 dark:border-blue-500/20" },
    }[status] ?? { icon: Clock, bg: "bg-slate-50 dark:bg-slate-500/10", text: "text-slate-600 dark:text-slate-400", border: "border-slate-200 dark:border-slate-500/20" };
    const Icon = cfg.icon;
    return (
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-bold uppercase tracking-wider border ${cfg.bg} ${cfg.text} ${cfg.border}`}>
            <Icon className={`w-3 h-3 ${status === "running" ? "animate-spin" : ""}`} />
            {status}
        </span>
    );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  Page Component                                                           */
/* ═══════════════════════════════════════════════════════════════════════════ */

export default function HistoryPage() {
    const { addToast } = useToast();
    const [runs, setRuns] = useState<IDPORun[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState<string>("all");
    const [expandedRun, setExpandedRun] = useState<string | null>(null);
    const [sortField, setSortField] = useState<SortField>("date");
    const [sortDir, setSortDir] = useState<SortDir>("desc");
    const [downloading, setDownloading] = useState<string | null>(null);

    /* ── Fetch ── */
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

    useEffect(() => { fetchRuns(); }, [fetchRuns]);

    /* ── Stats ── */
    const totalRuns = runs.length;
    const completedRuns = runs.filter((r) => r.status === "completed").length;
    const failedRuns = runs.filter((r) => r.status === "failed").length;
    const totalDocs = runs.reduce((acc, r) => acc + (r.doc_count ?? 0), 0);
    const avgDuration = completedRuns > 0
        ? runs.filter(r => r.status === "completed" && r.duration_ms).reduce((a, r) => a + (r.duration_ms ?? 0), 0) / completedRuns
        : 0;

    /* ── Filter + Sort ── */
    const filtered = useMemo(() => {
        let list = runs.filter((r) => {
            if (statusFilter !== "all" && r.status !== statusFilter) return false;
            if (searchQuery) {
                const q = searchQuery.toLowerCase();
                return (
                    r.run_id.toLowerCase().includes(q) ||
                    (r.config_path ?? "").toLowerCase().includes(q)
                );
            }
            return true;
        });

        list.sort((a, b) => {
            let cmp = 0;
            switch (sortField) {
                case "date":
                    cmp = parseTimestamp(a.started_at) - parseTimestamp(b.started_at);
                    break;
                case "docs":
                    cmp = (a.doc_count ?? 0) - (b.doc_count ?? 0);
                    break;
                case "duration":
                    cmp = (a.duration_ms ?? 0) - (b.duration_ms ?? 0);
                    break;
                case "status":
                    cmp = (a.status ?? "").localeCompare(b.status ?? "");
                    break;
            }
            return sortDir === "desc" ? -cmp : cmp;
        });

        return list;
    }, [runs, statusFilter, searchQuery, sortField, sortDir]);

    /* ── Sort toggle ── */
    const toggleSort = (field: SortField) => {
        if (sortField === field) {
            setSortDir((d) => (d === "desc" ? "asc" : "desc"));
        } else {
            setSortField(field);
            setSortDir("desc");
        }
    };

    /* ── Download handler (uses cookie auth, not localStorage) ── */
    const handleDownload = async (runId: string, type: "docs" | "entities" | "full_text") => {
        const key = `${runId}_${type}`;
        setDownloading(key);
        try {
            const token = getToken();
            const filename = type === "full_text" ? "full_text.txt" : `${type}.xlsx`;
            const res = await fetch(`${API_BASE}/api/idpo/runs/${runId}/${filename}`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.error || body.detail || `HTTP ${res.status}`);
            }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = type === "full_text"
                ? `${runId.substring(0, 8)}_full_text.txt`
                : `${runId.substring(0, 8)}_${type}.xlsx`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            addToast({ type: "success", title: `Downloaded ${type === "full_text" ? "full_text.txt" : `${type}.xlsx`}` });
        } catch (err) {
            addToast({ type: "error", title: `Download failed: ${err instanceof Error ? err.message : "Unknown error"}` });
        } finally {
            setDownloading(null);
        }
    };

    /* ── Sort button component ── */
    const SortBtn = ({ field, label }: { field: SortField; label: string }) => {
        const active = sortField === field;
        return (
            <button
                onClick={() => toggleSort(field)}
                className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold transition-all ${active
                        ? "bg-brand-500 text-white shadow-sm shadow-brand-500/25"
                        : "text-slate-500 dark:text-gray-400 hover:bg-slate-100 dark:hover:bg-gray-800"
                    }`}
            >
                {label}
                {active ? (
                    sortDir === "desc" ? <ArrowDownWideNarrow className="w-3 h-3" /> : <ArrowUpWideNarrow className="w-3 h-3" />
                ) : (
                    <ArrowUpDown className="w-3 h-3 opacity-40" />
                )}
            </button>
        );
    };

    return (
        <div className="space-y-6">
            {/* ═══ Header ═══ */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="flex items-center gap-4">
                    <div className="relative">
                        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-cyan-500 to-brand-600 flex items-center justify-center shadow-xl shadow-cyan-500/25">
                            <History className="w-7 h-7 text-white" strokeWidth={2} />
                        </div>
                        <div className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full bg-white dark:bg-gray-900 flex items-center justify-center border-2 border-cyan-400 shadow-sm">
                            <span className="text-[9px] font-black text-cyan-600 dark:text-cyan-400">{totalRuns}</span>
                        </div>
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
                            Processing History
                        </h1>
                        <p className="text-sm text-slate-500 dark:text-gray-400 mt-0.5">
                            Track extraction runs, download results, and monitor pipeline performance
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Link
                        href="/dashboard/idpo"
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-brand-500 to-cyan-500 text-white text-sm font-semibold shadow-lg shadow-brand-500/25 hover:shadow-xl hover:shadow-brand-500/40 transition-all hover:scale-[1.02] active:scale-[0.98]"
                    >
                        <FileText className="w-4 h-4" />
                        New Extraction
                    </Link>
                    <button
                        onClick={fetchRuns}
                        disabled={loading}
                        className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-700 text-sm font-medium text-slate-600 dark:text-gray-300 hover:bg-slate-50 dark:hover:bg-gray-800 transition-all shadow-sm disabled:opacity-50"
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                    </button>
                </div>
            </div>

            {/* ═══ Stats Cards ═══ */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                {[
                    { label: "Total Runs", value: totalRuns, icon: BarChart3, iconColor: "text-brand-500", bgColor: "bg-brand-50 dark:bg-brand-500/10", borderColor: "border-brand-200/50 dark:border-brand-500/20" },
                    { label: "Completed", value: completedRuns, icon: CheckCircle2, iconColor: "text-emerald-500", bgColor: "bg-emerald-50 dark:bg-emerald-500/10", borderColor: "border-emerald-200/50 dark:border-emerald-500/20" },
                    { label: "Failed", value: failedRuns, icon: AlertTriangle, iconColor: "text-red-500", bgColor: "bg-red-50 dark:bg-red-500/10", borderColor: "border-red-200/50 dark:border-red-500/20" },
                    { label: "Documents", value: totalDocs, icon: Files, iconColor: "text-cyan-500", bgColor: "bg-cyan-50 dark:bg-cyan-500/10", borderColor: "border-cyan-200/50 dark:border-cyan-500/20" },
                    { label: "Avg Duration", value: formatDuration(avgDuration), icon: Timer, iconColor: "text-amber-500", bgColor: "bg-amber-50 dark:bg-amber-500/10", borderColor: "border-amber-200/50 dark:border-amber-500/20" },
                ].map((stat) => (
                    <div
                        key={stat.label}
                        className={`relative overflow-hidden rounded-2xl bg-white/80 dark:bg-gray-900/60 backdrop-blur-xl border ${stat.borderColor} shadow-sm p-4 transition-all hover:shadow-md`}
                    >
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-gray-500 mb-1">
                                    {stat.label}
                                </p>
                                <p className="text-xl font-bold text-slate-900 dark:text-white">
                                    {stat.value}
                                </p>
                            </div>
                            <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${stat.bgColor}`}>
                                <stat.icon className={`w-4.5 h-4.5 ${stat.iconColor}`} />
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* ═══ Toolbar: Search + Sort + Filter ═══ */}
            <div className="rounded-2xl bg-white/80 dark:bg-gray-900/60 backdrop-blur-xl border border-white/60 dark:border-gray-800/40 shadow-sm p-4">
                <div className="flex flex-col lg:flex-row gap-3">
                    {/* Search */}
                    <div className="relative flex-1">
                        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                        <input
                            type="text"
                            placeholder="Search by run ID, config path..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-50 dark:bg-gray-800/50 border border-slate-200/60 dark:border-gray-700/60 text-sm text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition-all outline-none"
                        />
                    </div>

                    {/* Sort controls */}
                    <div className="flex items-center gap-1 p-1 rounded-xl bg-slate-50 dark:bg-gray-800/50 border border-slate-200/60 dark:border-gray-700/60">
                        <SortBtn field="date" label="Date" />
                        <SortBtn field="docs" label="Docs" />
                        <SortBtn field="duration" label="Duration" />
                        <SortBtn field="status" label="Status" />
                    </div>

                    {/* Status filter */}
                    <div className="flex items-center gap-1 p-1 rounded-xl bg-slate-50 dark:bg-gray-800/50 border border-slate-200/60 dark:border-gray-700/60">
                        {(["all", "completed", "failed"] as const).map((s) => (
                            <button
                                key={s}
                                onClick={() => setStatusFilter(s)}
                                className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold capitalize transition-all ${statusFilter === s
                                        ? "bg-white dark:bg-gray-700 text-slate-900 dark:text-white shadow-sm"
                                        : "text-slate-500 dark:text-gray-400 hover:text-slate-700 dark:hover:text-gray-200"
                                    }`}
                            >
                                {s === "all" ? `All (${totalRuns})` : s === "completed" ? `✓ ${completedRuns}` : `✗ ${failedRuns}`}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* ═══ Runs Table ═══ */}
            {loading ? (
                <div className="flex flex-col items-center justify-center py-24">
                    <div className="relative">
                        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500/20 to-cyan-500/20 flex items-center justify-center">
                            <Loader2 className="w-8 h-8 text-brand-500 animate-spin" />
                        </div>
                    </div>
                    <p className="mt-4 text-sm font-medium text-slate-500 dark:text-gray-400">Loading processing history...</p>
                </div>
            ) : filtered.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-24 text-center">
                    <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-slate-100 to-slate-50 dark:from-gray-800 dark:to-gray-900 flex items-center justify-center mb-5 shadow-inner">
                        <Package className="w-10 h-10 text-slate-300 dark:text-gray-600" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-700 dark:text-gray-300 mb-2">
                        {runs.length === 0 ? "No processing runs yet" : "No matching runs"}
                    </h3>
                    <p className="text-sm text-slate-400 dark:text-gray-500 max-w-sm mb-6">
                        {runs.length === 0
                            ? "Upload documents to start your first extraction pipeline run."
                            : "Try adjusting your search query or filters."}
                    </p>
                    {runs.length === 0 && (
                        <Link
                            href="/dashboard/idpo"
                            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-brand-500 to-cyan-500 text-white text-sm font-semibold shadow-lg shadow-brand-500/25 hover:shadow-xl transition-all"
                        >
                            <FileText className="w-4 h-4" />
                            Start Extracting
                        </Link>
                    )}
                </div>
            ) : (
                <div className="space-y-2">
                    {filtered.map((run, idx) => {
                        const isExpanded = expandedRun === run.run_id;
                        const hasExports = run.has_docs_export || run.has_entities_export || run.has_text_export;
                        return (
                            <div
                                key={run.run_id}
                                className="rounded-2xl bg-white/90 dark:bg-gray-900/70 backdrop-blur-xl border border-slate-200/60 dark:border-gray-800/50 shadow-sm overflow-hidden transition-all duration-200 hover:shadow-md hover:border-slate-300/60 dark:hover:border-gray-700/60"
                            >
                                {/* ── Row Header ── */}
                                <button
                                    onClick={() => setExpandedRun(isExpanded ? null : run.run_id)}
                                    className="w-full flex items-center gap-3 sm:gap-4 px-4 sm:px-5 py-3.5 text-left group"
                                >
                                    {/* Row number */}
                                    <span className="hidden sm:flex w-7 h-7 rounded-lg bg-slate-100 dark:bg-gray-800 items-center justify-center text-[10px] font-bold text-slate-400 dark:text-gray-500 flex-shrink-0">
                                        {idx + 1}
                                    </span>

                                    {/* Status */}
                                    <div className="flex-shrink-0">
                                        <StatusBadge status={run.status} />
                                    </div>

                                    {/* Main info */}
                                    <div className="flex-1 min-w-0 grid grid-cols-1 sm:grid-cols-3 gap-1 sm:gap-4">
                                        {/* Run ID + relative time */}
                                        <div>
                                            <p className="text-sm font-semibold text-slate-800 dark:text-gray-200 font-mono truncate">
                                                {run.run_id.substring(0, 8)}
                                            </p>
                                            <p className="text-[11px] text-slate-400 dark:text-gray-500 flex items-center gap-1 mt-0.5">
                                                <CalendarDays className="w-3 h-3" />
                                                {relativeTime(run.started_at)}
                                            </p>
                                        </div>

                                        {/* Docs + Duration */}
                                        <div className="hidden sm:flex items-center gap-4">
                                            <span className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-gray-400">
                                                <Files className="w-3.5 h-3.5 text-slate-400" />
                                                <span className="font-semibold text-slate-700 dark:text-gray-300">{run.doc_count ?? 0}</span>
                                                doc{(run.doc_count ?? 0) !== 1 ? "s" : ""}
                                            </span>
                                            {(run.failed_count ?? 0) > 0 && (
                                                <span className="text-[10px] font-bold text-red-500 bg-red-50 dark:bg-red-500/10 px-1.5 py-0.5 rounded-md">
                                                    {run.failed_count} failed
                                                </span>
                                            )}
                                        </div>

                                        <div className="hidden sm:flex items-center gap-1.5 text-xs text-slate-500 dark:text-gray-400">
                                            <Timer className="w-3.5 h-3.5 text-slate-400" />
                                            {formatDuration(run.duration_ms)}
                                        </div>
                                    </div>

                                    {/* Export indicators + expand chevron */}
                                    <div className="flex items-center gap-2 flex-shrink-0">
                                        {hasExports && (
                                            <span className="hidden md:flex items-center gap-1 px-2 py-1 rounded-md bg-brand-50 dark:bg-brand-500/10 text-[10px] font-bold text-brand-600 dark:text-brand-400 border border-brand-200/40 dark:border-brand-500/20">
                                                <Download className="w-3 h-3" />
                                                Exports
                                            </span>
                                        )}
                                        {isExpanded ? (
                                            <ChevronUp className="w-4 h-4 text-slate-400 dark:text-gray-500" />
                                        ) : (
                                            <ChevronDown className="w-4 h-4 text-slate-300 dark:text-gray-600 group-hover:text-slate-500 dark:group-hover:text-gray-400 transition-colors" />
                                        )}
                                    </div>
                                </button>

                                {/* ── Expanded Detail Panel ── */}
                                {isExpanded && (
                                    <div className="border-t border-slate-100 dark:border-gray-800/60 bg-gradient-to-b from-slate-50/80 to-white/40 dark:from-gray-950/40 dark:to-gray-900/20 px-5 py-5">
                                        {/* Detail grid */}
                                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
                                            {[
                                                { label: "Run ID", value: run.run_id, mono: true },
                                                { label: "Started", value: formatDate(run.started_at) },
                                                { label: "Documents", value: `${run.doc_count ?? 0} processed${(run.failed_count ?? 0) > 0 ? ` (${run.failed_count} failed)` : ""}` },
                                                { label: "Duration", value: formatDuration(run.duration_ms) },
                                            ].map((item) => (
                                                <div key={item.label} className="bg-white/80 dark:bg-gray-900/50 rounded-xl p-3 border border-slate-100 dark:border-gray-800/40">
                                                    <p className="text-[9px] font-bold uppercase tracking-widest text-slate-400 dark:text-gray-500 mb-1.5">{item.label}</p>
                                                    <p className={`text-xs text-slate-700 dark:text-gray-300 ${item.mono ? "font-mono break-all" : ""}`}>{item.value}</p>
                                                </div>
                                            ))}
                                        </div>

                                        {run.config_path && (
                                            <div className="mb-5 flex items-center gap-2">
                                                <span className="text-[9px] font-bold uppercase tracking-widest text-slate-400 dark:text-gray-500">Config:</span>
                                                <code className="text-xs font-mono text-slate-600 dark:text-gray-400 bg-slate-100 dark:bg-gray-800 px-2.5 py-1 rounded-lg border border-slate-200/60 dark:border-gray-700/40">
                                                    {run.config_path}
                                                </code>
                                            </div>
                                        )}

                                        {/* Download actions */}
                                        <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-100/80 dark:border-gray-800/40">
                                            {run.has_docs_export && (
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleDownload(run.run_id, "docs"); }}
                                                    disabled={downloading === `${run.run_id}_docs`}
                                                    className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-brand-500 to-brand-600 text-white text-xs font-semibold shadow-md shadow-brand-500/20 hover:shadow-lg hover:shadow-brand-500/30 transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:hover:scale-100"
                                                >
                                                    {downloading === `${run.run_id}_docs` ? (
                                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                    ) : (
                                                        <Download className="w-3.5 h-3.5" />
                                                    )}
                                                    Documents (.xlsx)
                                                </button>
                                            )}
                                            {run.has_entities_export && (
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleDownload(run.run_id, "entities"); }}
                                                    disabled={downloading === `${run.run_id}_entities`}
                                                    className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-emerald-600 text-white text-xs font-semibold shadow-md shadow-emerald-500/20 hover:shadow-lg hover:shadow-emerald-500/30 transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:hover:scale-100"
                                                >
                                                    {downloading === `${run.run_id}_entities` ? (
                                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                    ) : (
                                                        <Download className="w-3.5 h-3.5" />
                                                    )}
                                                    Entities (.xlsx)
                                                </button>
                                            )}
                                            {run.has_text_export && (
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleDownload(run.run_id, "full_text"); }}
                                                    disabled={downloading === `${run.run_id}_full_text`}
                                                    className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-sky-600 text-white text-xs font-semibold shadow-md shadow-cyan-500/20 hover:shadow-lg hover:shadow-cyan-500/30 transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:hover:scale-100"
                                                >
                                                    {downloading === `${run.run_id}_full_text` ? (
                                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                    ) : (
                                                        <Download className="w-3.5 h-3.5" />
                                                    )}
                                                    Full Text (.txt)
                                                </button>
                                            )}
                                            {!hasExports && (
                                                <p className="text-xs text-slate-400 dark:text-gray-500 italic flex items-center gap-1.5 py-2">
                                                    <AlertTriangle className="w-3.5 h-3.5" />
                                                    No export files available for this run
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {/* ═══ Footer ═══ */}
            {!loading && filtered.length > 0 && (
                <div className="flex items-center justify-between px-5 py-3 rounded-2xl bg-white/60 dark:bg-gray-900/40 border border-slate-200/40 dark:border-gray-800/40 text-xs text-slate-400 dark:text-gray-500">
                    <span className="flex items-center gap-1.5">
                        <Package className="w-3.5 h-3.5" />
                        Showing {filtered.length} of {totalRuns} run{totalRuns !== 1 ? "s" : ""}
                    </span>
                    <span className="flex items-center gap-3">
                        <span className="flex items-center gap-1">
                            <Files className="w-3.5 h-3.5" />
                            {totalDocs} total doc{totalDocs !== 1 ? "s" : ""}
                        </span>
                        <span className="hidden sm:flex items-center gap-1">
                            <Timer className="w-3.5 h-3.5" />
                            Avg: {formatDuration(avgDuration)}
                        </span>
                    </span>
                </div>
            )}
        </div>
    );
}

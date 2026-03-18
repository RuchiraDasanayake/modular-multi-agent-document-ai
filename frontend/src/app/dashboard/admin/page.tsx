"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useUser } from "@/hooks/use-user";

type Tab = "ltm" | "mtm" | "stm" | "guardrails" | "hitl";

interface LTMEntry {
    id: string;
    policy_id: string;
    doc_type?: string;
    vendor?: string;
}

interface MTMEntry {
    id: string;
    advice_id: string;
    created_at: string;
}

interface STMEntry {
    key: string;
}

interface GuardrailEntry {
    audit_log_id: string;
    doc_type: string;
}

interface HITLEntry {
    feedback_id: string;
    question: string;
}

export default function AdminPage() {
    const { isAdmin, loading: userLoading } = useUser();
    const [tab, setTab] = useState<Tab>("ltm");
    const [data, setData] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
    const [deleting, setDeleting] = useState(false);

    const loadTab = async () => {
        setLoading(true);
        setError("");
        try {
            let result: any = [];
            if (tab === "ltm") result = await api.getDatabaseLTM();
            else if (tab === "mtm") result = await api.getDatabaseMTM();
            else if (tab === "stm") result = await api.getDatabaseSTM();
            else if (tab === "guardrails") result = await api.getDatabaseGuardrails();
            else if (tab === "hitl") result = await api.getDatabaseHITL();
            setData(result || []);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Failed to load data");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { loadTab(); }, [tab]);

    const handleDelete = async (id: string) => {
        setDeleting(true);
        try {
            if (tab === "ltm") await api.deleteRecord("ltm", id);
            else if (tab === "mtm") await api.deleteRecord("mtm", id);
            else if (tab === "stm") await api.deleteRecord("stm", id);
            else if (tab === "guardrails") await api.deleteRecord("guardrails", id);
            else if (tab === "hitl") await api.deleteRecord("hitl", id);
            setDeleteConfirm(null);
            loadTab();
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Failed to delete record");
        } finally {
            setDeleting(false);
        }
    };

    if (loading || userLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    if (!isAdmin) {
        return (
            <div className="max-w-4xl 3xl:max-w-5xl mx-auto">
                <div className="glass-panel rounded-2xl p-12 text-center">
                    <div className="w-16 h-16 mx-auto rounded-2xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center mb-4">
                        <span className="text-3xl">🔒</span>
                    </div>
                    <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Access Denied</h2>
                    <p className="text-slate-500 dark:text-gray-400 text-sm">You need administrator privileges to access this page.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-6xl 3xl:max-w-7xl mx-auto space-y-8">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Database Records Management</h1>
                    <p className="text-slate-500 dark:text-gray-500 mt-1">Delete database records from LTM, MTM, STM, Guardrails, and HITL</p>
                </div>
            </div>

            {/* Tab Navigation */}
            <div className="flex flex-wrap gap-2">
                {(["ltm", "mtm", "stm", "guardrails", "hitl"] as Tab[]).map((t) => (
                    <button
                        key={t}
                        onClick={() => setTab(t)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                            tab === t
                                ? "bg-brand-600 text-white"
                                : "bg-slate-200 dark:bg-gray-700 text-slate-700 dark:text-gray-300 hover:bg-slate-300 dark:hover:bg-gray-600"
                        }`}
                    >
                        {t.toUpperCase()}
                    </button>
                ))}
            </div>

            {/* Error Message */}
            {error && (
                <div className="text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg px-4 py-3">
                    {error}
                </div>
            )}

            {/* Loading State */}
            {loading && (
                <div className="flex items-center justify-center h-64">
                    <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                </div>
            )}

            {/* Records Table */}
            {!loading && (
                <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl overflow-hidden">
                    {data.length === 0 ? (
                        <div className="flex items-center justify-center py-16 text-center">
                            <div className="w-14 h-14 rounded-2xl bg-slate-100 dark:bg-gray-800 border border-slate-200 dark:border-gray-700 flex items-center justify-center mb-4">
                                <span className="text-2xl">📭</span>
                            </div>
                            <p className="text-sm text-slate-500 dark:text-gray-500">No records found in {tab.toUpperCase()}</p>
                        </div>
                    ) : (
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-slate-200 dark:border-gray-800 bg-slate-100/80 dark:bg-gray-800/40">
                                    <th className="text-left py-3 px-4 text-slate-500 dark:text-gray-400 font-medium">ID / Key</th>
                                    <th className="text-left py-3 px-4 text-slate-500 dark:text-gray-400 font-medium">Details</th>
                                    <th className="text-right py-3 px-4 text-slate-500 dark:text-gray-400 font-medium">Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.map((record: any) => {
                                    const recordId = record.id || record.audit_log_id || record.feedback_id || record.key || "";
                                    return (
                                        <tr key={recordId} className="border-b border-slate-200 dark:border-gray-800/50 hover:bg-slate-50/50 dark:hover:bg-gray-800/20">
                                            <td className="py-3 px-4 text-slate-900 dark:text-white font-mono text-xs break-all">{recordId}</td>
                                            <td className="py-3 px-4 text-slate-600 dark:text-gray-400 text-xs">
                                                {record.doc_type && <span>{record.doc_type}</span>}
                                                {record.question && <span className="truncate block">{record.question}</span>}
                                                {record.policy_id && <span>Policy: {record.policy_id}</span>}
                                                {record.created_at && <span className="text-slate-500 dark:text-gray-500">{new Date(record.created_at).toLocaleString()}</span>}
                                            </td>
                                            <td className="py-3 px-4 text-right">
                                                {deleteConfirm === recordId ? (
                                                    <div className="flex gap-2 justify-end">
                                                        <button
                                                            onClick={() => handleDelete(recordId)}
                                                            disabled={deleting}
                                                            className="text-xs px-3 py-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white rounded transition-colors"
                                                        >
                                                            {deleting ? "Deleting..." : "Confirm"}
                                                        </button>
                                                        <button
                                                            onClick={() => setDeleteConfirm(null)}
                                                            disabled={deleting}
                                                            className="text-xs px-3 py-1 bg-slate-300 dark:bg-gray-700 hover:bg-slate-400 dark:hover:bg-gray-600 disabled:opacity-50 text-slate-900 dark:text-white rounded transition-colors"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <button
                                                        onClick={() => setDeleteConfirm(recordId)}
                                                        className="text-xs text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 transition-colors"
                                                    >
                                                        Delete
                                                    </button>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                </div>
            )}
        </div>
    );
}

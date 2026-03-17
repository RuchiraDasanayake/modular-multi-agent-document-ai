"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useUser } from "@/hooks/use-user";

type Tab = "ltm" | "mtm" | "stm" | "users" | "guardrails" | "hitl";

interface LTMEntry {
    id: string;
    context_hash: string;
    policy_id: string;
    policy_data: Record<string, unknown>;
    validation_metrics?: Record<string, unknown>;
    alpha: number;
    beta: number;
    confidence_score: number;
    last_promoted_at: string;
    doc_type?: string;
    vendor?: string;
    content_profile?: string;
}

interface MTMEntry {
    id: string;
    advice_id: string;
    policy_id_used: string;
    document_context: Record<string, unknown>;
    outcome_metrics: Record<string, unknown>;
    human_corrected: boolean;
    created_at: string;
}

interface STMEntry {
    key: string;
    ttl_seconds: number;
    data: Record<string, unknown>;
}

interface UserEntry {
    id: string;
    email: string;
    username: string;
    role: string;
    is_active: boolean;
    created_at: string;
}

interface GuardrailEntry {
    audit_log_id: string;
    document_id: string | null;
    doc_type: string;
    overall_passes: boolean;
    processing_time_ms: number;
    checks: Record<string, unknown>;
    timestamp: string;
}

interface HITLEntry {
    feedback_id: string;
    question: string;
    original_answer: string;
    feedback_type: string;
    is_answer_correct: boolean;
    explanation_quality?: number;
    highlight_accuracy?: number;
    xai_helpfulness?: number;
    ratings?: { explanation_quality?: number; highlight_accuracy?: number; xai_helpfulness?: number };
    timestamp?: string;
    created_at?: string;
    priority?: string;
}

const TABS: { key: Tab; label: string; icon: string; desc: string }[] = [
    { key: "ltm", label: "LTM Policies", icon: "🧠", desc: "Long-Term Memory — validated policy strategies with Thompson Sampling α/β" },
    { key: "mtm", label: "MTM Outcomes", icon: "📊", desc: "Mid-Term Memory — recent advice outcomes and performance metrics" },
    { key: "stm", label: "STM Cache", icon: "⚡", desc: "Short-Term Memory — active Redis entries with TTL countdown" },
    { key: "users", label: "Users", icon: "👥", desc: "Registered users and their roles" },
    { key: "guardrails", label: "Guardrail Audit", icon: "🛡️", desc: "Validation audit log — pass/fail history per document" },
    { key: "hitl", label: "HITL Feedback", icon: "✍️", desc: "Human-in-the-Loop expert feedback entries" },
];

function Badge({ children, color = "gray" }: { children: React.ReactNode; color?: string }) {
    const colors: Record<string, string> = {
        green: "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20",
        red: "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20",
        blue: "bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-500/20",
        amber: "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/20",
        violet: "bg-violet-50 dark:bg-violet-500/10 text-violet-700 dark:text-violet-400 border-violet-200 dark:border-violet-500/20",
        gray: "bg-slate-50 dark:bg-gray-800 text-slate-600 dark:text-gray-400 border-slate-200 dark:border-gray-700",
    };
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${colors[color] || colors.gray}`}>
            {children}
        </span>
    );
}

function JsonCell({ data }: { data: unknown }) {
    const [expanded, setExpanded] = useState(false);
    if (data === undefined || data === null) return <span className="text-slate-400 dark:text-gray-600 italic text-xs">—</span>;
    const text = JSON.stringify(data, null, 2);
    const preview = JSON.stringify(data) ?? "null";
    const isLong = preview.length > 60;

    return (
        <div className="relative">
            <button
                onClick={() => isLong && setExpanded(!expanded)}
                className={`text-left text-xs font-mono break-all ${isLong ? "cursor-pointer hover:text-brand-600 dark:hover:text-brand-400" : ""}`}
            >
                {expanded ? (
                    <pre className="whitespace-pre-wrap text-slate-600 dark:text-gray-400 max-w-xs">{text}</pre>
                ) : (
                    <span className="text-slate-600 dark:text-gray-400">
                        {isLong ? preview.slice(0, 57) + "..." : preview}
                    </span>
                )}
            </button>
        </div>
    );
}

function Th({ children }: { children: React.ReactNode }) {
    return (
        <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 dark:text-gray-500 uppercase tracking-wider whitespace-nowrap">
            {children}
        </th>
    );
}

function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
    return (
        <td className={`px-4 py-3 text-sm text-slate-700 dark:text-gray-300 ${className}`}>
            {children}
        </td>
    );
}

function policyColor(pid: string): string {
    const map: Record<string, string> = {
        table_heavy: "blue",
        forms: "green",
        scanned_text: "amber",
        mixed_content: "violet",
        default: "gray",
    };
    return map[pid] || "gray";
}

function formatTime(iso: string): string {
    try {
        return new Date(iso).toLocaleString(undefined, {
            month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        });
    } catch {
        return iso;
    }
}

// ── Main Component ──────────────────────────────────────────────────────────

export default function DatabaseExplorerPage() {
    const { isAdmin, loading: userLoading } = useUser();
    const [tab, setTab] = useState<Tab>("ltm");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    // Data stores
    const [ltm, setLtm] = useState<LTMEntry[]>([]);
    const [mtm, setMtm] = useState<MTMEntry[]>([]);
    const [stm, setStm] = useState<STMEntry[]>([]);
    const [users, setUsers] = useState<UserEntry[]>([]);
    const [guardrails, setGuardrails] = useState<GuardrailEntry[]>([]);
    const [hitl, setHitl] = useState<HITLEntry[]>([]);

    const loadTab = useCallback(async (t: Tab) => {
        setLoading(true);
        setError("");
        try {
            switch (t) {
                case "ltm": setLtm(await api.getLTM() as LTMEntry[]); break;
                case "mtm": setMtm(await api.getMTM(200) as MTMEntry[]); break;
                case "stm": setStm(await api.getSTM() as STMEntry[]); break;
                case "users": setUsers(await api.getUsers() as UserEntry[]); break;
                case "guardrails": setGuardrails(await api.getGuardrailHistory(200) as GuardrailEntry[]); break;
                case "hitl": {
                    const h = await api.getFeedbackHistory(200);
                    setHitl(((h as unknown as Record<string, unknown>)?.items || []) as HITLEntry[]);
                    break;
                }
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load data");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadTab(tab); }, [tab, loadTab]);

    if (userLoading) {
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
                    <p className="text-slate-500 dark:text-gray-400 text-sm">Administrator privileges required.</p>
                </div>
            </div>
        );
    }

    const tabInfo = TABS.find((t) => t.key === tab)!;

    return (
        <div className="max-w-7xl 3xl:max-w-full mx-auto space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Database Explorer</h1>
                <p className="text-slate-500 dark:text-gray-500 mt-1">Browse all data across PostgreSQL, Redis, and audit logs</p>
            </div>

            {/* Tab Bar */}
            <div className="flex flex-wrap gap-2">
                {TABS.map((t) => (
                    <button
                        key={t.key}
                        onClick={() => setTab(t.key)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${tab === t.key
                                ? "bg-brand-500/10 dark:bg-brand-500/15 text-brand-700 dark:text-brand-300 border border-brand-200/60 dark:border-brand-500/20 shadow-sm"
                                : "text-slate-600 dark:text-gray-400 hover:bg-slate-100 dark:hover:bg-gray-800 border border-transparent"
                            }`}
                    >
                        <span>{t.icon}</span>
                        {t.label}
                    </button>
                ))}
            </div>

            {/* Description + Refresh */}
            <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500 dark:text-gray-500">{tabInfo.desc}</p>
                <button
                    onClick={() => loadTab(tab)}
                    className="text-xs text-brand-600 dark:text-brand-400 hover:underline"
                >
                    ↻ Refresh
                </button>
            </div>

            {/* Error */}
            {error && (
                <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-700 dark:text-red-400">
                    {error}
                </div>
            )}

            {/* Data Table */}
            <div className="glass-panel rounded-2xl overflow-hidden">
                {loading ? (
                    <div className="flex items-center justify-center h-48">
                        <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        {tab === "ltm" && <LTMTable data={ltm} />}
                        {tab === "mtm" && <MTMTable data={mtm} />}
                        {tab === "stm" && <STMTable data={stm} />}
                        {tab === "users" && <UsersTable data={users} />}
                        {tab === "guardrails" && <GuardrailsTable data={guardrails} />}
                        {tab === "hitl" && <HITLTable data={hitl} />}
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Table Components ────────────────────────────────────────────────────────

function LTMTable({ data }: { data: LTMEntry[] }) {
    if (!data.length) return <EmptyState label="No LTM policies found — run the seed script to populate." />;
    return (
        <table className="min-w-full divide-y divide-slate-200/60 dark:divide-gray-800/60">
            <thead className="bg-slate-50/50 dark:bg-gray-900/30"><tr>
                <Th>Doc Type</Th><Th>Policy ID</Th><Th>Content Profile</Th><Th>α (alpha)</Th><Th>β (beta)</Th><Th>Mean</Th><Th>Confidence</Th><Th>Last Promoted</Th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-gray-800/40">
                {data.map((row, i) => {
                    const mean = row.alpha / (row.alpha + row.beta);
                    const policyData = row.policy_data || {};
                    const validationMetrics = row.validation_metrics || {};
                    const vmContext = (validationMetrics as Record<string, Record<string, string>>).document_context || {};
                    const docType = row.doc_type || (policyData as Record<string, string>).doc_type || vmContext.doc_type || "—";
                    const contentProfile =
                        row.content_profile
                        || (policyData as Record<string, string>).content_profile
                        || vmContext.content_profile
                        || "—";
                    return (
                        <tr key={row.id || i} className="hover:bg-slate-50/50 dark:hover:bg-gray-800/20 transition-colors">
                            <Td className="text-xs font-medium">{docType}</Td>
                            <Td><Badge color={policyColor(row.policy_id)}>{row.policy_id}</Badge></Td>
                            <Td className="text-xs text-slate-500 dark:text-gray-500">{contentProfile}</Td>
                            <Td className="font-mono">{row.alpha.toFixed(1)}</Td>
                            <Td className="font-mono">{row.beta.toFixed(1)}</Td>
                            <Td className="font-mono font-semibold">{mean.toFixed(3)}</Td>
                            <Td className="font-mono">{row.confidence_score?.toFixed(2) ?? "—"}</Td>
                            <Td className="text-xs text-slate-500 dark:text-gray-500">{formatTime(row.last_promoted_at)}</Td>
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
}

function MTMTable({ data }: { data: MTMEntry[] }) {
    if (!data.length) return <EmptyState label="No MTM outcomes recorded yet." />;
    return (
        <table className="min-w-full divide-y divide-slate-200/60 dark:divide-gray-800/60">
            <thead className="bg-slate-50/50 dark:bg-gray-900/30"><tr>
                <Th>Policy Used</Th><Th>Doc Type</Th><Th>Content Profile</Th><Th>F1 Score</Th><Th>Cost</Th><Th>Time (ms)</Th><Th>Human Corrected</Th><Th>Created</Th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-gray-800/40">
                {data.map((row, i) => {
                    const ctx = row.document_context || {};
                    const metrics = row.outcome_metrics || {};
                    const f1 = (metrics as Record<string, number>).f1_score;
                    const docType = (ctx as Record<string, string>).doc_type || "—";
                    const contentProfile = (ctx as Record<string, string>).content_profile || "—";
                    return (
                        <tr key={row.id || i} className="hover:bg-slate-50/50 dark:hover:bg-gray-800/20 transition-colors">
                            <Td><Badge color={policyColor(row.policy_id_used)}>{row.policy_id_used}</Badge></Td>
                            <Td className="text-xs">{docType}</Td>
                            <Td className="text-xs text-slate-500 dark:text-gray-500">{contentProfile}</Td>
                            <Td className="font-mono font-semibold">
                                {f1 != null ? (
                                    <span className={f1 >= 0.7 ? "text-emerald-600 dark:text-emerald-400" : f1 >= 0.5 ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400"}>
                                        {f1.toFixed(3)}
                                    </span>
                                ) : "—"}
                            </Td>
                            <Td className="font-mono">{(metrics as Record<string, number>).cost?.toFixed(3) ?? "—"}</Td>
                            <Td className="font-mono">{(metrics as Record<string, number>).processing_time_ms?.toFixed(0) ?? "—"}</Td>
                            <Td>{row.human_corrected ? <Badge color="amber">Yes</Badge> : <Badge color="gray">No</Badge>}</Td>
                            <Td className="text-xs text-slate-500 dark:text-gray-500">{formatTime(row.created_at)}</Td>
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
}

function STMTable({ data }: { data: STMEntry[] }) {
    if (!data.length) return <EmptyState label="No active STM entries — entries appear when AHMN processes advice requests." />;
    return (
        <table className="min-w-full divide-y divide-slate-200/60 dark:divide-gray-800/60">
            <thead className="bg-slate-50/50 dark:bg-gray-900/30"><tr>
                <Th>Key</Th><Th>TTL (seconds)</Th><Th>Data</Th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-gray-800/40">
                {data.map((row, i) => (
                    <tr key={row.key || i} className="hover:bg-slate-50/50 dark:hover:bg-gray-800/20 transition-colors">
                        <Td className="font-mono text-xs">{row.key}</Td>
                        <Td className="font-mono">
                            <span className={row.ttl_seconds < 300 ? "text-red-500" : row.ttl_seconds < 900 ? "text-amber-500" : "text-emerald-500"}>
                                {row.ttl_seconds}s
                            </span>
                        </Td>
                        <Td><JsonCell data={row.data} /></Td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function UsersTable({ data }: { data: UserEntry[] }) {
    if (!data.length) return <EmptyState label="No users found." />;
    return (
        <table className="min-w-full divide-y divide-slate-200/60 dark:divide-gray-800/60">
            <thead className="bg-slate-50/50 dark:bg-gray-900/30"><tr>
                <Th>Username</Th><Th>Email</Th><Th>Role</Th><Th>Active</Th><Th>Created</Th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-gray-800/40">
                {data.map((row) => (
                    <tr key={row.id} className="hover:bg-slate-50/50 dark:hover:bg-gray-800/20 transition-colors">
                        <Td className="font-semibold">{row.username}</Td>
                        <Td className="text-xs">{row.email}</Td>
                        <Td><Badge color={row.role === "admin" ? "violet" : "blue"}>{row.role}</Badge></Td>
                        <Td>{row.is_active ? <Badge color="green">Active</Badge> : <Badge color="red">Disabled</Badge>}</Td>
                        <Td className="text-xs text-slate-500 dark:text-gray-500">{formatTime(row.created_at)}</Td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function GuardrailsTable({ data }: { data: GuardrailEntry[] }) {
    if (!data.length) return <EmptyState label="No guardrail audits recorded yet." />;
    return (
        <table className="min-w-full divide-y divide-slate-200/60 dark:divide-gray-800/60">
            <thead className="bg-slate-50/50 dark:bg-gray-900/30"><tr>
                <Th>Doc Type</Th><Th>Result</Th><Th>Time (ms)</Th><Th>Checks</Th><Th>Created</Th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-gray-800/40">
                {data.map((row, i) => (
                    <tr key={row.audit_log_id || i} className="hover:bg-slate-50/50 dark:hover:bg-gray-800/20 transition-colors">
                        <Td className="text-xs">{row.doc_type}</Td>
                        <Td>{row.overall_passes ? <Badge color="green">PASS</Badge> : <Badge color="red">FAIL</Badge>}</Td>
                        <Td className="font-mono">{row.processing_time_ms?.toFixed(0)}</Td>
                        <Td><JsonCell data={row.checks} /></Td>
                        <Td className="text-xs text-slate-500 dark:text-gray-500">{formatTime(row.timestamp)}</Td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function HITLTable({ data }: { data: HITLEntry[] }) {
    if (!data.length) return <EmptyState label="No HITL feedback submitted yet." />;
    return (
        <table className="min-w-full divide-y divide-slate-200/60 dark:divide-gray-800/60">
            <thead className="bg-slate-50/50 dark:bg-gray-900/30"><tr>
                <Th>Question</Th><Th>Type</Th><Th>Correct?</Th><Th>XAI Quality</Th><Th>Created</Th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-gray-800/40">
                {data.map((row, i) => (
                    <tr key={row.feedback_id || i} className="hover:bg-slate-50/50 dark:hover:bg-gray-800/20 transition-colors">
                        <Td className="max-w-xs truncate text-xs">{row.question}</Td>
                        <Td><Badge color={row.feedback_type === "correct" ? "green" : row.feedback_type === "incorrect" ? "red" : "amber"}>{row.feedback_type}</Badge></Td>
                        <Td>{row.is_answer_correct ? <Badge color="green">Yes</Badge> : <Badge color="red">No</Badge>}</Td>
                        <Td className="font-mono">{(row.explanation_quality ?? row.ratings?.explanation_quality ?? 0)}/5</Td>
                        <Td className="text-xs text-slate-500 dark:text-gray-500">{formatTime(row.timestamp || row.created_at || '')}</Td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function EmptyState({ label }: { label: string }) {
    return (
        <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 dark:bg-gray-800 border border-slate-200 dark:border-gray-700 flex items-center justify-center mb-4">
                <span className="text-2xl">📭</span>
            </div>
            <p className="text-sm text-slate-500 dark:text-gray-500 max-w-md">{label}</p>
        </div>
    );
}

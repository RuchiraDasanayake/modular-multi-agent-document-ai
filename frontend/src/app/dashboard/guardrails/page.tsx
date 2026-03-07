"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/toast";
import type {
    GuardrailValidateRequest,
    GuardrailValidateResponse,
    GuardrailStats,
} from "@/types";

const DOC_TYPES = [
    "ClinicalSummary",
    "MedicationDosage",
    "Invoice",
    "InsuranceClaim",
    "BankStatement",
    "PurchaseOrder",
    "Receipt",
] as const;

const EXAMPLE_PAYLOADS: Record<string, Omit<GuardrailValidateRequest, "document_context">> = {
    Invoice: {
        query: "Extract invoice details",
        answer_json: '{"customer_name": "Jane Smith", "subtotal": 100, "tax": 10, "total": 110}',
        source_contexts: ["Invoice to Jane Smith. Subtotal: 100.00, Tax: 10.00, Total: 110.00"],
        document_id: "inv-demo-001",
    },
    ClinicalSummary: {
        query: "Summarize patient condition",
        answer_json: '{"patient_name": "John Doe", "condition": "Stable", "summary": "Routine checkup", "next_steps": "Follow-up in 6 months"}',
        source_contexts: ["Patient John Doe is stable with no issues noted."],
        document_id: "clin-demo-001",
    },
    Receipt: {
        query: "Extract receipt info",
        answer_json: '{"merchant": "StoreY", "total": 49.99, "date": "2025-12-01", "items": ["ItemA", "ItemB"]}',
        source_contexts: ["Receipt from StoreY. Total: 49.99. Date: 2025-12-01"],
        document_id: "rec-demo-001",
    },
};

function Badge({ pass: p }: { pass: boolean }) {
    return (
        <span
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${p ? "bg-green-500/10 text-green-400 border border-green-500/20" : "bg-red-500/10 text-red-400 border border-red-500/20"}`}
        >
            {p ? "PASS" : "FAIL"}
        </span>
    );
}

export default function GuardrailsPage() {
    const { addToast } = useToast();
    const [docType, setDocType] = useState<string>("Invoice");
    const [vendor, setVendor] = useState("");
    const [query, setQuery] = useState(EXAMPLE_PAYLOADS.Invoice.query);
    const [answerJson, setAnswerJson] = useState(EXAMPLE_PAYLOADS.Invoice.answer_json);
    const [sourceContexts, setSourceContexts] = useState(EXAMPLE_PAYLOADS.Invoice.source_contexts.join("\n"));
    const [documentId, setDocumentId] = useState(EXAMPLE_PAYLOADS.Invoice.document_id || "");
    const [result, setResult] = useState<GuardrailValidateResponse | null>(null);
    const [stats, setStats] = useState<GuardrailStats | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const loadExample = (type: string) => {
        setDocType(type);
        const example = EXAMPLE_PAYLOADS[type];
        if (example) {
            setQuery(example.query);
            setAnswerJson(example.answer_json);
            setSourceContexts(example.source_contexts.join("\n"));
            setDocumentId(example.document_id || "");
        }
    };

    const handleValidate = async () => {
        setLoading(true);
        setError("");
        setResult(null);
        try {
            const res = await api.validateGuardrail({
                document_context: {
                    doc_type: docType,
                    vendor: vendor || undefined,
                },
                query,
                answer_json: answerJson,
                source_contexts: sourceContexts.split("\n").filter(Boolean),
                document_id: documentId || undefined,
            });
            setResult(res);
            addToast({ type: res.overall_passes ? "success" : "warning", title: res.overall_passes ? "All checks passed" : "Validation issues found", message: `${res.validation_results.length} checks in ${res.processing_time_ms.toFixed(0)}ms` });
            // Also refresh stats
            const s = await api.getGuardrailStats();
            setStats(s);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "Validation failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-7xl 3xl:max-w-[1800px] mx-auto space-y-6">
            {/* Header */}
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6 animate-fade-in-up">
                <div className="absolute inset-0 bg-gradient-to-r from-emerald-500/5 to-green-500/5 dark:from-emerald-500/[0.03] dark:to-green-500/[0.03]" />
                <div className="relative">
                    <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-green-500 flex items-center justify-center shadow-lg shadow-emerald-500/20">
                            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                            </svg>
                        </div>
                        Hallucination Guardrails
                    </h1>
                    <p className="text-slate-500 dark:text-gray-400 mt-1.5 text-sm">
                        Validates extracted data through 5 independent checks: does it match the schema, is it internally consistent, does it follow domain rules, does it leak PII, and is it faithful to the source?
                    </p>
                </div>
            </div>

            {/* Quick-load examples */}
            <div className="flex gap-2 flex-wrap">
                {Object.keys(EXAMPLE_PAYLOADS).map((type) => (
                    <button
                        key={type}
                        onClick={() => loadExample(type)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${docType === type ? "bg-brand-500/20 text-brand-400 border border-brand-500/30" : "bg-slate-100 dark:bg-gray-800 text-slate-500 dark:text-gray-400 hover:bg-slate-200 dark:hover:bg-gray-700"}`}
                    >
                        {type}
                    </button>
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Input Form */}
                <div className="glass-panel rounded-2xl p-6 space-y-4 animate-fade-in-up" style={{ animationDelay: '60ms' }}>
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white">Validation Input</h2>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-[10px] text-slate-500 dark:text-gray-400 mb-1.5 font-semibold uppercase tracking-wider">Document Type</label>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-1.5">Category of document being validated</p>
                            <select
                                value={docType}
                                onChange={(e) => setDocType(e.target.value)}
                                className="w-full glass-input px-3 py-2.5 text-sm"
                            >
                                {DOC_TYPES.map((t) => (
                                    <option key={t} value={t}>{t}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="block text-[10px] text-slate-500 dark:text-gray-400 mb-1.5 font-semibold uppercase tracking-wider">Vendor (optional)</label>
                            <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-1.5">Supplier or source name for context-specific rules</p>
                            <input
                                value={vendor}
                                onChange={(e) => setVendor(e.target.value)}
                                className="w-full glass-input px-3 py-2.5 text-sm"
                                placeholder="e.g. ABC Suppliers"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-[10px] text-slate-500 dark:text-gray-400 mb-1.5 font-semibold uppercase tracking-wider">Query</label>
                        <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-1.5">The question or instruction the AI was given to extract data</p>
                        <input
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            className="w-full glass-input px-3 py-2.5 text-sm"
                        />
                    </div>

                    <div>
                        <label className="block text-[10px] text-slate-500 dark:text-gray-400 mb-1.5 font-semibold uppercase tracking-wider">Extracted JSON</label>
                        <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-1.5">The AI’s output in JSON format — this is what gets validated</p>
                        <textarea
                            value={answerJson}
                            onChange={(e) => setAnswerJson(e.target.value)}
                            rows={5}
                            className="w-full glass-input px-3 py-2.5 text-sm font-mono"
                        />
                    </div>

                    <div>
                        <label className="block text-[10px] text-slate-500 dark:text-gray-400 mb-1.5 font-semibold uppercase tracking-wider">Source Contexts</label>
                        <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-1.5">Original text passages the AI used — one per line. Used to check faithfulness.</p>
                        <textarea
                            value={sourceContexts}
                            onChange={(e) => setSourceContexts(e.target.value)}
                            rows={3}
                            className="w-full glass-input px-3 py-2.5 text-sm"
                        />
                    </div>

                    <div>
                        <label className="block text-[10px] text-slate-500 dark:text-gray-400 mb-1.5 font-semibold uppercase tracking-wider">Document ID (optional)</label>
                        <p className="text-[11px] text-slate-500 dark:text-gray-500 mb-1.5">Unique identifier for audit trail tracking</p>
                        <input
                            value={documentId}
                            onChange={(e) => setDocumentId(e.target.value)}
                            className="w-full glass-input px-3 py-2.5 text-sm"
                        />
                    </div>

                    <button
                        onClick={handleValidate}
                        disabled={loading}
                        className="w-full bg-gradient-to-r from-emerald-500 to-green-500 hover:shadow-lg hover:shadow-emerald-500/25 disabled:opacity-50 text-white px-4 py-3 rounded-xl text-sm font-bold transition-all duration-200 active:scale-[0.98] flex items-center justify-center gap-2"
                    >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                        {loading ? "Validating..." : "Run Guardrail Validation"}
                    </button>

                    {error && <p className="text-red-400 text-sm">{error}</p>}
                </div>

                {/* Results */}
                <div className="space-y-4">
                    {result && (
                        <div className="glass-panel rounded-2xl p-6 space-y-4 animate-fade-in-up">
                            <div className="flex items-center justify-between">
                                <h2 className="text-lg font-bold text-slate-900 dark:text-white">Validation Result</h2>
                                <Badge pass={result.overall_passes} />
                            </div>

                            <div className="grid grid-cols-3 gap-3 stagger-children">
                                <div className="glass-stat p-4">
                                    <div className="relative z-10 text-center">
                                        <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Checks Run</p>
                                        <p className="text-xl font-extrabold text-slate-900 dark:text-white">{result.validation_results.length}</p>
                                        <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-0.5">Total validations performed</p>
                                    </div>
                                </div>
                                <div className="glass-stat p-4">
                                    <div className="relative z-10 text-center">
                                        <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Failed</p>
                                        <p className="text-xl font-extrabold text-red-500 dark:text-red-400">{result.metrics.num_failed_checks}</p>
                                        <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-0.5">Checks that flagged issues</p>
                                    </div>
                                </div>
                                <div className="glass-stat p-4">
                                    <div className="relative z-10 text-center">
                                        <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Time</p>
                                        <p className="text-xl font-extrabold text-slate-900 dark:text-white">{result.processing_time_ms.toFixed(0)}ms</p>
                                        <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-0.5">Processing duration</p>
                                    </div>
                                </div>
                            </div>

                            {/* Per-check results */}
                            <div className="space-y-2">
                                {result.validation_results.map((check, i) => (
                                    <div
                                        key={i}
                                        className={`border rounded-lg p-3 ${check.is_pass ? "border-green-500/20 bg-green-500/5" : "border-red-500/20 bg-red-500/5"}`}
                                    >
                                        <div className="flex items-center justify-between mb-1">
                                            <span className="text-sm font-medium text-slate-900 dark:text-white capitalize">
                                                {check.name.replace(/_/g, " ")}
                                            </span>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs text-slate-500 dark:text-gray-400">Score: {check.score.toFixed(2)}</span>
                                                <Badge pass={check.is_pass} />
                                            </div>
                                        </div>
                                        <p className="text-xs text-slate-500 dark:text-gray-400">{check.details}</p>
                                    </div>
                                ))}
                            </div>

                            <p className="text-xs text-slate-500 dark:text-gray-500">Audit ID: {result.audit_log_id}</p>
                        </div>
                    )}

                    {/* Stats panel */}
                    {stats && stats.total_validations > 0 && (
                        <div className="glass-panel rounded-2xl p-6 animate-fade-in-up">
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-3">Session Stats</h2>
                            <div className="grid grid-cols-2 gap-3 stagger-children">
                                <div className="glass-stat p-4">
                                    <div className="relative z-10 text-center">
                                        <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Total Runs</p>
                                        <p className="text-xl font-extrabold text-slate-900 dark:text-white">{stats.total_validations}</p>
                                    </div>
                                </div>
                                <div className="glass-stat p-4">
                                    <div className="relative z-10 text-center">
                                        <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Pass Rate</p>
                                        <p className="text-xl font-extrabold text-emerald-500 dark:text-emerald-400">{(stats.pass_rate * 100).toFixed(1)}%</p>
                                    </div>
                                </div>
                                <div className="glass-stat p-4">
                                    <div className="relative z-10 text-center">
                                        <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Passed</p>
                                        <p className="text-xl font-extrabold text-emerald-500 dark:text-emerald-400">{stats.total_passed}</p>
                                    </div>
                                </div>
                                <div className="glass-stat p-4">
                                    <div className="relative z-10 text-center">
                                        <p className="text-[10px] text-slate-500 dark:text-gray-400 font-semibold uppercase tracking-wider">Failed</p>
                                        <p className="text-xl font-extrabold text-red-500 dark:text-red-400">{stats.total_failed}</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

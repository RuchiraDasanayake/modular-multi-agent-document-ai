"use client";

import { useState } from "react";
import { api } from "@/lib/api";
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
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">🛡️ Hallucination Guardrails</h1>
                <p className="text-slate-500 dark:text-gray-400 mt-1">
                    5-layer validation ensemble: Schema Adherence → Internal Consistency → Domain Rules → PII Leakage → Faithfulness
                </p>
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
                <div className="bg-white/80 dark:bg-gray-900/50 border border-slate-200 dark:border-gray-800 rounded-xl p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Validation Input</h2>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs text-slate-500 dark:text-gray-400 mb-1">Document Type</label>
                            <select
                                value={docType}
                                onChange={(e) => setDocType(e.target.value)}
                                className="w-full bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-white"
                            >
                                {DOC_TYPES.map((t) => (
                                    <option key={t} value={t}>{t}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs text-slate-500 dark:text-gray-400 mb-1">Vendor (optional)</label>
                            <input
                                value={vendor}
                                onChange={(e) => setVendor(e.target.value)}
                                className="w-full bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-white"
                                placeholder="e.g. ABC Suppliers"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs text-slate-500 dark:text-gray-400 mb-1">Query</label>
                        <input
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            className="w-full bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-white"
                        />
                    </div>

                    <div>
                        <label className="block text-xs text-slate-500 dark:text-gray-400 mb-1">Extracted JSON (answer_json)</label>
                        <textarea
                            value={answerJson}
                            onChange={(e) => setAnswerJson(e.target.value)}
                            rows={5}
                            className="w-full bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-white font-mono"
                        />
                    </div>

                    <div>
                        <label className="block text-xs text-slate-500 dark:text-gray-400 mb-1">Source Contexts (one per line)</label>
                        <textarea
                            value={sourceContexts}
                            onChange={(e) => setSourceContexts(e.target.value)}
                            rows={3}
                            className="w-full bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-white"
                        />
                    </div>

                    <div>
                        <label className="block text-xs text-slate-500 dark:text-gray-400 mb-1">Document ID (optional)</label>
                        <input
                            value={documentId}
                            onChange={(e) => setDocumentId(e.target.value)}
                            className="w-full bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-white"
                        />
                    </div>

                    <button
                        onClick={handleValidate}
                        disabled={loading}
                        className="w-full bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-slate-900 dark:text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-all"
                    >
                        {loading ? "Validating..." : "Run Guardrail Validation"}
                    </button>

                    {error && <p className="text-red-400 text-sm">{error}</p>}
                </div>

                {/* Results */}
                <div className="space-y-4">
                    {result && (
                        <div className="bg-white/80 dark:bg-gray-900/50 border border-slate-200 dark:border-gray-800 rounded-xl p-6 space-y-4">
                            <div className="flex items-center justify-between">
                                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Validation Result</h2>
                                <Badge pass={result.overall_passes} />
                            </div>

                            <div className="grid grid-cols-3 gap-3 text-center">
                                <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3">
                                    <p className="text-xs text-slate-500 dark:text-gray-400">Checks Run</p>
                                    <p className="text-xl font-bold text-slate-900 dark:text-white">{result.validation_results.length}</p>
                                </div>
                                <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3">
                                    <p className="text-xs text-slate-500 dark:text-gray-400">Failed</p>
                                    <p className="text-xl font-bold text-red-400">{result.metrics.num_failed_checks}</p>
                                </div>
                                <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3">
                                    <p className="text-xs text-slate-500 dark:text-gray-400">Time</p>
                                    <p className="text-xl font-bold text-slate-900 dark:text-white">{result.processing_time_ms.toFixed(0)}ms</p>
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
                        <div className="bg-white/80 dark:bg-gray-900/50 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                            <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">Session Stats</h2>
                            <div className="grid grid-cols-2 gap-3 text-center">
                                <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3">
                                    <p className="text-xs text-slate-500 dark:text-gray-400">Total Runs</p>
                                    <p className="text-xl font-bold text-slate-900 dark:text-white">{stats.total_validations}</p>
                                </div>
                                <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3">
                                    <p className="text-xs text-slate-500 dark:text-gray-400">Pass Rate</p>
                                    <p className="text-xl font-bold text-green-400">{(stats.pass_rate * 100).toFixed(1)}%</p>
                                </div>
                                <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3">
                                    <p className="text-xs text-slate-500 dark:text-gray-400">Passed</p>
                                    <p className="text-xl font-bold text-green-400">{stats.total_passed}</p>
                                </div>
                                <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3">
                                    <p className="text-xs text-slate-500 dark:text-gray-400">Failed</p>
                                    <p className="text-xl font-bold text-red-400">{stats.total_failed}</p>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

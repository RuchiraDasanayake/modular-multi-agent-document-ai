"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/toast";
import { Icon } from "@/components/icons";
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

const LABEL = "block text-xs font-semibold text-slate-700 dark:text-gray-200";
const HELP = "mt-0.5 mb-1.5 text-xs text-slate-500 dark:text-gray-400";

function Badge({ pass }: { pass: boolean }) {
    return (
        <span
            className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                pass
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300"
                    : "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
            }`}
        >
            <Icon name={pass ? "check" : "close"} className="h-3 w-3" />
            {pass ? "Pass" : "Fail"}
        </span>
    );
}

function StatTile({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "good" | "bad" }) {
    const toneClass =
        tone === "good"
            ? "text-emerald-700 dark:text-emerald-300"
            : tone === "bad"
              ? "text-rose-700 dark:text-rose-300"
              : "text-slate-900 dark:text-white";
    return (
        <div className="rounded-xl border border-slate-200 px-4 py-3 dark:border-gray-700">
            <p className="text-xs text-slate-500 dark:text-gray-400">{label}</p>
            <p className={`mt-1 text-xl font-bold tabular-nums ${toneClass}`}>{value}</p>
        </div>
    );
}

export default function GuardrailsPage() {
    const { addToast } = useToast();
    const [docType, setDocType] = useState<string>("Invoice");
    const [activeExample, setActiveExample] = useState<string>("Invoice");
    const [vendor, setVendor] = useState("");
    const [query, setQuery] = useState(EXAMPLE_PAYLOADS.Invoice.query);
    const [answerJson, setAnswerJson] = useState(EXAMPLE_PAYLOADS.Invoice.answer_json);
    const [sourceContexts, setSourceContexts] = useState(EXAMPLE_PAYLOADS.Invoice.source_contexts.join("\n"));
    const [documentId, setDocumentId] = useState(EXAMPLE_PAYLOADS.Invoice.document_id || "");
    const [result, setResult] = useState<GuardrailValidateResponse | null>(null);
    const [stats, setStats] = useState<GuardrailStats | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        api.getGuardrailStats().then(setStats).catch(() => undefined);
    }, []);

    const loadExample = (type: string) => {
        const example = EXAMPLE_PAYLOADS[type];
        if (!example) {
            return;
        }
        setActiveExample(type);
        setDocType(type);
        setQuery(example.query);
        setAnswerJson(example.answer_json);
        setSourceContexts(example.source_contexts.join("\n"));
        setDocumentId(example.document_id || "");
        setResult(null);
        setError("");
    };

    const handleValidate = async () => {
        try {
            JSON.parse(answerJson);
        } catch (parseError) {
            setError(
                `The extracted JSON is not valid JSON${parseError instanceof Error ? `: ${parseError.message}` : "."}`,
            );
            return;
        }
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
            addToast({
                type: res.overall_passes ? "success" : "warning",
                title: res.overall_passes ? "All checks passed" : "Some checks failed",
                message: `${res.validation_results.length} checks in ${res.processing_time_ms.toFixed(0)} ms`,
            });
            api.getGuardrailStats().then(setStats).catch(() => undefined);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "The checks could not run.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-7xl 3xl:max-w-[1800px] mx-auto space-y-6">
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6 animate-fade-in-up">
                <div className="absolute inset-0 bg-gradient-to-r from-emerald-500/5 to-green-500/5 dark:from-emerald-500/[0.03] dark:to-green-500/[0.03]" />
                <div className="relative">
                    <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                        <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-green-500 flex items-center justify-center shadow-lg shadow-emerald-500/20 text-white">
                            <Icon name="shield" className="h-5 w-5" />
                        </span>
                        Quality checks
                    </h1>
                    <p className="text-slate-600 dark:text-gray-300 mt-1.5 max-w-3xl text-sm">
                        Test extracted data against the Guardrails service. It checks the schema, internal consistency,
                        domain rules, personal data and faithfulness to the source text.
                    </p>
                    <p className="text-slate-500 dark:text-gray-400 mt-1 text-xs">
                        Guardrails runs as a separate service. The document pipeline and the benchmark do not call it.
                    </p>
                </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-slate-500 dark:text-gray-400">Load an example:</span>
                {Object.keys(EXAMPLE_PAYLOADS).map((type) => (
                    <button
                        key={type}
                        type="button"
                        onClick={() => loadExample(type)}
                        aria-pressed={activeExample === type}
                        className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                            activeExample === type
                                ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-300"
                                : "border-slate-200 bg-white text-slate-600 hover:bg-slate-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                        }`}
                    >
                        {type.replace(/([a-z])([A-Z])/g, "$1 $2")}
                    </button>
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <form
                    className="glass-panel rounded-2xl p-6 space-y-4 animate-fade-in-up"
                    onSubmit={(event) => {
                        event.preventDefault();
                        void handleValidate();
                    }}
                >
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white">What to check</h2>

                    <div className="grid gap-4 sm:grid-cols-2">
                        <div>
                            <label htmlFor="gr-doc-type" className={LABEL}>Document type</label>
                            <p className={HELP}>Selects the domain rules to apply.</p>
                            <select
                                id="gr-doc-type"
                                value={docType}
                                onChange={(e) => setDocType(e.target.value)}
                                className="w-full glass-input px-3 py-2.5 text-sm"
                            >
                                {DOC_TYPES.map((t) => (
                                    <option key={t} value={t}>{t.replace(/([a-z])([A-Z])/g, "$1 $2")}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label htmlFor="gr-vendor" className={LABEL}>Vendor (optional)</label>
                            <p className={HELP}>Supplier name, for vendor-specific rules.</p>
                            <input
                                id="gr-vendor"
                                value={vendor}
                                onChange={(e) => setVendor(e.target.value)}
                                className="w-full glass-input px-3 py-2.5 text-sm"
                                placeholder="e.g. ABC Suppliers"
                            />
                        </div>
                    </div>

                    <div>
                        <label htmlFor="gr-query" className={LABEL}>Instruction</label>
                        <p className={HELP}>What the model was asked to extract.</p>
                        <input
                            id="gr-query"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            className="w-full glass-input px-3 py-2.5 text-sm"
                        />
                    </div>

                    <div>
                        <label htmlFor="gr-answer" className={LABEL}>Extracted JSON</label>
                        <p className={HELP}>The model output to check.</p>
                        <textarea
                            id="gr-answer"
                            value={answerJson}
                            onChange={(e) => setAnswerJson(e.target.value)}
                            rows={5}
                            spellCheck={false}
                            className="w-full glass-input px-3 py-2.5 text-sm font-mono"
                        />
                    </div>

                    <div>
                        <label htmlFor="gr-sources" className={LABEL}>Source text</label>
                        <p className={HELP}>The passages the values should come from, one per line.</p>
                        <textarea
                            id="gr-sources"
                            value={sourceContexts}
                            onChange={(e) => setSourceContexts(e.target.value)}
                            rows={3}
                            className="w-full glass-input px-3 py-2.5 text-sm"
                        />
                    </div>

                    <div>
                        <label htmlFor="gr-doc-id" className={LABEL}>Document ID (optional)</label>
                        <p className={HELP}>Stored with the audit record.</p>
                        <input
                            id="gr-doc-id"
                            value={documentId}
                            onChange={(e) => setDocumentId(e.target.value)}
                            className="w-full glass-input px-3 py-2.5 text-sm"
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-gradient-to-r from-emerald-500 to-green-500 hover:shadow-lg hover:shadow-emerald-500/25 disabled:opacity-50 text-white px-4 py-3 rounded-xl text-sm font-bold transition-all duration-200 active:scale-[0.98] flex items-center justify-center gap-2"
                    >
                        <Icon name="shield" />
                        {loading ? "Checking..." : "Run checks"}
                    </button>

                    {error ? (
                        <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
                            {error}
                        </p>
                    ) : null}
                </form>

                <div className="space-y-4">
                    {result ? (
                        <div className="glass-panel rounded-2xl p-6 space-y-4 animate-fade-in-up">
                            <div className="flex items-center justify-between gap-3">
                                <h2 className="text-lg font-bold text-slate-900 dark:text-white">Result</h2>
                                <Badge pass={result.overall_passes} />
                            </div>

                            <div className="grid grid-cols-3 gap-3">
                                <StatTile label="Checks run" value={String(result.validation_results.length)} />
                                <StatTile
                                    label="Failed"
                                    value={String(result.metrics.num_failed_checks)}
                                    tone={result.metrics.num_failed_checks > 0 ? "bad" : "default"}
                                />
                                <StatTile label="Time" value={`${result.processing_time_ms.toFixed(0)} ms`} />
                            </div>

                            <ul className="space-y-2">
                                {result.validation_results.map((check, i) => (
                                    <li
                                        key={`${check.name}-${i}`}
                                        className={`rounded-lg border p-3 ${
                                            check.is_pass
                                                ? "border-emerald-200 bg-emerald-50/60 dark:border-emerald-500/20 dark:bg-emerald-500/5"
                                                : "border-rose-200 bg-rose-50/60 dark:border-rose-500/20 dark:bg-rose-500/5"
                                        }`}
                                    >
                                        <div className="mb-1 flex items-center justify-between gap-3">
                                            <span className="text-sm font-medium capitalize text-slate-900 dark:text-white">
                                                {check.name.replace(/_/g, " ")}
                                            </span>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs tabular-nums text-slate-500 dark:text-gray-400">
                                                    Score {check.score.toFixed(2)}
                                                </span>
                                                <Badge pass={check.is_pass} />
                                            </div>
                                        </div>
                                        <p className="text-xs text-slate-600 [overflow-wrap:anywhere] dark:text-gray-300">{check.details}</p>
                                    </li>
                                ))}
                            </ul>

                            <p className="text-xs text-slate-500 dark:text-gray-400">
                                Audit record <span className="font-mono">{result.audit_log_id}</span>
                            </p>
                        </div>
                    ) : (
                        <div className="flex min-h-[240px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 p-6 text-center dark:border-gray-700">
                            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-500 dark:bg-gray-800 dark:text-gray-400">
                                <Icon name="shield" className="h-5 w-5" />
                            </span>
                            <p className="mt-3 text-sm font-medium text-slate-900 dark:text-white">
                                {loading ? "Running checks..." : "No result yet"}
                            </p>
                            <p className="mt-1 max-w-xs text-sm text-slate-500 dark:text-gray-400">
                                Load an example or paste your own JSON and source text, then run the checks. Each check
                                reports a score and an explanation here.
                            </p>
                        </div>
                    )}

                    {stats && stats.total_validations > 0 ? (
                        <div className="glass-panel rounded-2xl p-6 animate-fade-in-up">
                            <h2 className="text-base font-bold text-slate-900 dark:text-white">Service totals</h2>
                            <p className="mt-0.5 text-xs text-slate-500 dark:text-gray-400">Kept in the service&apos;s memory, so they reset when it restarts.</p>
                            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                                <StatTile label="Runs" value={String(stats.total_validations)} />
                                <StatTile label="Pass rate" value={`${(stats.pass_rate * 100).toFixed(1)}%`} />
                                <StatTile label="Passed" value={String(stats.total_passed)} tone="good" />
                                <StatTile label="Failed" value={String(stats.total_failed)} tone={stats.total_failed > 0 ? "bad" : "default"} />
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>
        </div>
    );
}

"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Icon } from "@/components/icons";

type PolicyCheckResponse = {
    policy_id: string;
    policy_data: Record<string, unknown>;
    confidence: number;
    rabi_used: boolean;
};

const DOC_TYPES = [
    { value: "invoice", label: "Invoice" },
    { value: "receipt", label: "Receipt" },
    { value: "contract", label: "Contract" },
    { value: "form", label: "Form" },
    { value: "report", label: "Report" },
];

const FIELD =
    "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/50 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:placeholder-gray-500";

export default function PolicyCheckPage() {
    const [docType, setDocType] = useState("invoice");
    const [vendor, setVendor] = useState("");
    const [policy, setPolicy] = useState<PolicyCheckResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const handleCheckPolicy = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError("");
        try {
            const data = await api.request<PolicyCheckResponse>("/api/advice", {
                method: "POST",
                body: JSON.stringify({
                    doc_type: docType,
                    vendor: vendor || "unknown",
                }),
            });
            setPolicy(data);
        } catch (err) {
            setPolicy(null);
            setError(err instanceof Error ? `The AHMN service did not answer: ${err.message}` : "The AHMN service did not answer.");
        } finally {
            setLoading(false);
        }
    };

    const confidence = policy ? Math.max(0, Math.min(1, policy.confidence)) : 0;
    const hasSettings = policy?.policy_data && Object.keys(policy.policy_data).length > 0;

    return (
        <div className="max-w-2xl 3xl:max-w-3xl mx-auto space-y-6">
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6">
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/5 to-sky-500/5 dark:from-cyan-500/[0.03] dark:to-sky-500/[0.03]" />
                <div className="relative">
                    <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                        <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-sky-600 flex items-center justify-center shadow-lg shadow-cyan-500/20 text-white">
                            <Icon name="clipboard" className="h-5 w-5" />
                        </span>
                        Policy check
                    </h1>
                    <p className="text-slate-600 dark:text-gray-300 mt-1.5 text-sm">
                        Ask the AHMN service which extraction policy it would pick for a document type and vendor.
                    </p>
                </div>
            </div>

            <div className="glass-panel rounded-2xl p-6 space-y-5">
                <form onSubmit={handleCheckPolicy} className="space-y-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                        <div>
                            <label htmlFor="policy-doc-type" className="mb-1.5 block text-xs font-semibold text-slate-700 dark:text-gray-200">
                                Document type
                            </label>
                            <select id="policy-doc-type" value={docType} onChange={(e) => setDocType(e.target.value)} className={FIELD}>
                                {DOC_TYPES.map((type) => (
                                    <option key={type.value} value={type.value}>
                                        {type.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label htmlFor="policy-vendor" className="mb-1.5 block text-xs font-semibold text-slate-700 dark:text-gray-200">
                                Vendor (optional)
                            </label>
                            <input
                                id="policy-vendor"
                                type="text"
                                value={vendor}
                                onChange={(e) => setVendor(e.target.value)}
                                placeholder="For example acme_corp"
                                className={FIELD}
                            />
                        </div>
                    </div>
                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        {loading ? "Asking AHMN…" : "Check policy"}
                    </button>
                </form>

                {error && (
                    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
                        {error}
                    </div>
                )}

                {policy && (
                    <div className="rounded-xl border border-slate-200 p-5 dark:border-gray-700" aria-live="polite">
                        <p className="text-xs font-semibold text-slate-500 dark:text-gray-400">Recommended policy</p>
                        <p className="mt-1 font-mono text-xl font-bold text-slate-900 dark:text-white">{policy.policy_id}</p>

                        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
                            <div>
                                <dt className="text-xs font-semibold text-slate-500 dark:text-gray-400">Confidence</dt>
                                <dd className="mt-1">
                                    <span className="text-lg font-bold tabular-nums text-slate-900 dark:text-white">{(confidence * 100).toFixed(0)}%</span>
                                    <span className="mt-2 block h-2 overflow-hidden rounded bg-slate-100 dark:bg-gray-800">
                                        <span className="block h-full bg-brand-600 dark:bg-brand-400" style={{ width: `${confidence * 100}%` }} />
                                    </span>
                                </dd>
                            </div>
                            <div>
                                <dt className="text-xs font-semibold text-slate-500 dark:text-gray-400">Borrowed prior (RABI)</dt>
                                <dd className="mt-1 text-lg font-semibold text-slate-900 dark:text-white">{policy.rabi_used ? "Used" : "Not used"}</dd>
                            </div>
                        </dl>

                        {hasSettings && (
                            <details className="mt-4 border-t border-slate-200 pt-3 dark:border-gray-700">
                                <summary className="cursor-pointer text-xs font-semibold text-slate-600 hover:text-slate-900 dark:text-gray-300 dark:hover:text-white">
                                    Policy settings
                                </summary>
                                <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-700 dark:bg-gray-900/60 dark:text-gray-300">
                                    {JSON.stringify(policy.policy_data, null, 2)}
                                </pre>
                            </details>
                        )}
                    </div>
                )}
            </div>

            <div className="glass-panel rounded-2xl p-6">
                <h2 className="text-base font-semibold text-slate-900 dark:text-white mb-2">How it works</h2>
                <div className="text-sm text-slate-600 dark:text-gray-300 space-y-2">
                    <p>
                        AHMN looks up the stored policies closest to this document type and vendor and picks one with
                        Thompson sampling over their Beta posteriors. The draw is seeded from the request, so the same
                        question gets the same answer until the stored evidence changes.
                    </p>
                    <p>
                        When no stored context is close enough, it borrows a prior from the nearest neighbours (RABI)
                        instead of starting flat.
                    </p>
                    <p className="text-xs text-slate-500 dark:text-gray-400">
                        This asks the separate AHMN service. The document pipeline and the benchmark use their own
                        in-process advisor, which does not use RABI.
                    </p>
                </div>
                <Link
                    href="/dashboard/architecture"
                    className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline dark:text-brand-300"
                >
                    How the AHMN service learns
                    <Icon name="arrowRight" className="h-3.5 w-3.5" />
                </Link>
            </div>
        </div>
    );
}

"use client";

import { useState } from "react";
import { api } from "@/lib/api";

type PolicyCheckResponse = {
    policy_id: string;
    policy_data: Record<string, unknown>;
    confidence: number;
    rabi_used: boolean;
};

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
            setError(err instanceof Error ? err.message : "Unknown error");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-2xl 3xl:max-w-3xl mx-auto space-y-8">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Policy Check</h1>
                <p className="text-slate-500 dark:text-gray-500 mt-2">Check which policy AHMN recommends for your document</p>
            </div>

            {/* Policy Check Form */}
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6 space-y-4">
                <form onSubmit={handleCheckPolicy} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-gray-300 mb-2">Document Type</label>
                        <select
                            value={docType}
                            onChange={(e) => setDocType(e.target.value)}
                            className="w-full px-3 py-2 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                            <option value="invoice">Invoice</option>
                            <option value="receipt">Receipt</option>
                            <option value="contract">Contract</option>
                            <option value="form">Form</option>
                            <option value="report">Report</option>
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-600 dark:text-gray-300 mb-2">Vendor Name (optional)</label>
                        <input
                            type="text"
                            value={vendor}
                            onChange={(e) => setVendor(e.target.value)}
                            placeholder="e.g., acme_corp"
                            className="w-full px-3 py-2 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 dark:disabled:bg-gray-600 text-slate-900 dark:text-white rounded font-medium transition"
                    >
                        {loading ? "Checking..." : "Check Policy"}
                    </button>
                </form>

                {error && <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded text-red-600 dark:text-red-300 text-sm">{error}</div>}

                {policy && (
                    <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded space-y-3">
                        <div>
                            <p className="text-xs text-blue-600 dark:text-blue-400 uppercase font-semibold">Recommended Policy</p>
                            <p className="text-2xl font-bold text-blue-900 dark:text-blue-100 mt-1">{policy.policy_id}</p>
                        </div>

                        <div className="grid grid-cols-2 gap-3 text-sm">
                            <div>
                                <p className="text-blue-600 dark:text-blue-400 font-medium mb-1">Confidence</p>
                                <div className="flex items-baseline gap-2">
                                    <span className="text-xl font-bold text-blue-900 dark:text-blue-100">{(policy.confidence * 100).toFixed(0)}%</span>
                                </div>
                                <div className="mt-2 h-2 bg-blue-200 dark:bg-blue-800 rounded overflow-hidden">
                                    <div 
                                        className="h-full bg-blue-600 dark:bg-blue-400"
                                        style={{ width: `${policy.confidence * 100}%` }}
                                    />
                                </div>
                            </div>
                            <div>
                                <p className="text-blue-600 dark:text-blue-400 font-medium mb-1">Smart Prior</p>
                                <p className="text-lg font-semibold text-blue-900 dark:text-blue-100">
                                    {policy.rabi_used ? "✓ Enabled" : "—"}
                                </p>
                            </div>
                        </div>

                        {policy.policy_data && (
                            <div className="pt-3 border-t border-blue-200 dark:border-blue-700 text-xs text-slate-600 dark:text-gray-400">
                                <p className="font-mono break-all">{JSON.stringify(policy.policy_data)}</p>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Info Section */}
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6">
                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">How It Works</h3>
                <div className="text-sm text-slate-600 dark:text-gray-400 space-y-2">
                    <p>Select a document type and optional vendor name, then AHMN will recommend the best policy for processing that document based on:</p>
                    <ul className="list-disc list-inside space-y-1 ml-2">
                        <li>Historical learning (LTM) from similar documents</li>
                        <li>RABI smart prior transfer if available (faster cold-start)</li>
                        <li>Thompson Sampling confidence scores</li>
                    </ul>
                </div>
            </div>
        </div>
    );
}

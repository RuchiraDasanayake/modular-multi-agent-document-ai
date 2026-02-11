"use client";

import { useState } from "react";
import { getToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type AdviceResponse = {
    advice_id: string;
    policy_id: string;
    policy_data: Record<string, unknown>;
    confidence: number;
    rabi_used: boolean;
};

type LogRequest = {
    advice_id: string;
    policy_id_used: string;
    metrics: {
        f1_score: number;
        cost: number;
        processing_time_ms: number;
        success: boolean;
    };
};

async function apiRequest<T>(
    method: string,
    path: string,
    body?: unknown
): Promise<T> {
    const token = getToken();
    const headers: Record<string, string> = {
        "Content-Type": "application/json",
    };
    if (token) headers.Authorization = `Bearer ${token}`;

    const fetchOptions: RequestInit = {
        method,
        headers,
    };
    if (body) fetchOptions.body = JSON.stringify(body);

    const response = await fetch(`${API_BASE}${path}`, fetchOptions);

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || `API Error ${response.status}`);
    }

    return response.json();
}

export default function SubmitDataPage() {
    // Step 1: Get Advice
    const [docType, setDocType] = useState("invoice");
    const [vendor, setVendor] = useState("");
    const [advice, setAdvice] = useState<AdviceResponse | null>(null);
    const [adviceLoading, setAdviceLoading] = useState(false);
    const [adviceError, setAdviceError] = useState("");

    // Step 2: Log Outcome
    const [f1Score, setF1Score] = useState(0.85);
    const [cost, setCost] = useState(10.5);
    const [processingTime, setProcessingTime] = useState(250);
    const [success, setSuccess] = useState(true);
    const [humanCorrected, setHumanCorrected] = useState(false);
    const [logLoading, setLogLoading] = useState(false);
    const [logError, setLogError] = useState("");
    const [logSuccess, setLogSuccess] = useState(false);

    const handleGetAdvice = async (e: React.FormEvent) => {
        e.preventDefault();
        setAdviceLoading(true);
        setAdviceError("");

        try {
            const data = await apiRequest<AdviceResponse>("POST", "/api/advice", {
                doc_type: docType,
                vendor: vendor || "unknown",
            });
            setAdvice(data);
            setLogSuccess(false);
        } catch (err) {
            setAdviceError(err instanceof Error ? err.message : "Unknown error");
        } finally {
            setAdviceLoading(false);
        }
    };

    const handleLogOutcome = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!advice) {
            setLogError("Please get advice first");
            return;
        }

        setLogLoading(true);
        setLogError("");
        setLogSuccess(false);

        try {
            await apiRequest("POST", "/api/advice/log", {
                advice_id: advice.advice_id,
                policy_id_used: advice.policy_id,
                metrics: {
                    f1_score: parseFloat(f1Score.toString()),
                    cost: parseFloat(cost.toString()),
                    processing_time_ms: parseInt(processingTime.toString()),
                    success: success,
                },
            });

            setLogSuccess(true);
            // Reset form
            setAdvice(null);
            setVendor("");
            setF1Score(0.85);
            setCost(10.5);
            setProcessingTime(250);
            setSuccess(true);
            setHumanCorrected(false);
        } catch (err) {
            setLogError(err instanceof Error ? err.message : "Unknown error");
        } finally {
            setLogLoading(false);
        }
    };

    const handleFeedback = async () => {
        if (!advice) return;

        try {
            await apiRequest("POST", "/api/advice/feedback", {
                advice_id: advice.advice_id,
                human_corrected: humanCorrected,
            });

            setHumanCorrected(!humanCorrected);
        } catch (err) {
            console.error("Feedback error:", err);
        }
    };

    return (
        <div className="max-w-4xl mx-auto space-y-8">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold text-white">Submit Data</h1>
                <p className="text-gray-500 mt-2">Add document processing outcomes to improve the system</p>
            </div>

            <div className="grid gap-8 md:grid-cols-2">
                {/* Step 1: Get Advice */}
                <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 space-y-4">
                    <div className="flex items-center space-x-3">
                        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-500 text-white font-bold">1</div>
                        <h2 className="text-lg font-semibold text-white">Get Advice</h2>
                    </div>

                    <form onSubmit={handleGetAdvice} className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-300 mb-2">Document Type</label>
                            <select
                                value={docType}
                                onChange={(e) => setDocType(e.target.value)}
                                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            >
                                <option value="invoice">Invoice</option>
                                <option value="receipt">Receipt</option>
                                <option value="contract">Contract</option>
                                <option value="form">Form</option>
                                <option value="report">Report</option>
                            </select>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-300 mb-2">Vendor Name</label>
                            <input
                                type="text"
                                value={vendor}
                                onChange={(e) => setVendor(e.target.value)}
                                placeholder="e.g., acme_corp"
                                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>

                        <button
                            type="submit"
                            disabled={adviceLoading}
                            className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white rounded font-medium transition"
                        >
                            {adviceLoading ? "Loading..." : "Get Policy Advice"}
                        </button>
                    </form>

                    {adviceError && <div className="p-3 bg-red-900 border border-red-700 rounded text-red-200 text-sm">{adviceError}</div>}

                    {advice && (
                        <div className="p-4 bg-slate-700 rounded border border-slate-600 space-y-2">
                            <div>
                                <p className="text-xs text-gray-400 uppercase">Policy Recommended</p>
                                <p className="text-white font-semibold">{advice.policy_id}</p>
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                                <div>
                                    <p className="text-gray-400">Confidence</p>
                                    <p className="text-white font-medium">{(advice.confidence * 100).toFixed(1)}%</p>
                                </div>
                                <div>
                                    <p className="text-gray-400">RABI Used</p>
                                    <p className="text-white font-medium">{advice.rabi_used ? "Yes" : "No"}</p>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Step 2: Log Outcome */}
                <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 space-y-4">
                    <div className="flex items-center space-x-3">
                        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-green-500 text-white font-bold">2</div>
                        <h2 className="text-lg font-semibold text-white">Log Outcome</h2>
                    </div>

                    <form onSubmit={handleLogOutcome} className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-300 mb-2">F1 Score</label>
                            <div className="flex gap-2">
                                <input
                                    type="range"
                                    min="0"
                                    max="1"
                                    step="0.01"
                                    value={f1Score}
                                    onChange={(e) => setF1Score(parseFloat(e.target.value))}
                                    className="flex-1"
                                />
                                <input
                                    type="number"
                                    min="0"
                                    max="1"
                                    step="0.01"
                                    value={f1Score.toFixed(2)}
                                    onChange={(e) => setF1Score(parseFloat(e.target.value))}
                                    className="w-16 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                                />
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-300 mb-2">Cost ($)</label>
                            <input
                                type="number"
                                min="0"
                                step="0.1"
                                value={cost.toFixed(2)}
                                onChange={(e) => setCost(parseFloat(e.target.value))}
                                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-green-500"
                            />
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-300 mb-2">Processing Time (ms)</label>
                            <input
                                type="number"
                                min="0"
                                step="10"
                                value={processingTime}
                                onChange={(e) => setProcessingTime(parseInt(e.target.value))}
                                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-green-500"
                            />
                        </div>

                        <div className="flex items-center space-x-2">
                            <input
                                type="checkbox"
                                id="success"
                                checked={success}
                                onChange={(e) => setSuccess(e.target.checked)}
                                className="w-4 h-4 rounded border-gray-600 text-green-600"
                            />
                            <label htmlFor="success" className="text-sm text-gray-300">
                                Processing successful
                            </label>
                        </div>

                        <div className="flex items-center space-x-2">
                            <input
                                type="checkbox"
                                id="humanCorrected"
                                checked={humanCorrected}
                                onChange={(e) => setHumanCorrected(e.target.checked)}
                                className="w-4 h-4 rounded border-gray-600 text-blue-600"
                            />
                            <label htmlFor="humanCorrected" className="text-sm text-gray-300">
                                Human correction needed
                            </label>
                        </div>

                        <button
                            type="submit"
                            disabled={logLoading || !advice}
                            className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white rounded font-medium transition"
                        >
                            {logLoading ? "Logging..." : "Log Outcome"}
                        </button>
                    </form>

                    {logError && <div className="p-3 bg-red-900 border border-red-700 rounded text-red-200 text-sm">{logError}</div>}

                    {logSuccess && (
                        <div className="p-3 bg-green-900 border border-green-700 rounded text-green-200 text-sm flex items-center gap-2">
                            <span>✓</span>
                            <span>Outcome logged successfully! Data saved to database.</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Info Section */}
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 space-y-4">
                <h3 className="text-lg font-semibold text-white">How It Works</h3>
                <div className="grid md:grid-cols-3 gap-4 text-sm text-gray-300">
                    <div>
                        <p className="text-white font-medium mb-1">📋 Step 1</p>
                        <p>Select document type and vendor, then get a policy recommendation from the system.</p>
                    </div>
                    <div>
                        <p className="text-white font-medium mb-1">✅ Step 2</p>
                        <p>After processing, log the actual outcome metrics (F1 & accuracy) from your pipeline.</p>
                    </div>
                    <div>
                        <p className="text-white font-medium mb-1">🧠 Step 3</p>
                        <p>System learns from outcomes via DAAF drift detection and updates Long-Term Memory.</p>
                    </div>
                </div>
            </div>
        </div>
    );
}

"use client";

import { useState, useRef } from "react";
import { getToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ExtractionField = {
    name: string;
    description: string;
};

type DocRecord = {
    doc_id: string;
    filename: string;
    category: string;
    status: string;
    extracted_text?: string;
    entities?: Record<string, unknown>;
};

type RunResult = {
    run_id: string;
    run_dir: string;
    metrics: Record<string, number>;
    docs: DocRecord[];
    entities: Record<string, unknown>[];
    warnings: string[];
};

export default function IDPOPage() {
    const [files, setFiles] = useState<File[]>([]);
    const [fields, setFields] = useState<ExtractionField[]>([]);
    const [newFieldName, setNewFieldName] = useState("");
    const [newFieldDesc, setNewFieldDesc] = useState("");
    const [configPath, setConfigPath] = useState("configs/sample_config.json");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [result, setResult] = useState<RunResult | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) {
            setFiles(Array.from(e.target.files));
        }
    };

    const addField = () => {
        if (newFieldName.trim()) {
            setFields([...fields, { name: newFieldName.trim(), description: newFieldDesc.trim() }]);
            setNewFieldName("");
            setNewFieldDesc("");
        }
    };

    const removeField = (index: number) => {
        setFields(fields.filter((_, i) => i !== index));
    };

    const handleDownload = async (url: string, filename: string) => {
        try {
            const token = getToken();
            const response = await fetch(url, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (!response.ok) {
                throw new Error(`Download failed: ${response.status}`);
            }
            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(downloadUrl);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Download failed");
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (files.length === 0) {
            setError("Please select at least one file");
            return;
        }

        setLoading(true);
        setError("");
        setResult(null);

        const formData = new FormData();
        files.forEach((file) => formData.append("files", file));
        formData.append("fields", JSON.stringify(fields));
        formData.append("config_path", configPath);

        try {
            const token = getToken();
            const response = await fetch(`${API_BASE}/api/idpo/run`, {
                method: "POST",
                headers: token ? { Authorization: `Bearer ${token}` } : {},
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({ error: response.statusText }));
                throw new Error(err.error || err.detail || `Error ${response.status}`);
            }

            const data: RunResult = await response.json();
            setResult(data);
            setFiles([]);
            if (fileInputRef.current) fileInputRef.current.value = "";
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unknown error");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-6xl mx-auto space-y-8">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Document Processing</h1>
                <p className="text-slate-500 dark:text-gray-500 mt-2">
                    Upload documents for intelligent processing, extraction, and analysis using IDPO
                </p>
            </div>

            <div className="grid gap-8 lg:grid-cols-2">
                {/* Upload Form */}
                <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6 space-y-6">
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                        <span>Upload Documents</span>
                    </h2>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        {/* File Upload */}
                        <div>
                            <label className="block text-sm font-medium text-slate-600 dark:text-gray-300 mb-2">
                                Select Files
                            </label>
                            <input
                                ref={fileInputRef}
                                type="file"
                                multiple
                                onChange={handleFileChange}
                                className="w-full px-3 py-2 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded text-slate-900 dark:text-white file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-blue-50 dark:file:bg-blue-900 file:text-blue-700 dark:file:text-blue-300 hover:file:bg-blue-100 dark:hover:file:bg-blue-800"
                            />
                            {files.length > 0 && (
                                <p className="mt-2 text-sm text-slate-500 dark:text-gray-400">
                                    {files.length} file(s) selected: {files.map(f => f.name).join(", ")}
                                </p>
                            )}
                        </div>

                        {/* Config Path */}
                        <div>
                            <label className="block text-sm font-medium text-slate-600 dark:text-gray-300 mb-2">
                                Config Path
                            </label>
                            <input
                                type="text"
                                value={configPath}
                                onChange={(e) => setConfigPath(e.target.value)}
                                className="w-full px-3 py-2 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>

                        {/* Custom Extraction Fields */}
                        <div>
                            <label className="block text-sm font-medium text-slate-600 dark:text-gray-300 mb-2">
                                Custom Extraction Fields (Optional)
                            </label>
                            <div className="flex gap-2 mb-2">
                                <input
                                    type="text"
                                    placeholder="Field name"
                                    value={newFieldName}
                                    onChange={(e) => setNewFieldName(e.target.value)}
                                    className="flex-1 px-3 py-2 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                />
                                <input
                                    type="text"
                                    placeholder="Description"
                                    value={newFieldDesc}
                                    onChange={(e) => setNewFieldDesc(e.target.value)}
                                    className="flex-1 px-3 py-2 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                />
                                <button
                                    type="button"
                                    onClick={addField}
                                    className="px-4 py-2 bg-slate-200 dark:bg-slate-600 hover:bg-slate-300 dark:hover:bg-slate-500 rounded text-slate-700 dark:text-white text-sm font-medium transition"
                                >
                                    Add
                                </button>
                            </div>
                            {fields.length > 0 && (
                                <div className="space-y-1">
                                    {fields.map((field, i) => (
                                        <div key={i} className="flex items-center gap-2 px-3 py-2 bg-slate-50 dark:bg-slate-700 rounded text-sm">
                                            <span className="font-medium text-slate-900 dark:text-white">{field.name}</span>
                                            {field.description && (
                                                <span className="text-slate-500 dark:text-gray-400">- {field.description}</span>
                                            )}
                                            <button
                                                type="button"
                                                onClick={() => removeField(i)}
                                                className="ml-auto text-red-500 hover:text-red-700"
                                            >
                                                x
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <button
                            type="submit"
                            disabled={loading || files.length === 0}
                            className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 dark:disabled:bg-gray-600 text-white rounded font-medium transition flex items-center justify-center gap-2"
                        >
                            {loading ? (
                                <>
                                    <span className="animate-spin">...</span>
                                    Processing...
                                </>
                            ) : (
                                <>
                                    Process Documents
                                </>
                            )}
                        </button>
                    </form>

                    {error && (
                        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded text-red-600 dark:text-red-300 text-sm">
                            {error}
                        </div>
                    )}
                </div>

                {/* Results Panel */}
                <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Results</h2>

                    {!result ? (
                        <div className="text-center py-12 text-slate-400 dark:text-gray-500">
                            <p>Upload and process documents to see results here</p>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {/* Run Info */}
                            <div className="p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700 rounded">
                                <p className="text-green-700 dark:text-green-300 font-medium">Processing Complete</p>
                                <p className="text-sm text-green-600 dark:text-green-400 mt-1">
                                    Run ID: {result.run_id}
                                </p>
                            </div>

                            {/* Warnings */}
                            {result.warnings && result.warnings.length > 0 && (
                                <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700 rounded">
                                    <p className="text-yellow-700 dark:text-yellow-300 font-medium mb-2">Warnings</p>
                                    <ul className="text-sm text-yellow-600 dark:text-yellow-400 list-disc list-inside">
                                        {result.warnings.map((w, i) => (
                                            <li key={i}>{w}</li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            {/* Metrics */}
                            {result.metrics && Object.keys(result.metrics).length > 0 && (
                                <div>
                                    <p className="text-sm font-medium text-slate-600 dark:text-gray-300 mb-2">Metrics</p>
                                    <div className="grid grid-cols-2 gap-2">
                                        {Object.entries(result.metrics).map(([key, value]) => (
                                            <div key={key} className="p-2 bg-slate-50 dark:bg-slate-700 rounded text-sm">
                                                <span className="text-slate-500 dark:text-gray-400">{key}:</span>{" "}
                                                <span className="font-medium text-slate-900 dark:text-white">
                                                    {typeof value === "number" ? value.toFixed(3) : String(value)}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Documents */}
                            {result.docs && result.docs.length > 0 && (
                                <div>
                                    <p className="text-sm font-medium text-slate-600 dark:text-gray-300 mb-2">
                                        Processed Documents ({result.docs.length})
                                    </p>
                                    <div className="space-y-2 max-h-64 overflow-y-auto">
                                        {result.docs.map((doc, i) => (
                                            <div key={i} className="p-3 bg-slate-50 dark:bg-slate-700 rounded border border-slate-200 dark:border-slate-600">
                                                <div className="flex items-center justify-between">
                                                    <span className="font-medium text-slate-900 dark:text-white text-sm">
                                                        {doc.filename || doc.doc_id}
                                                    </span>
                                                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                                        doc.status === "success"
                                                            ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                                                            : "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300"
                                                    }`}>
                                                        {doc.status || "processed"}
                                                    </span>
                                                </div>
                                                {doc.category && (
                                                    <p className="text-xs text-slate-500 dark:text-gray-400 mt-1">
                                                        Category: {doc.category}
                                                    </p>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Download Links */}
                            <div className="flex gap-2 pt-4 border-t border-slate-200 dark:border-slate-700">
                                <button
                                    onClick={() => handleDownload(
                                        `${API_BASE}/api/idpo/runs/${result.run_id}/docs.xlsx`,
                                        "docs.xlsx"
                                    )}
                                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white text-sm font-medium transition"
                                >
                                    Download Results
                                </button>
                                {result.entities && result.entities.length > 0 && (
                                    <button
                                        onClick={() => handleDownload(
                                            `${API_BASE}/api/idpo/runs/${result.run_id}/entities.xlsx`,
                                            "entities.xlsx"
                                        )}
                                        className="px-4 py-2 bg-slate-200 dark:bg-slate-600 hover:bg-slate-300 dark:hover:bg-slate-500 rounded text-slate-700 dark:text-white text-sm font-medium transition"
                                    >
                                        Download Entities
                                    </button>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* How It Works */}
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-6">
                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">How IDPO Works</h3>
                <div className="grid md:grid-cols-4 gap-4 text-sm text-slate-600 dark:text-gray-300">
                    <div>
                        <p className="text-slate-900 dark:text-white font-medium mb-1">1. Intake</p>
                        <p>Documents are ingested and preprocessed (OCR, text extraction)</p>
                    </div>
                    <div>
                        <p className="text-slate-900 dark:text-white font-medium mb-1">2. Categorization</p>
                        <p>Multi-agent pipeline categorizes and chunks documents</p>
                    </div>
                    <div>
                        <p className="text-slate-900 dark:text-white font-medium mb-1">3. Extraction</p>
                        <p>LLM-based agents extract structured data and entities</p>
                    </div>
                    <div>
                        <p className="text-slate-900 dark:text-white font-medium mb-1">4. Export</p>
                        <p>Results exported with full provenance audit trail</p>
                    </div>
                </div>
            </div>
        </div>
    );
}

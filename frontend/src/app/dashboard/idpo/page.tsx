"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { api } from "@/lib/api";
import type {
    IDPOExtractionField,
    IDPORunResult,
    IDPODocRecord,
    IDPOEntityDetail,
    PipelineIntegration,
    GuardrailDocResult,
    XAIDocExplanation,
} from "@/types";

export default function IDPOPage() {
    /* ── State ── */
    const [files, setFiles] = useState<File[]>([]);
    const [fields, setFields] = useState<IDPOExtractionField[]>([]);
    const [newFieldName, setNewFieldName] = useState("");
    const [newFieldDesc, setNewFieldDesc] = useState("");
    const [configPath, setConfigPath] = useState("configs/config.json");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [result, setResult] = useState<IDPORunResult | null>(null);
    const [activeTab, setActiveTab] = useState<"documents" | "entities" | "fulltext" | "integration">("documents");
    const [expandedDoc, setExpandedDoc] = useState<string | null>(null);
    const [dragActive, setDragActive] = useState(false);
    const [showConfig, setShowConfig] = useState(false);
    const [elapsedSec, setElapsedSec] = useState(0);
    const elapsedRef = useRef<NodeJS.Timeout | null>(null);
    const [integrationTab, setIntegrationTab] = useState<"advice" | "guardrails" | "xai" | "feedback">("advice");
    const [enableGuardrails, setEnableGuardrails] = useState(true);
    const [enableXAI, setEnableXAI] = useState(false);
    const [enableAHMN, setEnableAHMN] = useState(true);
    const [entitySearch, setEntitySearch] = useState("");
    const [entityConfidenceFilter, setEntityConfidenceFilter] = useState<"all" | "high" | "medium" | "low">("all");
    const [entityPage, setEntityPage] = useState(0);
    const ENTITIES_PER_PAGE = 15;
    const fileInputRef = useRef<HTMLInputElement>(null);
    // Per-document progress tracking for multi-doc uploads
    const [docProgress, setDocProgress] = useState<{ name: string; status: "queued" | "processing" | "done" | "error"; elapsed?: number }[]>([]);
    const progressTimerRef = useRef<NodeJS.Timeout | null>(null);
    const progressStartRef = useRef<number>(0);

    // Persist toggle preferences
    useEffect(() => {
        try {
            const saved = localStorage.getItem("idpo_toggles");
            if (saved) {
                const parsed = JSON.parse(saved);
                if (typeof parsed.guardrails === "boolean") setEnableGuardrails(parsed.guardrails);
                if (typeof parsed.xai === "boolean") setEnableXAI(parsed.xai);
                if (typeof parsed.ahmn === "boolean") setEnableAHMN(parsed.ahmn);
            }
        } catch { }
    }, []);

    useEffect(() => {
        try { localStorage.setItem("idpo_toggles", JSON.stringify({ guardrails: enableGuardrails, xai: enableXAI, ahmn: enableAHMN })); } catch { }
    }, [enableGuardrails, enableXAI, enableAHMN]);

    /* ── Drag & drop handlers ── */
    const handleDrag = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
        else if (e.type === "dragleave") setDragActive(false);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files?.length) {
            setFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
        }
    }, []);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
    };

    const removeFile = (index: number) => setFiles(files.filter((_, i) => i !== index));

    /* ── Field management ── */
    const addField = () => {
        if (newFieldName.trim()) {
            setFields([...fields, { name: newFieldName.trim(), description: newFieldDesc.trim() }]);
            setNewFieldName("");
            setNewFieldDesc("");
        }
    };

    const removeField = (index: number) => setFields(fields.filter((_, i) => i !== index));

    const handleFieldKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter") { e.preventDefault(); addField(); }
    };

    /* ── Elapsed timer ── */
    useEffect(() => {
        if (!loading) {
            if (elapsedRef.current) clearInterval(elapsedRef.current);
            return;
        }
        setElapsedSec(0);
        elapsedRef.current = setInterval(() => setElapsedSec((s) => s + 1), 1000);
        return () => { if (elapsedRef.current) clearInterval(elapsedRef.current); };
    }, [loading]);

    /* ── Per-document progress simulator ── */
    useEffect(() => {
        if (!loading || files.length === 0) {
            if (progressTimerRef.current) clearInterval(progressTimerRef.current);
            return;
        }
        progressStartRef.current = Date.now();
        setDocProgress(files.map((f) => ({ name: f.name, status: "queued" as const })));
        let currentDoc = 0;
        // Cycle through docs with realistic timing
        const baseMs = enableGuardrails ? 3500 : enableXAI ? 2000 : 1800;
        const tickMs = 500;
        const interval = setInterval(() => {
            const elapsed = Date.now() - progressStartRef.current;
            setDocProgress((prev) => {
                const next = [...prev];
                // Mark documents as processing/done based on elapsed time
                for (let i = 0; i < next.length; i++) {
                    const docStartTime = i * baseMs;
                    const docEndTime = (i + 1) * baseMs;
                    if (elapsed >= docEndTime) {
                        if (next[i].status !== "done") next[i] = { ...next[i], status: "done", elapsed: docEndTime };
                    } else if (elapsed >= docStartTime) {
                        if (next[i].status === "queued") next[i] = { ...next[i], status: "processing", elapsed: elapsed - docStartTime };
                        else next[i] = { ...next[i], elapsed: elapsed - docStartTime };
                    }
                }
                return next;
            });
        }, tickMs);
        progressTimerRef.current = interval;
        return () => clearInterval(interval);
    }, [loading, files.length, enableGuardrails, enableXAI]);

    /* ── Download helper ── */
    const handleDownload = async (file: "docs.xlsx" | "entities.xlsx" | "run.xlsx", filename: string) => {
        if (!result) return;
        try {
            const blob = await api.downloadIDPOFile(result.run_id, file);
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Download failed");
        }
    };

    /* ── Submit handler ── */
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (files.length === 0) { setError("Please select at least one file"); return; }

        // Client-side validation
        const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
        const SUPPORTED_EXTS = [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".txt", ".json"];
        for (const file of files) {
            if (file.size > MAX_FILE_SIZE) {
                setError(`File '${file.name}' exceeds 50MB limit (${(file.size / 1024 / 1024).toFixed(1)}MB)`);
                return;
            }
            const ext = "." + (file.name.split(".").pop()?.toLowerCase() || "");
            if (!SUPPORTED_EXTS.includes(ext)) {
                setError(`Unsupported file type '${ext}'. Supported: ${SUPPORTED_EXTS.join(", ")}`);
                return;
            }
        }

        setLoading(true);
        setError("");
        setResult(null);


        try {
            const data = await api.runIDPO(files, fields, configPath, { enableGuardrails, enableXAI, enableAHMN });

            // Mark all doc progress as done
            setDocProgress((prev) => prev.map((d) => ({ ...d, status: "done" as const })));
            setResult(data);
            setFiles([]);
            if (fileInputRef.current) fileInputRef.current.value = "";
            // Default to Documents tab to show extraction results first
            setActiveTab("documents");
            // Auto-expand the first document so results are immediately visible
            if (data.docs?.length > 0) {
                setExpandedDoc(data.docs[0].doc_id);
            }

            // Save extracted document texts to sessionStorage for XAI page
            try {
                const extractedDocs = (data.docs || [])
                    .filter((d: { extracted_text?: string }) => d.extracted_text)
                    .map((d: { doc_id: string; filename?: string; extracted_text?: string }) => ({
                        id: d.doc_id,
                        filename: d.filename || d.doc_id,
                        text: d.extracted_text,
                    }));
                if (extractedDocs.length > 0) {
                    sessionStorage.setItem("idpo_extracted_docs", JSON.stringify(extractedDocs));
                }
            } catch {
                // sessionStorage may be full or unavailable
            }

            // Show partial failure warnings
            if (data.partial_failures?.length > 0) {
                const failedFiles = data.partial_failures.map((f: { file: string; error: string }) => f.file).join(", ");
                setError(`${data.partial_failures.length} file(s) failed processing: ${failedFiles}. Successfully processed ${data.docs.length} document(s).`);
            }
        } catch (err) {

            setDocProgress((prev) => prev.map((d) => d.status === "processing" || d.status === "queued" ? { ...d, status: "error" as const } : d));
            let errorMessage = "Unknown error";
            if (err instanceof Error) {
                if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
                    errorMessage = "Network error — check that all backend services are running";
                } else if (err.message.includes("502")) {
                    errorMessage = "IDPO service is unavailable — make sure the extraction service is running";
                } else if (err.message.includes("504") || err.message.includes("timed out")) {
                    errorMessage = "Processing timed out — try with fewer or smaller documents";
                } else if (err.message.includes("413")) {
                    errorMessage = "File too large — reduce file size and try again";
                } else {
                    errorMessage = err.message;
                }
            }
            setError(errorMessage);
        } finally {
            setLoading(false);
            if (progressTimerRef.current) clearInterval(progressTimerRef.current);
        }
    };

    /* ── Helpers ── */
    const fileIcon = (name: string) => {
        const ext = name.split(".").pop()?.toLowerCase();
        if (ext === "pdf") return "📄";
        if (["png", "jpg", "jpeg", "tiff", "bmp"].includes(ext || "")) return "🖼️";
        if (ext === "json") return "📋";
        return "📃";
    };

    const integration = result?.pipeline_integration;

    return (
        <div className="max-w-7xl 3xl:max-w-[1800px] mx-auto space-y-5">
            {/* ── Header ── */}
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6">
                <div className="absolute inset-0 bg-gradient-to-r from-brand-500/5 to-cyan-500/5 dark:from-brand-500/[0.03] dark:to-cyan-500/[0.03]" />
                <div className="relative flex items-center justify-between flex-wrap gap-4">
                    <div>
                        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-400 to-cyan-500 flex items-center justify-center shadow-lg shadow-brand-500/20">
                                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                                </svg>
                            </div>
                            Document Extraction
                        </h1>
                        <p className="text-slate-500 dark:text-gray-400 mt-1.5 text-sm">
                            Full-cycle AI pipeline: AHMN advice → 13-agent extraction → guardrails → XAI → learning
                        </p>
                    </div>
                    <div className="flex items-center gap-3">
                        {result && (
                            <span className="px-3 py-1.5 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-300 rounded-full text-xs font-medium">
                                Run: {result.run_id.slice(0, 8)}...
                            </span>
                        )}
                        {integration && <CycleStatusBadge integration={integration} />}
                    </div>
                </div>
            </div>

            {/* ── Processing Status Bar — Creative Document Animation ── */}
            {loading && (
                <div className="glass-panel rounded-2xl p-6 overflow-hidden relative" role="status" aria-label="Processing documents">
                    {/* Animated background */}
                    <div className="absolute inset-0 bg-gradient-to-r from-brand-500/5 via-cyan-500/5 to-violet-500/5 dark:from-brand-500/[0.03] dark:via-cyan-500/[0.03] dark:to-violet-500/[0.03]" />
                    <div className="absolute inset-0 overflow-hidden">
                        <div className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/10 to-transparent" style={{ animation: "shimmer 2s ease-in-out infinite" }} />
                    </div>
                    <style jsx>{`
                        @keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(400%); } }
                        @keyframes docFloat { 0%,100% { transform: translateY(0) rotate(0deg); } 25% { transform: translateY(-8px) rotate(2deg); } 50% { transform: translateY(-4px) rotate(0deg); } 75% { transform: translateY(-12px) rotate(-2deg); } }
                        @keyframes scanLine { 0% { top: 10%; opacity: 1; } 100% { top: 85%; opacity: 0.3; } }
                        @keyframes gearSpin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                        @keyframes pipelineStep { 0% { opacity: 0.3; transform: scale(0.95); } 50% { opacity: 1; transform: scale(1.05); } 100% { opacity: 0.3; transform: scale(0.95); } }
                        @keyframes gradientMove { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
                    `}</style>
                    <div className="relative flex items-center gap-6">
                        {/* Animated floating document with scan line */}
                        <div className="flex-shrink-0 relative" style={{ animation: "docFloat 3s ease-in-out infinite" }}>
                            <div className="w-16 h-20 rounded-lg bg-white dark:bg-gray-800 border-2 border-brand-300 dark:border-brand-500/40 shadow-xl shadow-brand-500/20 relative overflow-hidden">
                                {/* Document lines */}
                                <div className="absolute inset-x-3 top-3 space-y-1.5">
                                    <div className="h-1 bg-slate-200 dark:bg-gray-600 rounded-full w-8" />
                                    <div className="h-1 bg-slate-200 dark:bg-gray-600 rounded-full w-10" />
                                    <div className="h-1 bg-slate-200 dark:bg-gray-600 rounded-full w-6" />
                                    <div className="h-1 bg-slate-200 dark:bg-gray-600 rounded-full w-9" />
                                    <div className="h-1 bg-slate-200 dark:bg-gray-600 rounded-full w-7" />
                                </div>
                                {/* Scanning line */}
                                <div className="absolute left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-brand-500 to-transparent" style={{ animation: "scanLine 1.5s ease-in-out infinite alternate" }} />
                                {/* Corner fold */}
                                <div className="absolute top-0 right-0 w-4 h-4 bg-brand-100 dark:bg-brand-500/20" style={{ clipPath: "polygon(100% 0, 0 0, 100% 100%)" }} />
                            </div>
                            {/* Processing gear */}
                            <div className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center shadow-lg shadow-brand-500/30" style={{ animation: "gearSpin 2s linear infinite" }}>
                                <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                            </div>
                        </div>
                        {/* Pipeline stages + status */}
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-bold text-slate-800 dark:text-white mb-1">
                                Analyzing {files.length} document{files.length !== 1 ? "s" : ""}
                            </p>
                            {/* Pipeline steps visualization */}
                            <div className="flex items-center gap-1 mb-3">
                                {[
                                    { icon: "📥", label: "Ingest", delay: "0s" },
                                    { icon: "🔍", label: "OCR", delay: "0.5s" },
                                    { icon: "🧠", label: "Extract", delay: "1s" },
                                    { icon: "✅", label: "Validate", delay: "1.5s" },
                                    ...(enableAHMN ? [{ icon: "🎯", label: "Learn", delay: "2s" }] : []),
                                ].map((step, i) => (
                                    <div key={i} className="flex items-center gap-1">
                                        <div className="flex flex-col items-center px-1.5 py-1 rounded-lg" style={{ animation: `pipelineStep 2s ease-in-out ${step.delay} infinite` }}>
                                            <span className="text-xs">{step.icon}</span>
                                            <span className="text-[8px] text-slate-500 dark:text-gray-400 font-medium">{step.label}</span>
                                        </div>
                                        {i < (enableAHMN ? 4 : 3) && (
                                            <svg className="w-3 h-3 text-slate-300 dark:text-gray-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                                        )}
                                    </div>
                                ))}
                            </div>
                            {/* Progress bar */}
                            <div className="w-full h-1.5 bg-slate-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                <div className="h-full rounded-full bg-gradient-to-r from-brand-500 via-cyan-400 to-violet-500" style={{
                                    backgroundSize: "200% 100%",
                                    animation: "gradientMove 1.5s ease-in-out infinite",
                                    width: `${Math.min(95, (elapsedSec / (enableGuardrails ? 30 : enableXAI ? 15 : 10)) * 100)}%`,
                                    transition: "width 1s ease-out"
                                }} />
                            </div>
                        </div>
                        {/* Timer */}
                        <div className="flex-shrink-0 text-right">
                            <p className="text-2xl font-mono font-bold text-brand-600 dark:text-brand-400 tabular-nums">
                                {Math.floor(elapsedSec / 60)}:{String(elapsedSec % 60).padStart(2, "0")}
                            </p>
                            <p className="text-[10px] text-slate-400 dark:text-gray-500 uppercase tracking-wide">elapsed</p>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Main content grid ── */}
            <div className="grid gap-5 lg:grid-cols-5">
                {/* ── Upload Panel (2 cols) ── */}
                <div className="lg:col-span-2 space-y-4">
                    <form onSubmit={handleSubmit} className="space-y-4">
                        {/* Drop Zone */}
                        <div
                            role="button"
                            tabIndex={0}
                            aria-label="Upload documents — drag and drop or click to browse"
                            className={`relative overflow-hidden glass-panel rounded-2xl p-8 text-center cursor-pointer transition-all duration-300 ${dragActive
                                ? "ring-2 ring-brand-500 bg-brand-50/50 dark:bg-brand-500/5 border-brand-300 dark:border-brand-500/30 scale-[1.02] shadow-2xl shadow-brand-500/20"
                                : "hover:border-brand-300 dark:hover:border-brand-500/20 hover:shadow-xl"
                                }`}
                            onDragEnter={handleDrag}
                            onDragLeave={handleDrag}
                            onDragOver={handleDrag}
                            onDrop={handleDrop}
                            onClick={() => fileInputRef.current?.click()}
                            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInputRef.current?.click(); } }}
                        >
                            {dragActive && (
                                <div className="absolute inset-0 bg-gradient-to-br from-brand-500/5 to-cyan-500/5 animate-pulse" />
                            )}
                            <input ref={fileInputRef} type="file" multiple onChange={handleFileChange} className="hidden"
                                accept=".pdf,.png,.jpg,.jpeg,.tiff,.tif,.bmp,.txt,.json" aria-label="Select documents to upload" />
                            <div className="relative z-10">
                                <div className={`w-16 h-16 mx-auto rounded-2xl flex items-center justify-center mb-4 transition-all duration-300 ${dragActive
                                    ? "bg-gradient-to-br from-brand-400 to-cyan-500 shadow-lg shadow-brand-500/30 scale-110"
                                    : "bg-slate-100 dark:bg-gray-800 border border-slate-200 dark:border-gray-700"}`}>
                                    <svg className={`w-7 h-7 transition-colors ${dragActive ? "text-white" : "text-slate-400 dark:text-gray-500"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                                    </svg>
                                </div>
                                <p className="text-sm font-semibold text-slate-700 dark:text-gray-200">
                                    {dragActive ? "Drop files here" : "Drag & drop documents"}
                                </p>
                                <p className="text-xs text-slate-400 dark:text-gray-500 mt-1.5">
                                    PDF, PNG, JPG, TIFF, TXT, JSON — or click to browse
                                </p>
                            </div>
                        </div>

                        {/* File List */}
                        {files.length > 0 && (
                            <div className="glass-panel rounded-xl p-4 space-y-2">
                                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-2">
                                    {files.length} file{files.length > 1 ? "s" : ""} selected
                                </p>
                                <div className="space-y-1.5 max-h-40 overflow-y-auto">
                                    {files.map((file, i) => (
                                        <div key={i} className="flex items-center justify-between px-3 py-2 bg-white/60 dark:bg-gray-800/40 rounded-lg border border-slate-100 dark:border-gray-700/50">
                                            <div className="flex items-center gap-2 min-w-0">
                                                <span className="text-sm flex-shrink-0">{fileIcon(file.name)}</span>
                                                <span className="text-xs text-slate-700 dark:text-gray-200 truncate">{file.name}</span>
                                                <span className="text-[10px] text-slate-400 dark:text-gray-500 flex-shrink-0">
                                                    {(file.size / 1024).toFixed(0)} KB
                                                </span>
                                            </div>
                                            <button type="button" onClick={() => removeFile(i)}
                                                className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 transition-colors text-sm ml-2">✕</button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Extraction Fields */}
                        <div className="glass-panel rounded-xl p-4 space-y-3">
                            <div className="flex items-center justify-between">
                                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Extraction Fields</p>
                                <span className="text-[10px] text-slate-400 dark:text-gray-500 bg-slate-100 dark:bg-gray-800 px-2 py-0.5 rounded-full">{fields.length} defined</span>
                            </div>
                            {fields.length > 0 && (
                                <div className="space-y-1.5 max-h-32 overflow-y-auto">
                                    {fields.map((field, i) => (
                                        <div key={i} className="flex items-center gap-2 px-3 py-2 bg-brand-50/50 dark:bg-brand-500/5 rounded-lg border border-brand-100 dark:border-brand-500/10">
                                            <span className="w-1.5 h-1.5 rounded-full bg-brand-500 flex-shrink-0" />
                                            <span className="text-xs font-medium text-slate-800 dark:text-gray-200">{field.name}</span>
                                            {field.description && <span className="text-[10px] text-slate-400 dark:text-gray-500 truncate">— {field.description}</span>}
                                            <button type="button" onClick={() => removeField(i)}
                                                className="ml-auto text-slate-400 hover:text-red-500 text-xs flex-shrink-0">✕</button>
                                        </div>
                                    ))}
                                </div>
                            )}
                            {fields.length === 0 && (
                                <div className="space-y-2">
                                    <p className="text-[11px] text-slate-500 dark:text-gray-400">
                                        No fields defined — the system will auto-extract all detected entities. Add fields below to target specific data.
                                    </p>
                                    <div className="flex flex-wrap gap-1.5">
                                        <span className="text-[10px] text-slate-400 dark:text-gray-500 italic mr-1">Examples:</span>
                                        {[
                                            { name: "invoice_number", desc: "Unique invoice ID" },
                                            { name: "total_amount", desc: "Total due" },
                                            { name: "date", desc: "Document date" },
                                            { name: "vendor_name", desc: "Company name" },
                                            { name: "project_title", desc: "Title" },
                                        ].map((ex) => (
                                            <button key={ex.name} type="button"
                                                onClick={() => setFields((prev) => [...prev, { name: ex.name, description: ex.desc }])}
                                                className="px-2 py-1 bg-slate-100/80 dark:bg-gray-800/60 border border-dashed border-slate-300 dark:border-gray-600 rounded-md text-[10px] text-slate-500 dark:text-gray-400 hover:border-brand-400 hover:text-brand-600 dark:hover:text-brand-400 hover:bg-brand-50/50 dark:hover:bg-brand-500/5 transition-all cursor-pointer"
                                            >
                                                + {ex.name}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}
                            <div className="flex gap-2">
                                <input type="text" placeholder="Field name" value={newFieldName}
                                    onChange={(e) => setNewFieldName(e.target.value)} onKeyDown={handleFieldKeyDown}
                                    className="flex-1 glass-input px-3 py-2 text-xs rounded-lg" />
                                <input type="text" placeholder="Description" value={newFieldDesc}
                                    onChange={(e) => setNewFieldDesc(e.target.value)} onKeyDown={handleFieldKeyDown}
                                    className="flex-1 glass-input px-3 py-2 text-xs rounded-lg" />
                                <button type="button" onClick={addField}
                                    className="px-3 py-2 bg-slate-100 dark:bg-gray-800 hover:bg-slate-200 dark:hover:bg-gray-700 border border-slate-200 dark:border-gray-700 rounded-lg text-xs font-medium text-slate-600 dark:text-gray-300 transition-colors">+ Add</button>
                            </div>
                        </div>

                        {/* Pipeline Options — Upfront Toggles */}
                        <div className="glass-panel rounded-xl p-4 space-y-3">
                            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Pipeline Options</p>
                            <div className="space-y-2">
                                {([
                                    { key: "ahmn" as const, icon: "🎯", label: "AHMN Advice", desc: "Bandit-guided policy selection (~1-3s)", checked: enableAHMN, setter: setEnableAHMN },
                                    { key: "guardrails" as const, icon: "🛡️", label: "Guardrails", desc: "6-layer quality validation (~8-20s)", checked: enableGuardrails, setter: setEnableGuardrails },
                                    { key: "xai" as const, icon: "📊", label: "Explain", desc: "Component-level explanations (~1s)", checked: enableXAI, setter: setEnableXAI },
                                ]).map((opt) => (
                                    <label key={opt.key} className={`flex items-center justify-between cursor-pointer px-3 py-2.5 rounded-lg border transition-all duration-150 ${opt.checked ? "bg-brand-50/50 dark:bg-brand-500/5 border-brand-200 dark:border-brand-500/20" : "bg-white/30 dark:bg-gray-800/20 border-slate-200/60 dark:border-gray-700/40 hover:border-slate-300 dark:hover:border-gray-600"}`}>
                                        <div className="flex items-center gap-2.5">
                                            <span className="text-base">{opt.icon}</span>
                                            <div>
                                                <p className="text-[11px] font-semibold text-slate-700 dark:text-gray-200">{opt.label}</p>
                                                <p className="text-[9px] text-slate-400 dark:text-gray-500">{opt.desc}</p>
                                            </div>
                                        </div>
                                        <div className="relative">
                                            <input type="checkbox" checked={opt.checked} onChange={(e) => opt.setter(e.target.checked)} className="sr-only peer" />
                                            <div className="w-9 h-5 bg-slate-200 dark:bg-gray-700 rounded-full peer peer-checked:bg-brand-500 transition-colors" />
                                            <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow peer-checked:translate-x-4 transition-transform" />
                                        </div>
                                    </label>
                                ))}
                            </div>
                            <p className="text-[9px] text-slate-400 dark:text-gray-500 text-center pt-1">
                                Estimated time: ~{enableGuardrails ? "15-30s" : enableXAI ? "5-10s" : "3-8s"} per document
                            </p>
                        </div>

                        {/* Config (collapsible) */}
                        <button type="button" onClick={() => setShowConfig(!showConfig)}
                            className="w-full glass-panel rounded-xl px-4 py-3 text-left hover:bg-white/80 dark:hover:bg-gray-800/60 transition-all duration-150">
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-medium text-slate-600 dark:text-gray-300">Advanced Configuration</span>
                                <span className="text-slate-400 text-xs transition-transform duration-150" style={{ transform: showConfig ? "rotate(180deg)" : "rotate(0deg)" }}>▼</span>
                            </div>
                        </button>
                        {showConfig && (
                            <div className="glass-panel rounded-xl p-4">
                                <label className="block text-xs font-medium text-slate-500 dark:text-gray-400 mb-2">Pipeline Config Path</label>
                                <input type="text" value={configPath} onChange={(e) => setConfigPath(e.target.value)}
                                    className="w-full glass-input px-3 py-2 text-xs rounded-lg" />
                            </div>
                        )}

                        {/* Submit */}
                        <button type="submit" disabled={loading || files.length === 0}
                            className="w-full rounded-2xl px-4 py-4 text-sm disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2.5 font-bold text-white shadow-lg hover:shadow-xl transition-all duration-200 active:scale-[0.98] bg-gradient-to-r from-brand-500 to-cyan-500 shadow-brand-500/20 hover:shadow-brand-500/30">
                            {loading ? (
                                <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Processing Pipeline...</>
                            ) : (
                                <>
                                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                    </svg>
                                    Process {files.length > 0 ? `${files.length} Document${files.length > 1 ? "s" : ""}` : "Documents"}
                                </>
                            )}
                        </button>
                    </form>

                    {error && (
                        <div role="alert" aria-live="assertive" className={`glass-panel rounded-xl p-4 border-l-4 ${result && result.docs.length > 0 ? "border-l-amber-500" : "border-l-red-500"}`}>
                            <div className="flex items-start gap-2">
                                <span className="text-sm mt-0.5">{result && result.docs.length > 0 ? "⚠️" : "❌"}</span>
                                <div>
                                    <p className={`text-xs font-medium ${result && result.docs.length > 0 ? "text-amber-700 dark:text-amber-300" : "text-red-700 dark:text-red-300"}`}>{error}</p>
                                    {result?.partial_failures && result.partial_failures.length > 0 && (
                                        <div className="mt-2 space-y-1">
                                            {result.partial_failures.map((pf, i) => (
                                                <div key={i} className="flex items-start gap-1.5 text-[10px] text-amber-600 dark:text-amber-400">
                                                    <span className="mt-0.5 flex-shrink-0">•</span>
                                                    <span><span className="font-medium">{pf.file}:</span> {pf.error}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* ── Multi-Document Progress Tracker ── */}
                    {loading && docProgress.length > 1 && (
                        <div className="glass-panel rounded-xl p-4 space-y-3" role="status" aria-label="Document processing progress">
                            <div className="flex items-center justify-between">
                                <p className="text-xs font-semibold uppercase tracking-wider text-brand-600 dark:text-brand-400">
                                    Processing {docProgress.length} Documents
                                </p>
                                <span className="text-[10px] text-slate-400 dark:text-gray-500">
                                    {docProgress.filter(d => d.status === "done").length}/{docProgress.length} complete
                                </span>
                            </div>
                            {/* Overall progress bar */}
                            <div className="w-full h-2 bg-slate-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-gradient-to-r from-brand-500 to-cyan-500 rounded-full transition-all duration-500 ease-out"
                                    style={{ width: `${Math.max(5, (docProgress.filter(d => d.status === "done").length / docProgress.length) * 100)}%` }}
                                />
                            </div>
                            {/* Per-document rows */}
                            <div className="space-y-1.5 max-h-48 overflow-y-auto">
                                {docProgress.map((dp, i) => (
                                    <div key={i} className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-all duration-300 ${dp.status === "done"
                                        ? "bg-emerald-50/60 dark:bg-emerald-500/5 border-emerald-200/60 dark:border-emerald-500/10"
                                        : dp.status === "processing"
                                            ? "bg-brand-50/60 dark:bg-brand-500/5 border-brand-200/60 dark:border-brand-500/10 shadow-sm shadow-brand-500/5"
                                            : dp.status === "error"
                                                ? "bg-red-50/60 dark:bg-red-500/5 border-red-200/60 dark:border-red-500/10"
                                                : "bg-slate-50/60 dark:bg-gray-800/30 border-slate-200/40 dark:border-gray-700/40"
                                        }`}>
                                        {/* Status icon */}
                                        <div className="flex-shrink-0 w-6 h-6 flex items-center justify-center">
                                            {dp.status === "done" && <span className="text-emerald-500 text-sm">✓</span>}
                                            {dp.status === "processing" && (
                                                <div className="w-4 h-4 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
                                            )}
                                            {dp.status === "error" && <span className="text-red-500 text-sm">✕</span>}
                                            {dp.status === "queued" && (
                                                <div className="w-2 h-2 rounded-full bg-slate-300 dark:bg-gray-600" />
                                            )}
                                        </div>
                                        {/* File info */}
                                        <div className="flex-1 min-w-0">
                                            <p className={`text-xs font-medium truncate ${dp.status === "done" ? "text-emerald-700 dark:text-emerald-300"
                                                : dp.status === "processing" ? "text-brand-700 dark:text-brand-300"
                                                    : "text-slate-500 dark:text-gray-400"
                                                }`}>{dp.name}</p>
                                        </div>
                                        {/* Mini progress bar per doc */}
                                        <div className="flex-shrink-0 w-16">
                                            {dp.status === "processing" && (
                                                <div className="w-full h-1 bg-slate-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                                    <div className="h-full bg-brand-500 rounded-full animate-pulse" style={{ width: "60%" }} />
                                                </div>
                                            )}
                                            {dp.status === "done" && (
                                                <div className="w-full h-1 bg-emerald-500 rounded-full" />
                                            )}
                                        </div>
                                        {/* Status label */}
                                        <span className={`text-[9px] font-medium flex-shrink-0 ${dp.status === "done" ? "text-emerald-600 dark:text-emerald-400"
                                            : dp.status === "processing" ? "text-brand-600 dark:text-brand-400"
                                                : "text-slate-400 dark:text-gray-500"
                                            }`}>
                                            {dp.status === "done" ? "Complete" : dp.status === "processing" ? "Extracting..." : dp.status === "error" ? "Failed" : "Queued"}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* ── Quick Integration Summary (sidebar) ── */}
                    {integration && (
                        <div className="glass-panel rounded-xl p-4 space-y-3">
                            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Integration Summary</p>
                            <div className="space-y-2">
                                <SummaryRow icon="🎯" label="AHMN Advice"
                                    value={integration.ahmn_advice.error === "Skipped by user" ? "Skipped" : integration.ahmn_advice.error ? "Unavailable" : integration.ahmn_advice.policy_id}
                                    status={integration.ahmn_advice.error === "Skipped by user" ? null : !integration.ahmn_advice.error}
                                    detail={integration.ahmn_advice.error === "Skipped by user" ? "Disabled by user" : integration.ahmn_advice.error || `${(integration.ahmn_advice.confidence * 100).toFixed(0)}% confidence`} />
                                <SummaryRow icon="🛡️" label="Guardrails"
                                    value={integration.skipped_guardrails ? "Skipped" : `${integration.guardrails.filter(g => g.overall_passes).length}/${integration.guardrails.length} passed`}
                                    status={integration.skipped_guardrails ? null : integration.guardrails.every(g => g.overall_passes || !!g.error)}
                                    detail={integration.skipped_guardrails ? "Disabled by user" : integration.guardrails.some(g => g.error) ? "Some checks unavailable" : undefined} />
                                <SummaryRow icon="📊" label="Explanations"
                                    value={integration.skipped_xai ? "Skipped" : `${integration.xai_explanations.filter(x => !x.error).length} docs explained`}
                                    status={integration.skipped_xai ? null : integration.xai_explanations.some(x => !x.error)}
                                    detail={integration.skipped_xai ? "Disabled by user" : integration.xai_explanations.some(x => x.error) ? "Some unavailable" : undefined} />
                                <SummaryRow icon="�" label="AHMN Learn"
                                    value={integration.ahmn_feedback.status}
                                    status={integration.ahmn_feedback.status === "logged"}
                                    detail={integration.ahmn_feedback.error || (integration.ahmn_feedback.metrics_sent.f1_score
                                        ? `F1: ${(integration.ahmn_feedback.metrics_sent.f1_score * 100).toFixed(1)}%` : undefined)} />
                            </div>
                            <div className="pt-2 border-t border-slate-200 dark:border-gray-700">
                                <p className="text-[10px] text-slate-400 dark:text-gray-500">Cycle time: {(integration.cycle_time_ms / 1000).toFixed(1)}s</p>
                            </div>
                        </div>
                    )}
                </div>

                {/* ── Results Panel (3 cols) ── */}
                <div className="lg:col-span-3 space-y-4">
                    {!result ? (
                        <div className="glass-panel rounded-2xl p-12 text-center">
                            <div className="max-w-sm mx-auto">
                                <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-slate-100 to-slate-50 dark:from-gray-800 dark:to-gray-900 border border-slate-200/60 dark:border-gray-700 flex items-center justify-center mb-5 shadow-inner">
                                    <svg className="w-9 h-9 text-slate-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                                    </svg>
                                </div>
                                <p className="text-lg font-bold text-slate-600 dark:text-gray-300">Ready to extract</p>
                                <p className="text-sm text-slate-400 dark:text-gray-500 mt-2">Upload documents to run the full AI processing pipeline</p>
                                <div className="mt-6 grid grid-cols-4 gap-2 stagger-children">
                                    {[
                                        { icon: "🎯", label: "Advise" },
                                        { icon: "⚙️", label: "Extract" },
                                        { icon: "🛡️", label: "Validate" },
                                        { icon: "�", label: "Learn" },
                                    ].map((step) => (
                                        <div key={step.label} className="px-2 py-2.5 bg-slate-50 dark:bg-gray-800/50 rounded-xl border border-slate-200/60 dark:border-gray-700">
                                            <span className="text-lg block mb-0.5">{step.icon}</span>
                                            <p className="text-[10px] text-slate-500 dark:text-gray-400 text-center font-medium">{step.label}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    ) : (
                        <>
                            {/* Run Summary Bar */}
                            <div className="glass-panel rounded-xl p-4">
                                <div className="flex flex-wrap items-center gap-4">
                                    <div className="flex items-center gap-2">
                                        <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                                        <span className="text-xs font-medium text-emerald-700 dark:text-emerald-300">Complete</span>
                                    </div>
                                    <div className="h-4 w-px bg-slate-200 dark:bg-gray-700" />
                                    <div className="text-xs text-slate-500 dark:text-gray-400">
                                        <span className="text-slate-700 dark:text-gray-200 font-medium">{result.docs.length}</span> doc{result.docs.length !== 1 ? "s" : ""}
                                    </div>
                                    {result.metrics?.duration_ms != null && (
                                        <>
                                            <div className="h-4 w-px bg-slate-200 dark:bg-gray-700" />
                                            <div className="text-xs text-slate-500 dark:text-gray-400">
                                                <span className="text-slate-700 dark:text-gray-200 font-medium">{(result.metrics.duration_ms / 1000).toFixed(1)}</span>s
                                            </div>
                                        </>
                                    )}
                                    {integration && (
                                        <>
                                            <div className="h-4 w-px bg-slate-200 dark:bg-gray-700" />
                                            <div className="text-xs text-slate-500 dark:text-gray-400">
                                                Cycle: <span className="text-slate-700 dark:text-gray-200 font-medium">{(integration.cycle_time_ms / 1000).toFixed(1)}</span>s
                                            </div>
                                        </>
                                    )}
                                    <div className="ml-auto flex gap-2">
                                        <button onClick={() => handleDownload("docs.xlsx", "docs.xlsx")}
                                            className="px-3 py-1.5 bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 rounded-lg hover:bg-brand-100 dark:hover:bg-brand-500/20 text-xs font-medium transition-all shadow-sm shadow-brand-500/5">↓ Results</button>
                                        {result.entities?.length > 0 && (
                                            <button onClick={() => handleDownload("entities.xlsx", "entities.xlsx")}
                                                className="px-3 py-1.5 bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/20 text-violet-700 dark:text-violet-300 rounded-lg hover:bg-violet-100 dark:hover:bg-violet-500/20 text-xs font-medium transition-all shadow-sm shadow-violet-500/5">↓ Entities</button>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Warnings */}
                            {result.warnings?.length > 0 && (
                                <div className="glass-panel rounded-xl p-4 border-l-4 border-l-amber-500">
                                    <p className="text-xs font-semibold text-amber-700 dark:text-amber-300 mb-1.5">Preflight Warnings</p>
                                    <ul className="space-y-1">
                                        {result.warnings.map((w, i) => (
                                            <li key={i} className="text-xs text-amber-600 dark:text-amber-400 flex items-start gap-1.5">
                                                <span className="mt-0.5">⚠</span> {w}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            {/* Tab Bar */}
                            <div className="glass-panel rounded-xl p-1.5 flex gap-1" role="tablist" aria-label="Result views">
                                {(["documents", "entities", "fulltext", "integration"] as const).map((tab) => (
                                    <button key={tab} onClick={() => setActiveTab(tab)}
                                        role="tab"
                                        aria-selected={activeTab === tab}
                                        aria-controls={`tabpanel-${tab}`}
                                        className={`flex-1 px-3 py-2.5 rounded-lg text-xs font-medium transition-all duration-150 ${activeTab === tab
                                            ? tab === "integration"
                                                ? "bg-gradient-to-r from-brand-50 to-violet-50 dark:from-brand-500/10 dark:to-violet-500/10 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-500/20 shadow-sm"
                                                : "bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-500/20 shadow-sm shadow-brand-500/5"
                                            : "text-slate-500 dark:text-gray-400 hover:text-slate-700 dark:hover:text-gray-200 hover:bg-slate-50 dark:hover:bg-gray-800 border border-transparent"
                                            }`}>
                                        {tab === "documents" && `📄 Docs (${result.docs.length})`}
                                        {tab === "entities" && `🏷️ Entities (${result.entities?.length || 0})`}
                                        {tab === "fulltext" && "📝 Full Text"}
                                        {tab === "integration" && "🔄 Pipeline"}
                                    </button>
                                ))}
                            </div>

                            {/* Tab Content */}
                            <div className="space-y-3">
                                {activeTab === "documents" && result.docs.map((doc) => (
                                    <DocCard key={doc.doc_id} doc={doc} expanded={expandedDoc === doc.doc_id}
                                        onToggle={() => setExpandedDoc(expandedDoc === doc.doc_id ? null : doc.doc_id)}
                                        guardrail={integration?.guardrails.find(g => g.document_id === doc.doc_id)}
                                        xai={integration?.xai_explanations.find(x => x.document_id === doc.doc_id)} />
                                ))}

                                {activeTab === "entities" && (
                                    result.entities?.length > 0 ? (
                                        <div className="glass-panel rounded-xl overflow-hidden">
                                            {/* Search & Filter Bar */}
                                            <div className="px-4 py-3 border-b border-slate-200 dark:border-gray-700 bg-slate-50/50 dark:bg-gray-800/30 flex flex-wrap items-center gap-3">
                                                <div className="flex-1 min-w-[200px] relative">
                                                    <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                                                    <input type="text" placeholder="Search entities..." value={entitySearch} onChange={(e) => { setEntitySearch(e.target.value); setEntityPage(0); }}
                                                        className="w-full glass-input pl-9 pr-3 py-2 text-xs rounded-lg" />
                                                </div>
                                                <div className="flex gap-1">
                                                    {(["all", "high", "medium", "low"] as const).map((f) => (
                                                        <button key={f} onClick={() => { setEntityConfidenceFilter(f); setEntityPage(0); }}
                                                            className={`px-2.5 py-1.5 rounded-lg text-[10px] font-medium transition-all border ${entityConfidenceFilter === f
                                                                ? f === "high" ? "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-300"
                                                                    : f === "medium" ? "bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-300"
                                                                        : f === "low" ? "bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-300"
                                                                            : "bg-brand-50 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300"
                                                                : "border-slate-200 dark:border-gray-700 text-slate-500 dark:text-gray-400 hover:border-slate-300"}`}>
                                                            {f === "all" ? `All (${(() => {
                                                                const allEnts = result.docs.flatMap(d => d.entity_details || []);
                                                                return allEnts.length || result.entities.length;
                                                            })()})` : f === "high" ? "≥70%" : f === "medium" ? "50-70%" : "<50%"}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                            {/* Table */}
                                            {(() => {
                                                // Gather all entities across docs
                                                let allEntities = result.docs.flatMap(d =>
                                                    (d.entity_details || []).map(e => ({ ...e, docName: d.filename || d.doc_id }))
                                                );
                                                // Fallback to flat entities if no entity_details
                                                if (allEntities.length === 0) {
                                                    allEntities = result.entities.map((e: any) => ({
                                                        key: e.field_key || e.key || Object.keys(e)[0] || "",
                                                        label: e.field_key || e.key || "",
                                                        value: e.field_value || e.value || Object.values(e)[1] || "—",
                                                        confidence: typeof e.confidence === "number" ? e.confidence : parseFloat(e.field_confidence) || 0,
                                                        source: e.source || e.field_source || "—",
                                                        page: e.page,
                                                        is_explicit: false,
                                                        docName: "—",
                                                    }));
                                                }
                                                // Apply search filter
                                                if (entitySearch) {
                                                    const q = entitySearch.toLowerCase();
                                                    allEntities = allEntities.filter(e =>
                                                        (e.key || "").toLowerCase().includes(q) ||
                                                        (e.label || "").toLowerCase().includes(q) ||
                                                        String(e.value || "").toLowerCase().includes(q) ||
                                                        (e.docName || "").toLowerCase().includes(q)
                                                    );
                                                }
                                                // Apply confidence filter
                                                if (entityConfidenceFilter === "high") allEntities = allEntities.filter(e => e.confidence >= 0.7);
                                                else if (entityConfidenceFilter === "medium") allEntities = allEntities.filter(e => e.confidence >= 0.5 && e.confidence < 0.7);
                                                else if (entityConfidenceFilter === "low") allEntities = allEntities.filter(e => e.confidence < 0.5);

                                                const totalPages = Math.max(1, Math.ceil(allEntities.length / ENTITIES_PER_PAGE));
                                                const currentPage = Math.min(entityPage, totalPages - 1);
                                                const paged = allEntities.slice(currentPage * ENTITIES_PER_PAGE, (currentPage + 1) * ENTITIES_PER_PAGE);

                                                return (
                                                    <>
                                                        <div className="overflow-x-auto">
                                                            <table className="w-full text-xs">
                                                                <thead>
                                                                    <tr className="border-b border-slate-200 dark:border-gray-700">
                                                                        <th className="px-4 py-2.5 text-left font-semibold text-slate-500 dark:text-gray-400 bg-slate-50/30 dark:bg-gray-800/20 w-[140px]">Field</th>
                                                                        <th className="px-4 py-2.5 text-left font-semibold text-slate-500 dark:text-gray-400 bg-slate-50/30 dark:bg-gray-800/20">Value</th>
                                                                        <th className="px-4 py-2.5 text-left font-semibold text-slate-500 dark:text-gray-400 bg-slate-50/30 dark:bg-gray-800/20 w-[100px]">Confidence</th>
                                                                        <th className="px-4 py-2.5 text-left font-semibold text-slate-500 dark:text-gray-400 bg-slate-50/30 dark:bg-gray-800/20 w-[80px]">Source</th>
                                                                        <th className="px-4 py-2.5 text-left font-semibold text-slate-500 dark:text-gray-400 bg-slate-50/30 dark:bg-gray-800/20 w-[120px]">Document</th>
                                                                    </tr>
                                                                </thead>
                                                                <tbody>
                                                                    {paged.map((entity, i) => (
                                                                        <tr key={i} className="border-b border-slate-100 dark:border-gray-800/50 hover:bg-brand-50/20 dark:hover:bg-brand-500/5 transition-colors">
                                                                            <td className="px-4 py-2 font-medium text-slate-800 dark:text-gray-200">
                                                                                <div className="flex items-center gap-1.5">
                                                                                    <span className="truncate max-w-[120px]">{entity.label || entity.key}</span>
                                                                                    {entity.is_explicit && <span className="px-1 py-0.5 bg-brand-100 dark:bg-brand-500/10 rounded text-[7px] font-bold text-brand-600 dark:text-brand-400 flex-shrink-0">TARGET</span>}
                                                                                </div>
                                                                            </td>
                                                                            <td className="px-4 py-2 text-slate-700 dark:text-gray-300 max-w-[250px] truncate">{String(entity.value)}</td>
                                                                            <td className="px-4 py-2">
                                                                                <div className="flex items-center gap-1.5">
                                                                                    <div className="w-10 h-1.5 bg-slate-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                                                                        <div className={`h-full rounded-full ${entity.confidence >= 0.7 ? "bg-emerald-500" : entity.confidence >= 0.5 ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${Math.min(entity.confidence * 100, 100)}%` }} />
                                                                                    </div>
                                                                                    <span className={`text-[10px] font-semibold ${entity.confidence >= 0.7 ? "text-emerald-600 dark:text-emerald-400" : entity.confidence >= 0.5 ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400"}`}>
                                                                                        {(entity.confidence * 100).toFixed(0)}%
                                                                                    </span>
                                                                                </div>
                                                                            </td>
                                                                            <td className="px-4 py-2 text-slate-500 dark:text-gray-400 text-[10px]">{entity.source || "—"}</td>
                                                                            <td className="px-4 py-2 text-slate-500 dark:text-gray-400 text-[10px] truncate max-w-[100px]">{entity.docName}</td>
                                                                        </tr>
                                                                    ))}
                                                                </tbody>
                                                            </table>
                                                        </div>
                                                        {/* Pagination */}
                                                        {totalPages > 1 && (
                                                            <div className="px-4 py-3 border-t border-slate-200 dark:border-gray-700 flex items-center justify-between bg-slate-50/30 dark:bg-gray-800/20">
                                                                <p className="text-[10px] text-slate-400 dark:text-gray-500">
                                                                    Showing {currentPage * ENTITIES_PER_PAGE + 1}-{Math.min((currentPage + 1) * ENTITIES_PER_PAGE, allEntities.length)} of {allEntities.length}
                                                                </p>
                                                                <div className="flex gap-1">
                                                                    <button onClick={() => setEntityPage(Math.max(0, currentPage - 1))} disabled={currentPage === 0}
                                                                        className="px-2 py-1 rounded text-[10px] font-medium border border-slate-200 dark:border-gray-700 text-slate-500 dark:text-gray-400 hover:bg-slate-100 dark:hover:bg-gray-800 disabled:opacity-30 transition-all">← Prev</button>
                                                                    <span className="px-2 py-1 text-[10px] font-semibold text-slate-600 dark:text-gray-300">{currentPage + 1}/{totalPages}</span>
                                                                    <button onClick={() => setEntityPage(Math.min(totalPages - 1, currentPage + 1))} disabled={currentPage >= totalPages - 1}
                                                                        className="px-2 py-1 rounded text-[10px] font-medium border border-slate-200 dark:border-gray-700 text-slate-500 dark:text-gray-400 hover:bg-slate-100 dark:hover:bg-gray-800 disabled:opacity-30 transition-all">Next →</button>
                                                                </div>
                                                            </div>
                                                        )}
                                                        {allEntities.length === 0 && (
                                                            <div className="px-4 py-8 text-center text-slate-400 dark:text-gray-500 text-xs">
                                                                No entities match your search/filter criteria
                                                            </div>
                                                        )}
                                                    </>
                                                );
                                            })()}
                                        </div>
                                    ) : (
                                        <div className="glass-panel rounded-xl p-8 text-center text-slate-400 dark:text-gray-500 text-sm">
                                            No entities extracted — try adding extraction fields before processing
                                        </div>
                                    )
                                )}

                                {activeTab === "fulltext" && (
                                    result.docs.some(d => d.extracted_text) ? (
                                        <div className="space-y-4">
                                            {result.docs.map((doc) => (
                                                <div key={doc.doc_id} className="glass-panel rounded-xl overflow-hidden">
                                                    <div className="px-5 py-3 border-b border-slate-200 dark:border-gray-700 bg-slate-50/50 dark:bg-gray-800/30 flex items-center justify-between">
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-base">📄</span>
                                                            <p className="text-sm font-semibold text-slate-900 dark:text-white">{doc.filename || doc.doc_id}</p>
                                                            {doc.extracted_text && (
                                                                <span className="text-[10px] text-slate-400 dark:text-gray-500">
                                                                    {(doc.extracted_text.match(/--- Page \d+ ---/g) || []).length || 1} page{((doc.extracted_text.match(/--- Page \d+ ---/g) || []).length || 1) !== 1 ? "s" : ""}
                                                                    {" · "}{doc.extracted_text.length.toLocaleString()} chars
                                                                </span>
                                                            )}
                                                        </div>
                                                        <button
                                                            onClick={() => {
                                                                navigator.clipboard.writeText(doc.extracted_text || "");
                                                            }}
                                                            className="px-3 py-1.5 bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 rounded-lg hover:bg-brand-100 dark:hover:bg-brand-500/20 text-xs font-medium transition-all"
                                                        >
                                                            📋 Copy Text
                                                        </button>
                                                    </div>
                                                    <div className="p-5 max-h-[600px] overflow-y-auto">
                                                        <FormattedExtractedText text={doc.extracted_text || "No text extracted for this document."} />
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="glass-panel rounded-xl p-8 text-center text-slate-400 dark:text-gray-500 text-sm">
                                            No extracted text available — text will appear here after processing documents
                                        </div>
                                    )
                                )}

                                {activeTab === "integration" && integration && (
                                    <IntegrationPanel integration={integration} activeSubTab={integrationTab} onSubTabChange={setIntegrationTab} durationMs={result.metrics?.duration_ms} />
                                )}
                                {activeTab === "integration" && !integration && (
                                    <div className="glass-panel rounded-xl p-8 text-center text-slate-400 dark:text-gray-500 text-sm">
                                        No integration data — services may be unavailable
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

/* ══════════════════════════════════════════════════════════════════════════ */
/*  Sub-Components                                                          */
/* ══════════════════════════════════════════════════════════════════════════ */

function CycleStatusBadge({ integration }: { integration: PipelineIntegration }) {
    const stages = [
        { ok: !integration.ahmn_advice.error, label: "A" },
        { ok: integration.guardrails.some(g => g.overall_passes), label: "G" },
        { ok: integration.xai_explanations.some(x => !x.error), label: "X" },
        { ok: integration.ahmn_feedback.status === "logged", label: "L" },
    ];
    const allOk = stages.every(s => s.ok);
    return (
        <div className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium border ${allOk
            ? "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-300"
            : "bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-300"}`}>
            {stages.map((s, i) => (
                <span key={i} className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold ${s.ok ? "bg-emerald-500 text-white" : "bg-slate-300 dark:bg-gray-600 text-white"}`}>{s.label}</span>
            ))}
            <span className="ml-1">{allOk ? "Full Cycle" : "Partial"}</span>
        </div>
    );
}

function SummaryRow({ icon, label, value, status, detail }: { icon: string; label: string; value: string; status: boolean | null; detail?: string }) {
    return (
        <div className="flex items-start gap-2.5 px-3 py-2 bg-white/40 dark:bg-gray-800/30 rounded-lg">
            <span className="text-sm mt-0.5">{icon}</span>
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <p className="text-[11px] font-medium text-slate-700 dark:text-gray-200">{label}</p>
                    <div className={`w-1.5 h-1.5 rounded-full ${status === null ? "bg-slate-400" : status ? "bg-emerald-500" : "bg-amber-500"}`} />
                </div>
                <p className={`text-[10px] truncate ${status === null ? "text-slate-400 dark:text-gray-500 italic" : "text-slate-600 dark:text-gray-300"}`}>{value}</p>
                {detail && <p className="text-[9px] text-slate-400 dark:text-gray-500 truncate">{detail}</p>}
            </div>
        </div>
    );
}

function IntegrationPanel({ integration, activeSubTab, onSubTabChange, durationMs }: {
    integration: PipelineIntegration;
    activeSubTab: "advice" | "guardrails" | "xai" | "feedback";
    onSubTabChange: (tab: "advice" | "guardrails" | "xai" | "feedback") => void;
    durationMs?: number;
}) {
    const tabs = [
        { key: "advice" as const, icon: "🎯", label: "AHMN Advice" },
        { key: "guardrails" as const, icon: "🛡️", label: "Guardrails" },
        { key: "xai" as const, icon: "📊", label: "Explanations" },
        { key: "feedback" as const, icon: "�", label: "AHMN Learn" },
    ];
    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex gap-1.5 flex-wrap">
                {tabs.map((tab) => (
                    <button key={tab.key} onClick={() => onSubTabChange(tab.key)}
                        className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all border ${activeSubTab === tab.key
                            ? "bg-white dark:bg-gray-800 border-slate-300 dark:border-gray-600 text-slate-900 dark:text-white shadow-sm"
                            : "bg-transparent border-transparent text-slate-500 dark:text-gray-400 hover:text-slate-700 dark:hover:text-gray-200 hover:bg-slate-50 dark:hover:bg-gray-800/50"}`}>
                        <span>{tab.icon}</span>{tab.label}
                    </button>
                ))}
            </div>
            <div className="flex items-center gap-3 text-[10px] text-slate-400 dark:text-gray-500">
                {durationMs != null && <span>Total: <span className="font-medium text-slate-600 dark:text-gray-300">{(durationMs / 1000).toFixed(1)}s</span></span>}
                <span>Cycle: <span className="font-medium text-slate-600 dark:text-gray-300">{(integration.cycle_time_ms / 1000).toFixed(1)}s</span></span>
            </div>
            </div>
            {activeSubTab === "advice" && <AdvicePanel advice={integration.ahmn_advice} />}
            {activeSubTab === "guardrails" && <GuardrailsPanel results={integration.guardrails} skipped={integration.skipped_guardrails} />}
            {activeSubTab === "xai" && <XAIPanel explanations={integration.xai_explanations} skipped={integration.skipped_xai} />}
            {activeSubTab === "feedback" && <FeedbackPanel feedback={integration.ahmn_feedback} />}
        </div>
    );
}

function AdvicePanel({ advice }: { advice: PipelineIntegration["ahmn_advice"] }) {
    if (advice.error) {
        return (
            <div className="glass-panel rounded-xl p-5 border-l-4 border-l-amber-500">
                <div className="flex items-center gap-2 mb-2"><span className="text-lg">🎯</span><p className="text-sm font-medium text-amber-700 dark:text-amber-300">AHMN Advice Unavailable</p></div>
                <p className="text-xs text-amber-600 dark:text-amber-400">{advice.error}</p>
                <p className="text-xs text-slate-400 dark:text-gray-500 mt-2">Pipeline continued with default policy.</p>
            </div>
        );
    }
    return (
        <div className="glass-panel rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2"><span className="text-lg">🎯</span><p className="text-sm font-semibold text-slate-900 dark:text-white">AHMN Policy Advice</p></div>
                <span className={`px-2.5 py-1 rounded-full text-[10px] font-medium border ${advice.retrieval_source === "LTM"
                    ? "bg-brand-50 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300"
                    : "bg-slate-100 dark:bg-gray-800 border-slate-200 dark:border-gray-700 text-slate-600 dark:text-gray-300"}`}>
                    Source: {advice.retrieval_source}
                </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Policy ID</p>
                    <p className="text-sm font-medium text-slate-900 dark:text-white font-mono">{advice.policy_id}</p>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Confidence</p>
                    <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-slate-900 dark:text-white">{(advice.confidence * 100).toFixed(1)}%</p>
                        <div className="flex-1 h-1.5 bg-slate-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div className="h-full bg-brand-500 rounded-full transition-all" style={{ width: `${advice.confidence * 100}%` }} />
                        </div>
                    </div>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">RABI Prior</p>
                    <p className="text-sm font-medium text-slate-900 dark:text-white">{advice.rabi_used ? `Yes (${advice.n_neighbors} neighbors)` : "No"}</p>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Advice ID</p>
                    <p className="text-xs font-mono text-slate-600 dark:text-gray-400 truncate">{advice.advice_id || "—"}</p>
                </div>
            </div>
            {Object.keys(advice.policy_data).length > 0 && (
                <div className="p-3 bg-brand-50/30 dark:bg-brand-500/5 rounded-lg border border-brand-100 dark:border-brand-500/10">
                    <p className="text-[10px] font-semibold text-brand-600 dark:text-brand-400 uppercase tracking-wider mb-2">Policy Configuration</p>
                    <pre className="text-xs text-slate-700 dark:text-gray-300 overflow-x-auto">{JSON.stringify(advice.policy_data, null, 2)}</pre>
                </div>
            )}
        </div>
    );
}

function GuardrailsPanel({ results, skipped }: { results: GuardrailDocResult[]; skipped?: boolean }) {
    if (skipped) return (
        <div className="glass-panel rounded-xl p-8 text-center">
            <span className="text-3xl block mb-3">🛡️</span>
            <p className="text-sm font-medium text-slate-600 dark:text-gray-300 mb-1">Guardrails Validation Skipped</p>
            <p className="text-xs text-slate-400 dark:text-gray-500">Enable guardrails in Pipeline Options to run 6-layer quality validation</p>
        </div>
    );
    if (results.length === 0) return <div className="glass-panel rounded-xl p-8 text-center text-slate-400 dark:text-gray-500 text-sm">No guardrail validations available</div>;
    return (
        <div className="space-y-3">
            {results.map((gr) => (
                <div key={gr.document_id} className={`glass-panel rounded-xl p-4 border-l-4 ${gr.error ? "border-l-amber-500" : gr.overall_passes ? "border-l-emerald-500" : "border-l-red-500"}`}>
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                            <span className="text-base">🛡️</span>
                            <p className="text-xs font-medium text-slate-900 dark:text-white">Doc: {gr.document_id.slice(0, 12)}...</p>
                        </div>
                        <div className="flex items-center gap-2">
                            {gr.processing_time_ms > 0 && <span className="text-[10px] text-slate-400 dark:text-gray-500">{(gr.processing_time_ms / 1000).toFixed(1)}s</span>}
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${gr.error
                                ? "bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-300"
                                : gr.overall_passes
                                    ? "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-300"
                                    : "bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-300"}`}>
                                {gr.error ? "Unavailable" : gr.overall_passes ? "PASSED" : "FAILED"}
                            </span>
                        </div>
                    </div>
                    {gr.error ? <p className="text-xs text-amber-600 dark:text-amber-400">{gr.error}</p> : (
                        <div className="space-y-2">
                            {gr.validation_results.map((vr, i) => (
                                <div key={i} className="flex items-center justify-between px-3 py-2 bg-white/40 dark:bg-gray-800/30 rounded-lg">
                                    <div className="flex items-center gap-2 min-w-0">
                                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${vr.is_pass ? "bg-emerald-500" : "bg-red-500"}`} />
                                        <span className="text-[11px] font-medium text-slate-700 dark:text-gray-200">{vr.name}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-[10px] text-slate-400 dark:text-gray-500 truncate max-w-[200px]">{vr.details}</span>
                                        <span className="text-[10px] font-mono text-slate-600 dark:text-gray-300">{(vr.score * 100).toFixed(0)}%</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
}

function ComponentCard({ comp }: { comp: { component: string; title: string; summary: string; details: Array<{ step: number; action: string; description: string; outcome: string; passed?: boolean }>; status: string; metrics: Record<string, unknown> } }) {
    const statusColors = {
        success: "border-l-emerald-500 bg-emerald-50/30 dark:bg-emerald-500/5",
        warning: "border-l-amber-500 bg-amber-50/30 dark:bg-amber-500/5",
        error: "border-l-red-500 bg-red-50/30 dark:bg-red-500/5",
        info: "border-l-slate-400 bg-slate-50/30 dark:bg-slate-500/5",
    };
    const icons = {
        ahmn: "🎯",
        idpo: "⚙️",
        guardrails: "🛡️",
    };
    const bgClass = statusColors[comp.status as keyof typeof statusColors] || statusColors.info;
    const icon = icons[comp.component as keyof typeof icons] || "📋";

    return (
        <div className={`rounded-xl border-l-4 p-4 ${bgClass}`}>
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <span className="text-lg">{icon}</span>
                    <p className="text-sm font-semibold text-slate-900 dark:text-white">{comp.title}</p>
                </div>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium uppercase ${
                    comp.status === "success" ? "bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" :
                    comp.status === "warning" ? "bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300" :
                    comp.status === "error" ? "bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-300" :
                    "bg-slate-100 dark:bg-slate-500/10 text-slate-600 dark:text-slate-300"
                }`}>{comp.status}</span>
            </div>
            <p className="text-xs text-slate-600 dark:text-gray-300 mb-3">{comp.summary}</p>
            {comp.details.length > 0 && (
                <div className="space-y-1.5">
                    {comp.details.map((detail, i) => (
                        <div key={i} className="flex items-start gap-2 text-[11px]">
                            <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0 ${
                                detail.passed === true ? "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300" :
                                detail.passed === false ? "bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300" :
                                "bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-300"
                            }`}>{detail.step}</span>
                            <div className="flex-1 min-w-0">
                                <p className="font-medium text-slate-800 dark:text-gray-200">{detail.action}</p>
                                <p className="text-slate-500 dark:text-gray-400">{detail.description}</p>
                                <p className={`mt-0.5 ${
                                    detail.passed === true ? "text-emerald-600 dark:text-emerald-400" :
                                    detail.passed === false ? "text-red-600 dark:text-red-400" :
                                    "text-slate-600 dark:text-gray-300"
                                }`}>→ {detail.outcome}</p>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function XAIPanel({ explanations, skipped }: { explanations: XAIDocExplanation[]; skipped?: boolean }) {
    if (skipped) return (
        <div className="glass-panel rounded-xl p-8 text-center">
            <span className="text-3xl block mb-3">📊</span>
            <p className="text-sm font-medium text-slate-600 dark:text-gray-300 mb-1">Component Explanations Skipped</p>
            <p className="text-xs text-slate-400 dark:text-gray-500">Enable XAI in Pipeline Options to see how AHMN, IDPO, and Guardrails processed your documents</p>
        </div>
    );
    if (explanations.length === 0) return <div className="glass-panel rounded-xl p-8 text-center text-slate-400 dark:text-gray-500 text-sm">No component explanations available</div>;

    return (
        <div className="space-y-4">
            {explanations.map((xai) => (
                <div key={xai.document_id} className="glass-panel rounded-xl p-4">
                    <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-200 dark:border-gray-700">
                        <div className="flex items-center gap-2">
                            <span className="text-base">📄</span>
                            <p className="text-sm font-medium text-slate-900 dark:text-white">Doc: {xai.document_id.slice(0, 12)}...</p>
                        </div>
                        {!xai.error && (
                            <span className="px-2.5 py-1 bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/20 text-violet-700 dark:text-violet-300 rounded-full text-[10px] font-semibold">
                                {(xai.confidence * 100).toFixed(0)}% overall confidence
                            </span>
                        )}
                    </div>

                    {xai.error ? (
                        <div className="p-3 bg-amber-50/50 dark:bg-amber-500/5 rounded-lg border border-amber-200 dark:border-amber-500/10">
                            <p className="text-xs text-amber-600 dark:text-amber-400">{xai.error}</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {/* Summary */}
                            <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                                <p className="text-xs text-slate-700 dark:text-gray-300">{xai.answer}</p>
                            </div>

                            {/* Component Explanations */}
                            {xai.component_explanations && xai.component_explanations.length > 0 ? (
                                <div className="space-y-3">
                                    {xai.component_explanations.map((comp, i) => (
                                        <ComponentCard key={i} comp={comp} />
                                    ))}
                                </div>
                            ) : (
                                /* Fallback for old format without component_explanations */
                                <div className="p-3 bg-violet-50/30 dark:bg-violet-500/5 rounded-lg border border-violet-100 dark:border-violet-500/10">
                                    <p className="text-[10px] font-semibold text-violet-600 dark:text-violet-400 uppercase tracking-wider mb-1.5">Analysis</p>
                                    <p className="text-xs text-slate-700 dark:text-gray-300 leading-relaxed">{xai.answer}</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
}

function FeedbackPanel({ feedback }: { feedback: PipelineIntegration["ahmn_feedback"] }) {
    const statusColor = feedback.status === "logged"
        ? "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-300"
        : feedback.status === "failed"
            ? "bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-300"
            : "bg-slate-100 dark:bg-gray-800 border-slate-200 dark:border-gray-700 text-slate-600 dark:text-gray-300";
    return (
        <div className="glass-panel rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2"><span className="text-lg">�</span><p className="text-sm font-semibold text-slate-900 dark:text-white">AHMN Learning Feedback</p></div>
                <span className={`px-2.5 py-1 rounded-full text-[10px] font-medium border ${statusColor}`}>{feedback.status.toUpperCase()}</span>
            </div>
            {feedback.error && (
                <div className="p-3 bg-amber-50/50 dark:bg-amber-500/5 rounded-lg border border-amber-200 dark:border-amber-500/10">
                    <p className="text-xs text-amber-600 dark:text-amber-400">{feedback.error}</p>
                </div>
            )}
            {feedback.status === "logged" && (
                <>
                    <div className="grid grid-cols-3 gap-3">
                        <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">F1 Score</p>
                            <p className="text-lg font-bold text-slate-900 dark:text-white">{feedback.metrics_sent.f1_score ? `${(feedback.metrics_sent.f1_score * 100).toFixed(1)}%` : "—"}</p>
                        </div>
                        <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Precision</p>
                            <p className="text-lg font-bold text-slate-900 dark:text-white">{feedback.metrics_sent.precision != null ? `${(feedback.metrics_sent.precision * 100).toFixed(1)}%` : "—"}</p>
                        </div>
                        <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Recall</p>
                            <p className="text-lg font-bold text-slate-900 dark:text-white">{feedback.metrics_sent.recall != null ? `${(feedback.metrics_sent.recall * 100).toFixed(1)}%` : "—"}</p>
                        </div>
                        <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Processing Time</p>
                            <p className="text-lg font-bold text-slate-900 dark:text-white">{feedback.metrics_sent.processing_time_ms ? `${(feedback.metrics_sent.processing_time_ms / 1000).toFixed(1)}s` : "—"}</p>
                        </div>
                        <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Success</p>
                            <p className="text-lg font-bold text-slate-900 dark:text-white">{feedback.metrics_sent.success !== undefined ? (feedback.metrics_sent.success ? "Yes ✓" : "No ✕") : "—"}</p>
                        </div>
                        <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Policy Used</p>
                            <p className="text-sm font-medium text-slate-900 dark:text-white font-mono truncate">{feedback.policy_id_used || "—"}</p>
                        </div>
                    </div>
                    <div className="p-3 bg-emerald-50/30 dark:bg-emerald-500/5 rounded-lg border border-emerald-100 dark:border-emerald-500/10">
                        <div className="flex items-start gap-2">
                            <svg className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                            <div>
                                <p className="text-xs font-medium text-emerald-700 dark:text-emerald-300">Bandit Updated</p>
                                <p className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-0.5">
                                    AHMN has updated its Thompson Sampling posteriors based on this outcome. Future advice for similar documents will reflect this learning.
                                </p>
                            </div>
                        </div>
                    </div>
                </>
            )}
            {feedback.status === "skipped" && (
                <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                    <p className="text-xs text-slate-500 dark:text-gray-400">No feedback was sent because AHMN advice was not available for this run.</p>
                </div>
            )}
        </div>
    );
}

/* ══════════════════════════════════════════════════════════════════════════ */
/*  Document Card (enhanced with inline integration data)                   */
/* ══════════════════════════════════════════════════════════════════════════ */

function DocCard({ doc, expanded, onToggle, guardrail, xai }: {
    doc: IDPODocRecord; expanded: boolean; onToggle: () => void;
    guardrail?: GuardrailDocResult; xai?: XAIDocExplanation;
}) {
    const statusColor = doc.status === "success"
        ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/20"
        : doc.status === "error"
            ? "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-300 border-red-200 dark:border-red-500/20"
            : "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/20";

    const entityDetails: IDPOEntityDetail[] = doc.entity_details || [];
    const explicitEntities = entityDetails.filter(e => e.is_explicit);
    const topEntities = explicitEntities.length > 0 ? explicitEntities.slice(0, 3) : entityDetails.slice(0, 3);

    const qualityScore = typeof doc.quality_score === "number" ? doc.quality_score : null;
    const complexityScore = typeof doc.complexity_score === "number" ? doc.complexity_score : null;

    const sourceIcon = (src: string) => {
        if (src === "llm_cloud" || src === "llm_local") return "🤖";
        if (src === "rule" || src === "schema_regex") return "📐";
        if (src === "generic_kv") return "🔑";
        if (src === "schema_match") return "🔗";
        if (src === "policy") return "📋";
        return "⚡";
    };

    const confidenceColor = (conf: number) => {
        if (conf >= 0.8) return "bg-emerald-500";
        if (conf >= 0.6) return "bg-brand-500";
        if (conf >= 0.4) return "bg-amber-500";
        return "bg-red-500";
    };

    const confidenceLabel = (conf: number) => {
        if (conf >= 0.8) return "High";
        if (conf >= 0.6) return "Medium";
        if (conf >= 0.4) return "Low";
        return "Very Low";
    };

    return (
        <div className="glass-panel rounded-xl overflow-hidden transition-all duration-200 hover:shadow-lg hover:shadow-brand-500/5">
            {/* ── Card Header (always visible) ── */}
            <button onClick={onToggle} className="w-full px-5 py-4 text-left hover:bg-white/40 dark:hover:bg-gray-800/30 transition-colors">
                <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-100 to-cyan-100 dark:from-brand-500/10 dark:to-cyan-500/10 border border-brand-200/50 dark:border-brand-500/20 flex items-center justify-center flex-shrink-0">
                            <span className="text-lg">📄</span>
                        </div>
                        <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                                <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{doc.filename || doc.source || doc.doc_id}</p>
                                {doc.source && <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-gray-800 rounded text-[9px] font-medium text-slate-500 dark:text-gray-400 flex-shrink-0 uppercase">{doc.source}</span>}
                            </div>
                            {/* Mini entity preview in collapsed state */}
                            {!expanded && topEntities.length > 0 && (
                                <div className="flex items-center gap-2 mt-1 flex-wrap">
                                    {topEntities.map((e, i) => (
                                        <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 bg-brand-50/60 dark:bg-brand-500/5 rounded text-[10px] border border-brand-100/60 dark:border-brand-500/10">
                                            <span className="text-slate-400 dark:text-gray-500">{e.label || e.key}:</span>
                                            <span className="font-medium text-slate-700 dark:text-gray-200 max-w-[120px] truncate">{e.value}</span>
                                        </span>
                                    ))}
                                    {entityDetails.length > 3 && (
                                        <span className="text-[10px] text-slate-400 dark:text-gray-500">+{entityDetails.length - 3} more</span>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                        {guardrail && !guardrail.error && (
                            <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] ${guardrail.overall_passes ? "bg-emerald-100 dark:bg-emerald-500/10 ring-1 ring-emerald-200 dark:ring-emerald-500/20" : "bg-red-100 dark:bg-red-500/10 ring-1 ring-red-200 dark:ring-red-500/20"}`} title={guardrail.overall_passes ? "Guardrails passed" : "Guardrails failed"}>🛡️</span>
                        )}
                        {xai && !xai.error && <span className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] bg-violet-100 dark:bg-violet-500/10 ring-1 ring-violet-200 dark:ring-violet-500/20" title="XAI explanation available">�</span>}
                        {entityDetails.length > 0 && (
                            <span className="px-2 py-1 bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 rounded-full text-[10px] font-semibold">
                                {entityDetails.length} field{entityDetails.length !== 1 ? "s" : ""}
                            </span>
                        )}
                        {(doc.category || doc.doc_type) && (
                            <span className="px-2.5 py-1 bg-slate-100 dark:bg-gray-800 text-slate-600 dark:text-gray-300 rounded-full text-[10px] font-medium border border-slate-200 dark:border-gray-700">{doc.category || doc.doc_type}</span>
                        )}
                        <span className={`px-2.5 py-1 rounded-full text-[10px] font-medium border ${statusColor}`}>{doc.status || "processed"}</span>
                        <svg className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>
                    </div>
                </div>
            </button>

            {/* ── Expanded Content ── */}
            {expanded && (
                <div className="px-5 pb-5 border-t border-slate-100 dark:border-gray-800 pt-4 space-y-4">

                    {/* Document Overview Row */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {qualityScore !== null && (
                            <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-xl border border-slate-200 dark:border-gray-700">
                                <p className="text-[10px] font-semibold text-slate-400 dark:text-gray-500 uppercase tracking-wider mb-1.5">Quality</p>
                                <div className="flex items-center gap-2">
                                    <span className="text-lg font-bold text-slate-900 dark:text-white">{(qualityScore * 100).toFixed(0)}%</span>
                                    <div className="flex-1 h-2 bg-slate-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                        <div className={`h-full rounded-full transition-all ${qualityScore >= 0.7 ? "bg-emerald-500" : qualityScore >= 0.4 ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${qualityScore * 100}%` }} />
                                    </div>
                                </div>
                            </div>
                        )}
                        {complexityScore !== null && (
                            <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-xl border border-slate-200 dark:border-gray-700">
                                <p className="text-[10px] font-semibold text-slate-400 dark:text-gray-500 uppercase tracking-wider mb-1.5">Complexity</p>
                                <div className="flex items-center gap-2">
                                    <span className="text-lg font-bold text-slate-900 dark:text-white">{(complexityScore * 100).toFixed(0)}%</span>
                                    <div className="flex-1 h-2 bg-slate-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                        <div className={`h-full rounded-full transition-all ${complexityScore <= 0.3 ? "bg-emerald-500" : complexityScore <= 0.6 ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${complexityScore * 100}%` }} />
                                    </div>
                                </div>
                            </div>
                        )}
                        <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-xl border border-slate-200 dark:border-gray-700">
                            <p className="text-[10px] font-semibold text-slate-400 dark:text-gray-500 uppercase tracking-wider mb-1.5">Entities</p>
                            <div className="flex items-baseline gap-1.5">
                                <span className="text-lg font-bold text-slate-900 dark:text-white">{doc.entity_count || entityDetails.length}</span>
                                <span className="text-[10px] text-slate-400 dark:text-gray-500">
                                    ({doc.explicit_entity_count || explicitEntities.length} targeted)
                                </span>
                            </div>
                        </div>
                        <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-xl border border-slate-200 dark:border-gray-700">
                            <p className="text-[10px] font-semibold text-slate-400 dark:text-gray-500 uppercase tracking-wider mb-1.5">Processing</p>
                            <div className="flex flex-wrap gap-1">
                                {doc.preprocess_route ? doc.preprocess_route.split(",").filter(Boolean).map((step, i) => (
                                    <span key={i} className="px-1.5 py-0.5 bg-slate-200 dark:bg-gray-700 rounded text-[9px] font-medium text-slate-600 dark:text-gray-300">{step}</span>
                                )) : <span className="text-[10px] text-slate-400 dark:text-gray-500">—</span>}
                            </div>
                        </div>
                    </div>

                    {/* Profile Tags */}
                    {(doc.quality_bin || doc.complexity_bin || doc.content_profile || doc.vendor_cluster) && (
                        <div className="flex flex-wrap gap-1.5">
                            {doc.quality_bin && (
                                <span className={`px-2 py-1 rounded-lg text-[10px] font-medium border ${doc.quality_bin === "high" ? "bg-emerald-50 dark:bg-emerald-500/5 border-emerald-200 dark:border-emerald-500/10 text-emerald-700 dark:text-emerald-300" : doc.quality_bin === "low" ? "bg-red-50 dark:bg-red-500/5 border-red-200 dark:border-red-500/10 text-red-700 dark:text-red-300" : "bg-amber-50 dark:bg-amber-500/5 border-amber-200 dark:border-amber-500/10 text-amber-700 dark:text-amber-300"}`}>
                                    Quality: {doc.quality_bin}
                                </span>
                            )}
                            {doc.complexity_bin && (
                                <span className={`px-2 py-1 rounded-lg text-[10px] font-medium border ${doc.complexity_bin === "low" ? "bg-emerald-50 dark:bg-emerald-500/5 border-emerald-200 dark:border-emerald-500/10 text-emerald-700 dark:text-emerald-300" : doc.complexity_bin === "high" ? "bg-red-50 dark:bg-red-500/5 border-red-200 dark:border-red-500/10 text-red-700 dark:text-red-300" : "bg-amber-50 dark:bg-amber-500/5 border-amber-200 dark:border-amber-500/10 text-amber-700 dark:text-amber-300"}`}>
                                    Complexity: {doc.complexity_bin}
                                </span>
                            )}
                            {doc.content_profile && (
                                <span className="px-2 py-1 rounded-lg text-[10px] font-medium border bg-slate-50 dark:bg-gray-800/50 border-slate-200 dark:border-gray-700 text-slate-600 dark:text-gray-300">
                                    Profile: {doc.content_profile}
                                </span>
                            )}
                            {doc.vendor_cluster && (
                                <span className="px-2 py-1 rounded-lg text-[10px] font-medium border bg-violet-50 dark:bg-violet-500/5 border-violet-200 dark:border-violet-500/10 text-violet-700 dark:text-violet-300">
                                    Vendor: {doc.vendor_cluster}
                                </span>
                            )}
                            {doc.model_used && (
                                <span className="px-2 py-1 rounded-lg text-[10px] font-medium border bg-cyan-50 dark:bg-cyan-500/5 border-cyan-200 dark:border-cyan-500/10 text-cyan-700 dark:text-cyan-300">
                                    🤖 {doc.model_used} ({doc.model_mode || "local"})
                                </span>
                            )}
                        </div>
                    )}

                    {/* Summary */}
                    {doc.summary && (
                        <div className="p-4 bg-gradient-to-r from-slate-50 to-gray-50 dark:from-gray-800/50 dark:to-gray-900/30 rounded-xl border border-slate-200 dark:border-gray-700">
                            <div className="flex items-center gap-2 mb-2">
                                <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h7" /></svg>
                                <p className="text-[10px] font-semibold text-slate-400 dark:text-gray-500 uppercase tracking-wider">Document Summary</p>
                            </div>
                            <p className="text-xs text-slate-700 dark:text-gray-300 leading-relaxed">{doc.summary}</p>
                        </div>
                    )}

                    {/* Extracted Entities — show top 3, collapse rest */}
                    {entityDetails.length > 0 && (
                        <div className="p-4 bg-gradient-to-br from-brand-50/40 to-cyan-50/30 dark:from-brand-500/5 dark:to-cyan-500/5 rounded-xl border border-brand-100 dark:border-brand-500/10">
                            <div className="flex items-center justify-between mb-3">
                                <div className="flex items-center gap-2">
                                    <svg className="w-4 h-4 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" /></svg>
                                    <p className="text-[11px] font-semibold text-brand-700 dark:text-brand-300 uppercase tracking-wider">Extracted Fields</p>
                                </div>
                                <span className="text-[10px] text-brand-500 dark:text-brand-400">{entityDetails.length} total</span>
                            </div>
                            <div className="space-y-2">
                                {entityDetails.slice(0, 3).map((entity, i) => (
                                    <div key={i} className="flex items-center gap-3 px-3 py-2.5 bg-white/70 dark:bg-gray-800/50 rounded-lg border border-white dark:border-gray-700/50 hover:border-brand-200 dark:hover:border-brand-500/20 transition-colors group">
                                        <span className="text-sm flex-shrink-0" title={entity.source}>{sourceIcon(entity.source)}</span>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <span className="text-[10px] font-semibold text-slate-500 dark:text-gray-400 uppercase tracking-wide">{entity.label || entity.key}</span>
                                                {entity.is_explicit && (
                                                    <span className="px-1 py-0.5 bg-brand-100 dark:bg-brand-500/10 rounded text-[8px] font-bold text-brand-600 dark:text-brand-400">TARGETED</span>
                                                )}
                                                {entity.page != null && (
                                                    <span className="text-[9px] text-slate-400 dark:text-gray-500">p.{entity.page}</span>
                                                )}
                                            </div>
                                            <p className="text-sm font-medium text-slate-900 dark:text-white mt-0.5 truncate">{entity.value}</p>
                                        </div>
                                        <div className="flex-shrink-0 w-20 text-right">
                                            <div className="flex items-center gap-1.5 justify-end">
                                                <div className="w-12 h-1.5 bg-slate-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                                    <div className={`h-full rounded-full transition-all ${confidenceColor(entity.confidence)}`} style={{ width: `${entity.confidence * 100}%` }} />
                                                </div>
                                                <span className={`text-[10px] font-semibold ${entity.confidence >= 0.7 ? "text-emerald-600 dark:text-emerald-400" : entity.confidence >= 0.5 ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400"}`}>
                                                    {(entity.confidence * 100).toFixed(0)}%
                                                </span>
                                            </div>
                                            <span className="text-[9px] text-slate-400 dark:text-gray-500 hidden group-hover:block">{confidenceLabel(entity.confidence)}</span>
                                        </div>
                                    </div>
                                ))}
                                {entityDetails.length > 3 && (
                                    <details className="group/entities">
                                        <summary className="flex items-center justify-center gap-2 cursor-pointer py-2 px-3 rounded-lg bg-white/50 dark:bg-gray-800/30 border border-brand-100 dark:border-brand-500/10 hover:bg-brand-50/50 dark:hover:bg-brand-500/10 transition-colors">
                                            <svg className="w-3.5 h-3.5 text-brand-500 transition-transform group-open/entities:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                                            <span className="text-[11px] font-medium text-brand-600 dark:text-brand-400">
                                                Show {entityDetails.length - 3} more field{entityDetails.length - 3 !== 1 ? "s" : ""}
                                            </span>
                                        </summary>
                                        <div className="mt-2 space-y-2">
                                            {entityDetails.slice(3).map((entity, i) => (
                                                <div key={i + 3} className="flex items-center gap-3 px-3 py-2.5 bg-white/70 dark:bg-gray-800/50 rounded-lg border border-white dark:border-gray-700/50 hover:border-brand-200 dark:hover:border-brand-500/20 transition-colors group">
                                                    <span className="text-sm flex-shrink-0" title={entity.source}>{sourceIcon(entity.source)}</span>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-[10px] font-semibold text-slate-500 dark:text-gray-400 uppercase tracking-wide">{entity.label || entity.key}</span>
                                                            {entity.is_explicit && (
                                                                <span className="px-1 py-0.5 bg-brand-100 dark:bg-brand-500/10 rounded text-[8px] font-bold text-brand-600 dark:text-brand-400">TARGETED</span>
                                                            )}
                                                            {entity.page != null && (
                                                                <span className="text-[9px] text-slate-400 dark:text-gray-500">p.{entity.page}</span>
                                                            )}
                                                        </div>
                                                        <p className="text-sm font-medium text-slate-900 dark:text-white mt-0.5 truncate">{entity.value}</p>
                                                    </div>
                                                    <div className="flex-shrink-0 w-20 text-right">
                                                        <div className="flex items-center gap-1.5 justify-end">
                                                            <div className="w-12 h-1.5 bg-slate-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                                                <div className={`h-full rounded-full transition-all ${confidenceColor(entity.confidence)}`} style={{ width: `${entity.confidence * 100}%` }} />
                                                            </div>
                                                            <span className={`text-[10px] font-semibold ${entity.confidence >= 0.7 ? "text-emerald-600 dark:text-emerald-400" : entity.confidence >= 0.5 ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400"}`}>
                                                                {(entity.confidence * 100).toFixed(0)}%
                                                            </span>
                                                        </div>
                                                        <span className="text-[9px] text-slate-400 dark:text-gray-500 hidden group-hover:block">{confidenceLabel(entity.confidence)}</span>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </details>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Fallback: show entities from flat dict if entity_details is empty */}
                    {entityDetails.length === 0 && doc.entities && Object.keys(doc.entities).length > 0 && (
                        <div className="p-4 bg-brand-50/30 dark:bg-brand-500/5 rounded-xl border border-brand-100 dark:border-brand-500/10">
                            <p className="text-[10px] font-semibold text-brand-600 dark:text-brand-400 uppercase tracking-wider mb-2">Extracted Fields</p>
                            <div className="grid grid-cols-2 gap-2">
                                {Object.entries(doc.entities).map(([k, v]) => (
                                    <div key={k} className="p-2 bg-white/50 dark:bg-gray-800/30 rounded-lg">
                                        <span className="text-[10px] text-slate-400 dark:text-gray-500 block">{k}</span>
                                        <span className="text-xs font-medium text-slate-800 dark:text-gray-200">{String(v)}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Validation Issues */}
                    {doc.validation_issues && doc.validation_issues.length > 0 && (
                        <div className="p-3 bg-amber-50/50 dark:bg-amber-500/5 rounded-xl border border-amber-200 dark:border-amber-500/10">
                            <div className="flex items-center gap-2 mb-2">
                                <span className="text-sm">⚠️</span>
                                <p className="text-[10px] font-semibold text-amber-600 dark:text-amber-400 uppercase tracking-wider">
                                    {doc.validation_issues.length} Validation Issue{doc.validation_issues.length !== 1 ? "s" : ""}
                                </p>
                            </div>
                            <div className="space-y-1">
                                {doc.validation_issues.map((vi, i) => (
                                    <div key={i} className="flex items-center gap-2 px-2 py-1.5 bg-white/50 dark:bg-gray-800/30 rounded-lg">
                                        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${vi.severity === "high" ? "bg-red-500" : vi.severity === "medium" ? "bg-amber-500" : "bg-slate-400"}`} />
                                        <span className="text-[10px] font-medium text-slate-600 dark:text-gray-300">{vi.field}:</span>
                                        <span className="text-[10px] text-slate-500 dark:text-gray-400 truncate">{vi.issue}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Recovered Fields */}
                    {doc.recovered_fields && Object.keys(doc.recovered_fields).length > 0 && (
                        <div className="p-3 bg-emerald-50/50 dark:bg-emerald-500/5 rounded-xl border border-emerald-200 dark:border-emerald-500/10">
                            <div className="flex items-center gap-2 mb-2">
                                <span className="text-sm">🔧</span>
                                <p className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">Recovered Fields</p>
                            </div>
                            <div className="grid grid-cols-2 gap-1.5">
                                {Object.entries(doc.recovered_fields).map(([k, v]) => (
                                    <div key={k} className="p-2 bg-white/50 dark:bg-gray-800/30 rounded-lg">
                                        <span className="text-[10px] text-emerald-600 dark:text-emerald-400 block">{k}</span>
                                        <span className="text-xs font-medium text-slate-800 dark:text-gray-200">{String(v)}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Sections */}
                    {doc.sections && doc.sections.length > 0 && (
                        <details className="group">
                            <summary className="flex items-center gap-2 cursor-pointer hover:text-slate-600 dark:hover:text-gray-300 transition-colors">
                                <svg className="w-3.5 h-3.5 text-slate-400 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                                <span className="text-[10px] font-semibold text-slate-400 dark:text-gray-500 uppercase tracking-wider">Document Sections ({doc.sections.length})</span>
                            </summary>
                            <div className="mt-2 space-y-1.5">
                                {doc.sections.map((section, i) => (
                                    <div key={i} className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                                        <div className="flex items-center justify-between mb-1">
                                            <p className="text-[11px] font-semibold text-slate-700 dark:text-gray-200">{section.name}</p>
                                            <span className="text-[9px] text-slate-400">{(section.confidence * 100).toFixed(0)}%</span>
                                        </div>
                                        <p className="text-[10px] text-slate-500 dark:text-gray-400 line-clamp-2">{section.text}</p>
                                    </div>
                                ))}
                            </div>
                        </details>
                    )}

                    {/* Extracted Full Text Preview */}
                    {doc.extracted_text && (
                        <details className="group">
                            <summary className="flex items-center gap-2 cursor-pointer hover:text-slate-600 dark:hover:text-gray-300 transition-colors">
                                <svg className="w-3.5 h-3.5 text-slate-400 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                                <span className="text-[10px] font-semibold text-slate-400 dark:text-gray-500 uppercase tracking-wider">Extracted Text</span>
                                <span className="text-[9px] text-slate-400 dark:text-gray-500">({doc.extracted_text.length.toLocaleString()} chars)</span>
                            </summary>
                            <div className="mt-2 p-4 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700 max-h-[300px] overflow-y-auto">
                                <div className="flex justify-end mb-2">
                                    <button
                                        onClick={() => navigator.clipboard.writeText(doc.extracted_text || "")}
                                        className="px-2 py-1 bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 rounded text-[9px] font-medium hover:bg-brand-100 dark:hover:bg-brand-500/20 transition-colors"
                                    >
                                        📋 Copy
                                    </button>
                                </div>
                                <p className="text-[11px] text-slate-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">{doc.extracted_text}</p>
                            </div>
                        </details>
                    )}

                    {/* Inline Guardrails */}
                    {guardrail && !guardrail.error && (
                        <div className={`p-3 rounded-xl border ${guardrail.overall_passes ? "bg-emerald-50/30 dark:bg-emerald-500/5 border-emerald-200 dark:border-emerald-500/10" : "bg-red-50/30 dark:bg-red-500/5 border-red-200 dark:border-red-500/10"}`}>
                            <div className="flex items-center justify-between mb-2">
                                <p className={`text-[10px] font-semibold uppercase tracking-wider ${guardrail.overall_passes ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                                    🛡️ Guardrails: {guardrail.overall_passes ? "PASSED" : "FAILED"}
                                </p>
                                <span className="text-[9px] text-slate-400">{(guardrail.processing_time_ms / 1000).toFixed(1)}s</span>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                                {guardrail.validation_results.map((vr, i) => (
                                    <span key={i} className={`px-2 py-0.5 rounded text-[9px] font-medium ${vr.is_pass ? "bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-300"}`}>
                                        {vr.name}: {(vr.score * 100).toFixed(0)}%
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Inline Component Explanations */}
                    {xai && !xai.error && (
                        <details className="group">
                            <summary className="flex items-center gap-2 cursor-pointer hover:text-slate-600 dark:hover:text-gray-300 transition-colors">
                                <svg className="w-3.5 h-3.5 text-violet-400 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                                <span className="text-[10px] font-semibold text-violet-600 dark:text-violet-400 uppercase tracking-wider">📊 Component Explanations</span>
                                <span className="text-[9px] text-violet-500">{(xai.confidence * 100).toFixed(0)}% confident</span>
                            </summary>
                            <div className="mt-2 space-y-2">
                                <p className="text-xs text-slate-700 dark:text-gray-300 p-2 bg-slate-50 dark:bg-gray-800/50 rounded-lg">{xai.answer}</p>
                                {xai.component_explanations && xai.component_explanations.map((comp, i) => (
                                    <div key={i} className={`p-2.5 rounded-lg border-l-2 ${
                                        comp.status === "success" ? "border-l-emerald-500 bg-emerald-50/30 dark:bg-emerald-500/5" :
                                        comp.status === "warning" ? "border-l-amber-500 bg-amber-50/30 dark:bg-amber-500/5" :
                                        comp.status === "error" ? "border-l-red-500 bg-red-50/30 dark:bg-red-500/5" :
                                        "border-l-slate-400 bg-slate-50/30 dark:bg-slate-500/5"
                                    }`}>
                                        <div className="flex items-center gap-1.5 mb-1">
                                            <span className="text-sm">{comp.component === "ahmn" ? "🎯" : comp.component === "idpo" ? "⚙️" : "🛡️"}</span>
                                            <span className="text-[10px] font-semibold text-slate-700 dark:text-gray-200">{comp.title}</span>
                                        </div>
                                        <p className="text-[10px] text-slate-600 dark:text-gray-400">{comp.summary}</p>
                                    </div>
                                ))}
                            </div>
                        </details>
                    )}


                </div>
            )}
        </div>
    );
}

/* ══════════════════════════════════════════════════════════════════════════ */
/*  Formatted Extracted Text (styled page separators)                       */
/* ══════════════════════════════════════════════════════════════════════════ */

function FormattedExtractedText({ text }: { text: string }) {
    const parts = text.split(/(--- Page \d+ ---)/g);
    if (parts.length <= 1) {
        return <pre className="text-xs text-slate-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap font-sans">{text}</pre>;
    }
    return (
        <div className="space-y-0">
            {parts.map((part, i) => {
                const pageMatch = part.match(/^--- Page (\d+) ---$/);
                if (pageMatch) {
                    return (
                        <div key={i} className="flex items-center gap-3 my-4 select-none">
                            <div className="flex-1 h-px bg-gradient-to-r from-transparent via-slate-300 dark:via-gray-600 to-transparent" />
                            <span className="px-3 py-1 bg-slate-100 dark:bg-gray-800 rounded-full text-[10px] font-semibold text-slate-500 dark:text-gray-400 border border-slate-200 dark:border-gray-700 shadow-sm">
                                Page {pageMatch[1]}
                            </span>
                            <div className="flex-1 h-px bg-gradient-to-r from-transparent via-slate-300 dark:via-gray-600 to-transparent" />
                        </div>
                    );
                }
                if (!part.trim()) return null;
                return (
                    <pre key={i} className="text-xs text-slate-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap font-sans">{part}</pre>
                );
            })}
        </div>
    );
}

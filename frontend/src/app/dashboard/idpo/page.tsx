"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type {
    IDPOExtractionField,
    IDPORunResult,
    IDPODocRecord,
    IDPOEntityDetail,
    PipelineIntegration,
    GuardrailDocResult,
    XAIDocExplanation,
    AHMNAdvice,
    AHMNFeedback,
} from "@/types";

function formatPercent(value?: number | null, digits = 0) {
    if (typeof value !== "number" || Number.isNaN(value)) return "-";
    return `${(value * 100).toFixed(digits)}%`;
}

function average(values: Array<number | null | undefined>) {
    const valid = values.filter((value): value is number => typeof value === "number" && !Number.isNaN(value));
    if (valid.length === 0) return null;
    return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function formatPolicyLabel(policyId?: string | null) {
    return (policyId || "default").replace(/_/g, " ").trim();
}

function looksCorruptedText(value?: string | null) {
    if (!value) return true;
    return /Ãƒ|Ã‚|Ã¢|Ã°|Ã¯Â¸/.test(value);
}

function shortToken(label: string) {
    const words = label
        .split(/[\s/+_-]+/)
        .map((word) => word.trim())
        .filter(Boolean);
    if (words.length === 0) return "--";
    if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
    return words.slice(0, 2).map((word) => word[0]?.toUpperCase() || "").join("");
}

function safeIconText(value: string, fallbackLabel: string) {
    return looksCorruptedText(value) ? shortToken(fallbackLabel) : value;
}

export default function IDPOPage() {
    /* Ã¢â€â‚¬Ã¢â€â‚¬ State Ã¢â€â‚¬Ã¢â€â‚¬ */
    const [files, setFiles] = useState<File[]>([]);
    const [fields, setFields] = useState<IDPOExtractionField[]>([]);
    const [newFieldName, setNewFieldName] = useState("");
    const [newFieldDesc, setNewFieldDesc] = useState("");
    const configPath = "configs/idpo_research_config.json";
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [result, setResult] = useState<IDPORunResult | null>(null);
    const [activeTab, setActiveTab] = useState<"documents" | "entities" | "fulltext" | "integration">("documents");
    const [expandedDoc, setExpandedDoc] = useState<string | null>(null);
    const [dragActive, setDragActive] = useState(false);
    const [showConfig, setShowConfig] = useState(false);
    const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
    const [maxCostPerDoc, setMaxCostPerDoc] = useState("");
    const [escalationEnabled, setEscalationEnabled] = useState(true);
    const [elapsedSec, setElapsedSec] = useState(0);
    const elapsedRef = useRef<NodeJS.Timeout | null>(null);
    const [integrationTab, setIntegrationTab] = useState<"advice" | "guardrails" | "xai" | "feedback">("advice");
    const [adaptiveMode, setAdaptiveMode] = useState<"static" | "adaptive_safe">("adaptive_safe");
    const [entitySearch, setEntitySearch] = useState("");
    const [entityConfidenceFilter, setEntityConfidenceFilter] = useState<"all" | "high" | "medium" | "low">("all");
    const [entityPage, setEntityPage] = useState(0);
    const [pairedRunId, setPairedRunId] = useState<string | null>(null);
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
                if (parsed.adaptiveMode === "static" || parsed.adaptiveMode === "adaptive_safe") {
                    setAdaptiveMode(parsed.adaptiveMode);
                }
                if (typeof parsed.maxCostPerDoc === "string") setMaxCostPerDoc(parsed.maxCostPerDoc);
                if (typeof parsed.escalationEnabled === "boolean") setEscalationEnabled(parsed.escalationEnabled);
            }
        } catch { }
    }, []);

    useEffect(() => {
        try {
            localStorage.setItem(
                "idpo_toggles",
                JSON.stringify({ adaptiveMode, maxCostPerDoc, escalationEnabled }),
            );
        } catch { }
    }, [adaptiveMode, maxCostPerDoc, escalationEnabled]);

    // Restore extraction results from sessionStorage on mount
    useEffect(() => {
        try {
            const savedResult = sessionStorage.getItem("idpo_result");
            if (savedResult) {
                const parsed = JSON.parse(savedResult);
                setResult(parsed);
                const savedPairs = sessionStorage.getItem("idpo_last_runs");
                if (savedPairs) {
                    const runs = JSON.parse(savedPairs) as { static?: string; adaptive_safe?: string };
                    const inferredMode = parsed?.run_id && runs?.static === parsed.run_id ? "static" : "adaptive_safe";
                    const counterpart = inferredMode === "static" ? runs?.adaptive_safe : runs?.static;
                    setPairedRunId(counterpart ?? null);
                }
                const savedTab = sessionStorage.getItem("idpo_activeTab");
                if (savedTab) setActiveTab(savedTab as typeof activeTab);
                const savedExpanded = sessionStorage.getItem("idpo_expandedDoc");
                if (savedExpanded) setExpandedDoc(savedExpanded);
            }
        } catch { }
    }, []);

    // Persist extraction results to sessionStorage whenever they change
    useEffect(() => {
        try {
            if (result) {
                sessionStorage.setItem("idpo_result", JSON.stringify(result));
            }
        } catch { }
    }, [result]);

    useEffect(() => {
        try { if (result) sessionStorage.setItem("idpo_activeTab", activeTab); } catch { }
    }, [activeTab, result]);

    useEffect(() => {
        try { if (result && expandedDoc) sessionStorage.setItem("idpo_expandedDoc", expandedDoc); } catch { }
    }, [expandedDoc, result]);

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Drag & drop handlers Ã¢â€â‚¬Ã¢â€â‚¬ */
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

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Field management Ã¢â€â‚¬Ã¢â€â‚¬ */
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

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Elapsed timer Ã¢â€â‚¬Ã¢â€â‚¬ */
    useEffect(() => {
        if (!loading) {
            if (elapsedRef.current) clearInterval(elapsedRef.current);
            return;
        }
        setElapsedSec(0);
        elapsedRef.current = setInterval(() => setElapsedSec((s) => s + 1), 1000);
        return () => { if (elapsedRef.current) clearInterval(elapsedRef.current); };
    }, [loading]);

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Per-document progress simulator Ã¢â€â‚¬Ã¢â€â‚¬ */
    useEffect(() => {
        if (!loading || files.length === 0) {
            if (progressTimerRef.current) clearInterval(progressTimerRef.current);
            return;
        }
        progressStartRef.current = Date.now();
        setDocProgress(files.map((f) => ({ name: f.name, status: "queued" as const })));
        let currentDoc = 0;
        // Cycle through docs with realistic timing
        const baseMs = 2200;
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
    }, [loading, files.length]);

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Download helper Ã¢â€â‚¬Ã¢â€â‚¬ */
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

    const handleDownloadFullExtractedDocs = () => {
        if (!result) return;
        const docsWithText = result.docs.filter((doc) => Boolean(doc.extracted_text?.trim()));
        if (docsWithText.length === 0) {
            setError("No extracted text is available for download");
            return;
        }

        const content = docsWithText.map((doc, index) => {
            const header = [
                `Document ${index + 1}: ${doc.filename || doc.doc_id}`,
                `Doc ID: ${doc.doc_id}`,
                `Policy: ${doc.policy_id || "n/a"}`,
                "",
            ].join("\n");
            return `${header}${doc.extracted_text?.trim() || ""}`;
        }).join("\n\n" + "=".repeat(80) + "\n\n");

        const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${result.run_id.slice(0, 8)}_full_extracted_docs.txt`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    };

    const handleDownloadSingleExtractedDoc = (doc: IDPODocRecord) => {
        const text = doc.extracted_text?.trim();
        if (!text) {
            setError("This document does not have extracted text to download");
            return;
        }

        const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${(doc.filename || doc.doc_id).replace(/\.[^.]+$/, "")}_extracted.txt`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    };

    function validateSelectedFiles() {
        if (files.length === 0) { setError("Please select at least one file"); return false; }

        // Client-side validation
        const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
        const SUPPORTED_EXTS = [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".txt", ".json"];
        for (const file of files) {
            if (file.size > MAX_FILE_SIZE) {
                setError(`File '${file.name}' exceeds 50MB limit (${(file.size / 1024 / 1024).toFixed(1)}MB)`);
                return false;
            }
            const ext = "." + (file.name.split(".").pop()?.toLowerCase() || "");
            if (!SUPPORTED_EXTS.includes(ext)) {
                setError(`Unsupported file type '${ext}'. Supported: ${SUPPORTED_EXTS.join(", ")}`);
                return false;
            }
        }
        return true;
    }

    function buildRunOptions(mode: "static" | "adaptive_safe") {
        const parsedMaxCost = maxCostPerDoc.trim().length > 0 ? Number(maxCostPerDoc) : undefined;
        return {
            adaptiveMode: mode,
            maxCostPerDoc: typeof parsedMaxCost === "number" && Number.isFinite(parsedMaxCost) ? parsedMaxCost : undefined,
            escalationEnabled,
        };
    }

    function rememberRun(runId: string, mode: "static" | "adaptive_safe") {
        try {
            const savedPairs = sessionStorage.getItem("idpo_last_runs");
            const runs = savedPairs ? (JSON.parse(savedPairs) as { static?: string; adaptive_safe?: string }) : {};
            runs[mode] = runId;
            sessionStorage.setItem("idpo_last_runs", JSON.stringify(runs));
            return mode === "static" ? (runs.adaptive_safe ?? null) : (runs.static ?? null);
        } catch {
            return null;
        }
    }

    function cacheRunArtifacts(data: IDPORunResult) {
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

            const adviceId = data.pipeline_integration?.ahmn_advice?.advice_id;
            if (adviceId) {
                sessionStorage.setItem("xai_advice_id", adviceId);
                localStorage.setItem("xai_advice_id", adviceId);
            }
        } catch {
            // storage may be unavailable
        }
    }

    function finalizeVisibleRun(data: IDPORunResult, mode: "static" | "adaptive_safe", overridePairedRunId?: string | null) {
        setDocProgress((prev) => prev.map((d) => ({ ...d, status: "done" as const })));
        setResult(data);
        const counterpartRunId = overridePairedRunId ?? rememberRun(data.run_id, mode);
        setPairedRunId(counterpartRunId ?? null);
        cacheRunArtifacts(data);
        setFiles([]);
        if (fileInputRef.current) fileInputRef.current.value = "";
        setActiveTab("documents");
        if (data.docs?.length > 0) {
            setExpandedDoc(data.docs[0].doc_id);
        }
    }

    function formatPartialFailures(prefix: string, data: IDPORunResult) {
        const partialFailures = data.partial_failures ?? [];
        if (partialFailures.length === 0) {
            return "";
        }
        const failedFiles = partialFailures.map((f: { file: string; error: string }) => f.file).join(", ");
        return `${prefix}: ${partialFailures.length} file(s) failed processing: ${failedFiles}. Successfully processed ${data.docs.length} document(s).`;
    }

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Submit handler Ã¢â€â‚¬Ã¢â€â‚¬ */
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!validateSelectedFiles()) return;

        setLoading(true);
        setError("");
        setResult(null);


        try {
            const data = await api.runIDPO(files, fields, configPath, buildRunOptions(adaptiveMode));
            finalizeVisibleRun(data, adaptiveMode);
            const partialFailureMessage = formatPartialFailures("Current run", data);
            if (partialFailureMessage) setError(partialFailureMessage);
        } catch (err) {

            setDocProgress((prev) => prev.map((d) => d.status === "processing" || d.status === "queued" ? { ...d, status: "error" as const } : d));
            let errorMessage = "Unknown error";
            if (err instanceof Error) {
                if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
                    errorMessage = "Network error Ã¢â‚¬â€ check that all backend services are running";
                } else if (err.message.includes("502")) {
                    errorMessage = "IDPO service is unavailable Ã¢â‚¬â€ make sure the extraction service is running";
                } else if (err.message.includes("504") || err.message.includes("timed out")) {
                    errorMessage = "Processing timed out Ã¢â‚¬â€ try with fewer or smaller documents";
                } else if (err.message.includes("413")) {
                    errorMessage = "File too large Ã¢â‚¬â€ reduce file size and try again";
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

    const handlePairedRun = async () => {
        if (!validateSelectedFiles()) return;

        setLoading(true);
        setError("");
        setResult(null);

        let staticData: IDPORunResult | null = null;

        try {
            staticData = await api.runIDPO(files, fields, configPath, buildRunOptions("static"));
            rememberRun(staticData.run_id, "static");

            const adaptiveData = await api.runIDPO(files, fields, configPath, buildRunOptions("adaptive_safe"));
            rememberRun(adaptiveData.run_id, "adaptive_safe");
            finalizeVisibleRun(adaptiveData, "adaptive_safe", staticData.run_id);

            const warnings = [
                formatPartialFailures("Static run", staticData),
                formatPartialFailures("Adaptive-safe run", adaptiveData),
            ].filter(Boolean);
            if (warnings.length > 0) {
                setError(warnings.join(" "));
            }
        } catch (err) {
            if (staticData) {
                finalizeVisibleRun(staticData, "static");
            }
            setDocProgress((prev) => prev.map((d) => d.status === "processing" || d.status === "queued" ? { ...d, status: "error" as const } : d));
            let errorMessage = "Paired run failed";
            if (err instanceof Error) {
                errorMessage = staticData
                    ? `Adaptive-safe run failed after static completed: ${err.message}`
                    : err.message;
            }
            setError(errorMessage);
        } finally {
            setLoading(false);
            if (progressTimerRef.current) clearInterval(progressTimerRef.current);
        }
    };

    /* Ã¢â€â‚¬Ã¢â€â‚¬ Helpers Ã¢â€â‚¬Ã¢â€â‚¬ */
    const fileIcon = (name: string) => {
        const ext = name.split(".").pop()?.toLowerCase();
        if (ext === "pdf") return "[PDF]";
        if (["png", "jpg", "jpeg", "tiff", "bmp"].includes(ext || "")) return "[IMG]";
        if (ext === "json") return "[JSON]";
        return "[FILE]";
    };

    const integration = result?.pipeline_integration;
    const resultDocs = result?.docs || [];
    const adviceFollowedCount = resultDocs.filter((doc, index) => {
        const advisedPolicy =
            integration?.ahmn_advices?.[index]?.selected_policy_id ||
            integration?.ahmn_advices?.[index]?.policy_id ||
            doc.advisor_recommendation?.policy_id;
        return Boolean(
            doc.policy_id &&
            advisedPolicy &&
            doc.policy_id === advisedPolicy &&
            !doc.fallback_reason &&
            !doc.safety_status?.rollback_triggered,
        );
    }).length;
    const fallbackCount = resultDocs.filter((doc) => Boolean(doc.fallback_reason)).length;
    const rollbackCount = resultDocs.filter((doc) => Boolean(doc.safety_status?.rollback_triggered)).length;
    const reviewCount = resultDocs.filter((doc) => (doc.defer_status || "not_needed") !== "not_needed").length;
    const feedbackLoggedCount = resultDocs.filter((doc) => Boolean(doc.feedback_status?.logged)).length;
    const schemaValidRate = resultDocs.length > 0
        ? resultDocs.filter((doc) => doc.schema_valid === true).length / resultDocs.length
        : null;
    const avgSchemaCoverage = average(resultDocs.map((doc) => doc.schema_coverage));
    const avgGroundingCoverage = average(resultDocs.map((doc) => doc.schema_grounding_coverage));

    return (
        <div className="max-w-7xl 3xl:max-w-[1800px] mx-auto space-y-5">
            {/* Ã¢â€â‚¬Ã¢â€â‚¬ Header Ã¢â€â‚¬Ã¢â€â‚¬ */}
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
                            IDPO Document Journey
                        </h1>
                        <p className="text-slate-500 dark:text-gray-400 mt-1.5 text-sm">
                            Identify documents, retrieve or default a policy, execute the extraction path, evaluate schema quality, and log feedback in one visible IDPO flow.
                        </p>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className="px-3 py-1.5 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 rounded-full text-xs font-medium">
                            Mode: {adaptiveMode}
                        </span>
                        {result && (
                            <span className="px-3 py-1.5 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-300 rounded-full text-xs font-medium">
                                Run: {result.run_id.slice(0, 8)}...
                            </span>
                        )}
                        {result && (
                            <Link
                                href={`/dashboard/idpo/runs/${result.run_id}`}
                                className="px-3 py-1.5 border border-brand-300 dark:border-brand-500/40 text-brand-700 dark:text-brand-300 rounded-full text-xs font-medium hover:bg-brand-50 dark:hover:bg-brand-500/10 transition-colors"
                            >
                                Open This Run
                            </Link>
                        )}
                        {integration && <CycleStatusBadge integration={integration} />}
                    </div>
                </div>
            </div>
            <div className="relative mt-4 rounded-xl border border-brand-200/60 dark:border-brand-500/20 bg-brand-50/60 dark:bg-brand-500/5 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-wider text-brand-700 dark:text-brand-300">IDPO Runtime Path</p>
                <p className="mt-1 text-sm text-slate-700 dark:text-gray-200">
                    Use <span className="font-mono">static</span> or <span className="font-mono">adaptive_safe</span> to compare deterministic routing against fixed AHMN top-1 advice in the same IDPO runtime and evidence path.
                </p>
            </div>

            {/* Runtime quick access */}
            <div className="glass-panel rounded-2xl p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="text-slate-500 dark:text-gray-400 font-medium">Runtime Views:</span>
                    <Link
                        href="/dashboard/idpo/benchmark"
                        className="px-2.5 py-1 rounded-full border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    >
                        Benchmark Results
                    </Link>
                    <Link
                        href="/dashboard/idpo/compare"
                        className="px-2.5 py-1 rounded-full border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    >
                        Compare Runs
                    </Link>
                    {result && (
                        <Link
                            href={`/dashboard/idpo/runs/${result.run_id}`}
                            className="px-2.5 py-1 rounded-full border border-brand-300 dark:border-brand-500/40 text-brand-700 dark:text-brand-300 hover:bg-brand-50 dark:hover:bg-brand-500/10 transition-colors"
                        >
                            Current Run Detail
                        </Link>
                    )}
                    {result && pairedRunId && (
                        <Link
                            href={`/dashboard/idpo/compare?left=${encodeURIComponent(result.run_id)}&right=${encodeURIComponent(pairedRunId)}`}
                            className="px-2.5 py-1 rounded-full border border-emerald-300 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors"
                        >
                            Compare Paired Runs
                        </Link>
                    )}
                </div>
            </div>

            {/* Processing Status Bar */}
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
                            {files.length > 1 && (
                                <p className="mb-2 text-xs text-slate-500 dark:text-gray-400">
                                    Multi-document batches can take several minutes depending on OCR + extraction complexity.
                                </p>
                            )}
                            {/* Pipeline steps visualization */}
                            <div className="flex items-center gap-1 mb-3">
                                {[
                                    { icon: "Ã°Å¸â€œÂ¥", label: "Ingest", delay: "0s" },
                                    { icon: "Ã°Å¸Å½Â¯", label: "Advise", delay: "0.5s" },
                                    { icon: "Ã°Å¸Â§Â ", label: "Extract", delay: "1s" },
                                    { icon: "Ã¢Å“â€¦", label: "Safe Route", delay: "1.5s" },
                                    { icon: "Ã°Å¸â€œË†", label: "Feedback", delay: "2s" },
                                ].map((step, i) => (
                                    <div key={i} className="flex items-center gap-1">
                                        <div className="flex flex-col items-center px-1.5 py-1 rounded-lg" style={{ animation: `pipelineStep 2s ease-in-out ${step.delay} infinite` }}>
                                            <span className="text-xs">{step.icon}</span>
                                            <span className="text-[8px] text-slate-500 dark:text-gray-400 font-medium">{step.label}</span>
                                        </div>
                                        {i < 4 && (
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
                                    width: `${Math.min(95, (elapsedSec / 12) * 100)}%`,
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

            {/* Ã¢â€â‚¬Ã¢â€â‚¬ Main content grid Ã¢â€â‚¬Ã¢â€â‚¬ */}
            <div className="grid gap-5 lg:grid-cols-5">
                {/* Ã¢â€â‚¬Ã¢â€â‚¬ Upload Panel (2 cols) Ã¢â€â‚¬Ã¢â€â‚¬ */}
                <div className="lg:col-span-2 space-y-4">
                    <form onSubmit={handleSubmit} className="space-y-4">
                        {/* Drop Zone */}
                        <div
                            role="button"
                            tabIndex={0}
                            aria-label="Upload documents Ã¢â‚¬â€ drag and drop or click to browse"
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
                                    {dragActive ? "Drop files here" : "Drag and drop documents"}
                                </p>
                                <p className="text-xs text-slate-400 dark:text-gray-500 mt-1.5">
                                    PDF, PNG, JPG, TIFF, TXT, JSON or click to browse
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
                                                aria-label={`Remove ${file.name}`}
                                                className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 transition-colors text-[11px] font-semibold ml-2">Remove</button>
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
                                            {field.description && <span className="text-[10px] text-slate-400 dark:text-gray-500 truncate">- {field.description}</span>}
                                            <button type="button" onClick={() => removeField(i)}
                                                aria-label={`Remove field ${field.name}`}
                                                className="ml-auto text-slate-400 hover:text-red-500 text-[11px] font-semibold flex-shrink-0">Remove</button>
                                        </div>
                                    ))}
                                </div>
                            )}
                            {fields.length === 0 && (
                                <div className="space-y-2">
                                    <p className="text-[11px] text-slate-500 dark:text-gray-400">
                                        No fields defined. The system will auto-extract detected entities. Add fields below to target specific data.
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

                        {/* Pipeline Options Ã¢â‚¬â€ Upfront Toggles */}
                        <div className="glass-panel rounded-xl p-4 space-y-3">
                            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Pipeline Options</p>
                            <div className="rounded-xl border border-slate-200 dark:border-gray-700 p-3 bg-white/40 dark:bg-gray-800/30">
                                <div className="flex items-center justify-between gap-3 mb-2">
                                    <div>
                                        <p className="text-[11px] font-semibold text-slate-700 dark:text-gray-200">Run Mode</p>
                                        <p className="text-[9px] text-slate-400 dark:text-gray-500">Use the same workflow for deterministic and adaptive-safe processing.</p>
                                    </div>
                                    <span className="px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-[10px] font-medium text-brand-700 dark:text-brand-300">
                                        {adaptiveMode}
                                    </span>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                    {([
                                        {
                                            key: "static" as const,
                                            label: "static",
                                            desc: "Deterministic baseline without AHMN advice.",
                                        },
                                        {
                                            key: "adaptive_safe" as const,
                                            label: "adaptive_safe",
                                            desc: "AHMN top-1 advice with IDPO fallback and rollback.",
                                        },
                                    ]).map((mode) => (
                                        <button
                                            key={mode.key}
                                            type="button"
                                            onClick={() => setAdaptiveMode(mode.key)}
                                            className={`rounded-lg border px-3 py-3 text-left transition-all ${
                                                adaptiveMode === mode.key
                                                    ? "border-brand-300 dark:border-brand-500/30 bg-brand-50 dark:bg-brand-500/10 shadow-sm"
                                                    : "border-slate-200 dark:border-gray-700 bg-white/50 dark:bg-gray-800/40 hover:border-slate-300 dark:hover:border-gray-600"
                                            }`}
                                        >
                                            <p className="text-[11px] font-semibold text-slate-800 dark:text-gray-100">{mode.label}</p>
                                            <p className="mt-1 text-[10px] text-slate-500 dark:text-gray-400">{mode.desc}</p>
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div className="space-y-2">
                                <div className="rounded-lg border border-amber-200/70 bg-amber-50/60 px-3 py-2.5 text-[10px] text-amber-900 dark:border-amber-400/20 dark:bg-amber-500/10 dark:text-amber-100">
                                    Guardrails and XAI are not part of the canonical research runtime. Those legacy toggles were removed from this path.
                                </div>
                            </div>
                            <p className="text-[9px] text-slate-400 dark:text-gray-500 text-center pt-1">
                                Estimated time: ~{adaptiveMode === "adaptive_safe" ? "8-15s" : "5-10s"} per document
                            </p>
                        </div>

                        <button
                            type="button"
                            onClick={() => setShowAdvancedSettings(!showAdvancedSettings)}
                            className="w-full glass-panel rounded-xl px-4 py-3 text-left hover:bg-white/80 dark:hover:bg-gray-800/60 transition-all duration-150"
                        >
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-medium text-slate-600 dark:text-gray-300">Advanced Settings</span>
                                <span className="text-slate-400 text-xs transition-transform duration-150" style={{ transform: showAdvancedSettings ? "rotate(180deg)" : "rotate(0deg)" }}>v</span>
                            </div>
                        </button>
                        {showAdvancedSettings && (
                            <div className="glass-panel rounded-xl p-4 space-y-4">
                                <div className="rounded-lg border border-slate-200/70 dark:border-gray-700/70 bg-white/40 dark:bg-gray-800/20 px-3 py-2.5">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Base Config</p>
                                    <p className="mt-1 text-xs font-mono text-slate-700 dark:text-gray-200">{configPath}</p>
                                    <p className="mt-1 text-[10px] text-slate-400 dark:text-gray-500">Only canonical runtime controls remain here. Dead routing, guardrails, and XAI toggles were removed.</p>
                                </div>
                                <div className="grid gap-3 sm:grid-cols-1">
                                    <label className="block">
                                        <span className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-gray-400">Max Cost Per Doc</span>
                                        <input
                                            type="number"
                                            min="0"
                                            step="0.01"
                                            value={maxCostPerDoc}
                                            onChange={(e) => setMaxCostPerDoc(e.target.value)}
                                            placeholder="Use config default"
                                            className="w-full glass-input px-3 py-2 text-xs rounded-lg"
                                        />
                                    </label>
                                </div>
                                <label className={`flex items-center justify-between rounded-lg border px-3 py-2.5 transition-all duration-150 ${escalationEnabled ? "bg-brand-50/50 dark:bg-brand-500/5 border-brand-200 dark:border-brand-500/20" : "bg-white/30 dark:bg-gray-800/20 border-slate-200/60 dark:border-gray-700/40"}`}>
                                    <div>
                                        <p className="text-[11px] font-semibold text-slate-700 dark:text-gray-200">Escalation</p>
                                        <p className="text-[9px] text-slate-400 dark:text-gray-500">Allow stronger-model escalation when the runtime requests it.</p>
                                    </div>
                                    <div className="relative">
                                        <input type="checkbox" checked={escalationEnabled} onChange={(e) => setEscalationEnabled(e.target.checked)} className="sr-only peer" />
                                        <div className="w-9 h-5 bg-slate-200 dark:bg-gray-700 rounded-full peer peer-checked:bg-brand-500 transition-colors" />
                                        <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow peer-checked:translate-x-4 transition-transform" />
                                    </div>
                                </label>
                            </div>
                        )}

                        {/* Legacy config path control kept hidden for compatibility */}
                        <button type="button" onClick={() => setShowConfig(!showConfig)}
                            className="hidden w-full glass-panel rounded-xl px-4 py-3 text-left hover:bg-white/80 dark:hover:bg-gray-800/60 transition-all duration-150">
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-medium text-slate-600 dark:text-gray-300">Advanced Configuration</span>
                                <span className="text-slate-400 text-xs transition-transform duration-150" style={{ transform: showConfig ? "rotate(180deg)" : "rotate(0deg)" }}>Ã¢â€“Â¼</span>
                            </div>
                        </button>
                        {false && showConfig && (
                            <div className="glass-panel rounded-xl p-4">
                                <label className="block text-xs font-medium text-slate-500 dark:text-gray-400 mb-2">Pipeline Config Path</label>
                                <input type="text" value={configPath} readOnly
                                    className="w-full glass-input px-3 py-2 text-xs rounded-lg" />
                            </div>
                        )}

                        {/* Submit */}
                        <div className="grid gap-2 sm:grid-cols-2">
                            <button type="submit" disabled={loading || files.length === 0}
                                className="w-full rounded-2xl px-4 py-4 text-sm disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2.5 font-bold text-white shadow-lg hover:shadow-xl transition-all duration-200 active:scale-[0.98] bg-gradient-to-r from-brand-500 to-cyan-500 shadow-brand-500/20 hover:shadow-brand-500/30">
                                {loading ? (
                                    <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Processing Pipeline...</>
                                ) : (
                                    <>
                                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                        </svg>
                                        Run {adaptiveMode}
                                    </>
                                )}
                            </button>
                            <button
                                type="button"
                                disabled={loading || files.length === 0}
                                onClick={handlePairedRun}
                                className="w-full rounded-2xl px-4 py-4 text-sm disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2.5 font-bold text-slate-900 dark:text-white shadow-lg hover:shadow-xl transition-all duration-200 active:scale-[0.98] bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                            >
                                {loading ? (
                                    <><div className="w-4 h-4 border-2 border-slate-400/30 border-t-slate-600 dark:border-white/30 dark:border-t-white rounded-full animate-spin" /> Running paired comparison...</>
                                ) : (
                                    <>
                                        <span className="text-base font-semibold">2x</span>
                                        Run static + adaptive_safe
                                    </>
                                )}
                            </button>
                        </div>
                        <p className="text-[10px] text-slate-400 dark:text-gray-500 text-center">
                            Paired run submits the same upload twice and links both runs for comparison and evidence generation.
                        </p>
                    </form>

                    {error && (
                        <div role="alert" aria-live="assertive" className={`glass-panel rounded-xl p-4 border-l-4 ${result && result.docs.length > 0 ? "border-l-amber-500" : "border-l-red-500"}`}>
                            <div className="flex items-start gap-2">
                                <span className="text-sm mt-0.5">{result && result.docs.length > 0 ? "Ã¢Å¡Â Ã¯Â¸Â" : "Ã¢ÂÅ’"}</span>
                                <div>
                                    <p className={`text-xs font-medium ${result && result.docs.length > 0 ? "text-amber-700 dark:text-amber-300" : "text-red-700 dark:text-red-300"}`}>{error}</p>
                                    {result?.partial_failures && result.partial_failures.length > 0 && (
                                        <div className="mt-2 space-y-1">
                                            {result.partial_failures.map((pf, i) => (
                                                <div key={i} className="flex items-start gap-1.5 text-[10px] text-amber-600 dark:text-amber-400">
                                                    <span className="mt-0.5 flex-shrink-0">Ã¢â‚¬Â¢</span>
                                                    <span><span className="font-medium">{pf.file}:</span> {pf.error}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Ã¢â€â‚¬Ã¢â€â‚¬ Multi-Document Progress Tracker Ã¢â€â‚¬Ã¢â€â‚¬ */}
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
                                            {dp.status === "done" && <span className="text-emerald-500 text-sm">Ã¢Å“â€œ</span>}
                                            {dp.status === "processing" && (
                                                <div className="w-4 h-4 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
                                            )}
                                            {dp.status === "error" && <span className="text-red-500 text-sm">Ã¢Å“â€¢</span>}
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

                    {/* Ã¢â€â‚¬Ã¢â€â‚¬ Quick Integration Summary (sidebar) Ã¢â€â‚¬Ã¢â€â‚¬ */}
                    {integration && (() => {
                        // Compute per-doc advice summary
                        const advices = integration.ahmn_advices || [];
                        const feedbacks = integration.ahmn_feedbacks || [];
                        const validAdvices = advices.filter(a => a && !a.error);
                        const avgConfidence = validAdvices.length > 0 ? validAdvices.reduce((sum, a) => sum + (a.confidence || 0), 0) / validAdvices.length : 0;
                        const uniquePolicies = [...new Set(validAdvices.map(a => a.policy_id).filter(Boolean))];
                        const loggedFeedbacks = feedbacks.filter(f => f?.status === "logged");
                        const avgF1 = loggedFeedbacks.length > 0 ? loggedFeedbacks.reduce((sum, f) => sum + (f.metrics_sent?.f1_score || 0), 0) / loggedFeedbacks.length : 0;

                        return (
                            <div className="glass-panel rounded-xl p-4 space-y-3">
                                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Adaptive Routing Summary</p>
                                <div className="space-y-2">
                                    <SummaryRow icon="Ã°Å¸Å½Â¯" label="Top-1 Advice"
                                        value={`${validAdvices.length} doc${validAdvices.length !== 1 ? "s" : ""}`}
                                        status={validAdvices.length > 0}
                                        detail={uniquePolicies.length > 1 ? `${uniquePolicies.length} recommendations, avg ${(avgConfidence * 100).toFixed(0)}%` : validAdvices.length > 0 ? `${uniquePolicies[0] || "default"} (${(avgConfidence * 100).toFixed(0)}%)` : "No advice"} />
                                    <SummaryRow icon="Ã°Å¸Â§Â­" label="Fallback / Safety"
                                        value={`${advices.filter(a => a.fallback_reason || a.safety_status?.rollback_triggered || a.safety_status?.blocked_policy).length} doc${advices.filter(a => a.fallback_reason || a.safety_status?.rollback_triggered || a.safety_status?.blocked_policy).length !== 1 ? "s" : ""}`}
                                        status={advices.some(a => a.selected_policy_id || a.policy_id)}
                                        detail={advices.some(a => a.fallback_reason || a.safety_status?.rollback_triggered || a.safety_status?.blocked_policy) ? "Fallback or rollback recorded" : "No fallback or rollback recorded"} />
                                    <SummaryRow icon="Ã°Å¸â€ºÂ¡Ã¯Â¸Â" label="Guardrails"
                                        value={integration.skipped_guardrails ? "Skipped" : `${integration.guardrails.filter(g => g.overall_passes).length}/${integration.guardrails.length} passed`}
                                        status={integration.skipped_guardrails ? null : integration.guardrails.every(g => g.overall_passes || !!g.error)}
                                        detail={integration.skipped_guardrails ? "Disabled by user" : integration.guardrails.some(g => g.error) ? "Some checks unavailable" : undefined} />
                                    <SummaryRow icon="Ã°Å¸â€œÅ " label="Explanations"
                                        value={integration.skipped_xai ? "Skipped" : `${integration.xai_explanations.filter(x => !x.error).length} docs explained`}
                                        status={integration.skipped_xai ? null : integration.xai_explanations.some(x => !x.error)}
                                        detail={integration.skipped_xai ? "Disabled by user" : integration.xai_explanations.some(x => x.error) ? "Some unavailable" : undefined} />
                                    <SummaryRow icon="Ã°Å¸â€œË†" label="Feedback Logged"
                                        value={`${loggedFeedbacks.length}/${advices.length} logged`}
                                        status={loggedFeedbacks.length > 0}
                                        detail={loggedFeedbacks.length > 0 ? `Avg F1: ${(avgF1 * 100).toFixed(1)}%` : "No feedback logged"} />
                                </div>
                                <div className="pt-2 border-t border-slate-200 dark:border-gray-700">
                                    <p className="text-[10px] text-slate-400 dark:text-gray-500">Cycle time: {(integration.cycle_time_ms / 1000).toFixed(1)}s</p>
                                </div>
                            </div>
                        );
                    })()}
                </div>

                {/* Ã¢â€â‚¬Ã¢â€â‚¬ Results Panel (3 cols) Ã¢â€â‚¬Ã¢â€â‚¬ */}
                <div className="lg:col-span-3 space-y-4">
                    {!result ? (
                        <div className="glass-panel rounded-2xl p-12 text-center">
                            <div className="max-w-sm mx-auto">
                                <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-slate-100 to-slate-50 dark:from-gray-800 dark:to-gray-900 border border-slate-200/60 dark:border-gray-700 flex items-center justify-center mb-5 shadow-inner">
                                    <svg className="w-9 h-9 text-slate-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                                    </svg>
                                </div>
                                <p className="text-lg font-bold text-slate-600 dark:text-gray-300">Ready to run the IDPO journey</p>
                                <p className="text-sm text-slate-400 dark:text-gray-500 mt-2">Upload documents to see identification, policy selection, execution, evaluation, and feedback in one path.</p>
                                <div className="mt-6 grid grid-cols-5 gap-2 stagger-children">
                                    {[
                                        { icon: "Ã°Å¸Å½Â¯", label: "Advise" },
                                        { icon: "Ã¢Å¡â„¢Ã¯Â¸Â", label: "Execute" },
                                        { icon: "Ã°Å¸Â§Â­", label: "Safeguard" },
                                        { icon: "Ã°Å¸â€œË†", label: "Feedback" },
                                    ].map((step) => (
                                        <div key={step.label} className="px-2 py-2.5 bg-slate-50 dark:bg-gray-800/50 rounded-xl border border-slate-200/60 dark:border-gray-700">
                                            <span className="text-sm block mb-0.5 font-semibold text-slate-700 dark:text-slate-200">{safeIconText(step.icon, step.label)}</span>
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
                                            className="px-3 py-1.5 bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 rounded-lg hover:bg-brand-100 dark:hover:bg-brand-500/20 text-xs font-medium transition-all shadow-sm shadow-brand-500/5">Download Results</button>
                                        {result.entities?.length > 0 && (
                                            <button onClick={() => handleDownload("entities.xlsx", "entities.xlsx")}
                                                className="px-3 py-1.5 bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/20 text-violet-700 dark:text-violet-300 rounded-lg hover:bg-violet-100 dark:hover:bg-violet-500/20 text-xs font-medium transition-all shadow-sm shadow-violet-500/5">Download Fields</button>
                                        )}
                                        {result.docs.some((doc) => Boolean(doc.extracted_text?.trim())) && (
                                            <button onClick={handleDownloadFullExtractedDocs}
                                                className="px-3 py-1.5 bg-cyan-50 dark:bg-cyan-500/10 border border-cyan-200 dark:border-cyan-500/20 text-cyan-700 dark:text-cyan-300 rounded-lg hover:bg-cyan-100 dark:hover:bg-cyan-500/20 text-xs font-medium transition-all shadow-sm shadow-cyan-500/5">Download Text</button>
                                        )}
                                    </div>
                                    <div className="hidden">
                                        <button onClick={() => handleDownload("docs.xlsx", "docs.xlsx")}
                                            className="px-3 py-1.5 bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 rounded-lg hover:bg-brand-100 dark:hover:bg-brand-500/20 text-xs font-medium transition-all shadow-sm shadow-brand-500/5">Ã¢â€ â€œ Results</button>
                                        {result.entities?.length > 0 && (
                                            <button onClick={() => handleDownload("entities.xlsx", "entities.xlsx")}
                                                className="px-3 py-1.5 bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/20 text-violet-700 dark:text-violet-300 rounded-lg hover:bg-violet-100 dark:hover:bg-violet-500/20 text-xs font-medium transition-all shadow-sm shadow-violet-500/5">Ã¢â€ â€œ Entities</button>
                                        )}
                                        {result.docs.some((doc) => Boolean(doc.extracted_text?.trim())) && (
                                            <button onClick={handleDownloadFullExtractedDocs}
                                                className="px-3 py-1.5 bg-cyan-50 dark:bg-cyan-500/10 border border-cyan-200 dark:border-cyan-500/20 text-cyan-700 dark:text-cyan-300 rounded-lg hover:bg-cyan-100 dark:hover:bg-cyan-500/20 text-xs font-medium transition-all shadow-sm shadow-cyan-500/5">Ã¢â€ â€œ Full Text</button>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                                <div className="glass-panel rounded-xl p-4">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Advice Followed</p>
                                    <p className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">{adviceFollowedCount}</p>
                                    <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">Documents that stayed on the advised policy.</p>
                                </div>
                                <div className="glass-panel rounded-xl p-4">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Safety + Review</p>
                                    <p className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">
                                        {fallbackCount} fallback / {rollbackCount} rollback / {reviewCount} review
                                    </p>
                                    <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">Fallback, rollback, and defer states across this run.</p>
                                </div>
                                <div className="glass-panel rounded-xl p-4">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Schema Quality</p>
                                    <p className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">{formatPercent(schemaValidRate)} valid</p>
                                    <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">
                                        Coverage {formatPercent(avgSchemaCoverage)} / grounded {formatPercent(avgGroundingCoverage)}
                                    </p>
                                </div>
                                <div className="glass-panel rounded-xl p-4">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Feedback Logged</p>
                                    <p className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">{feedbackLoggedCount}</p>
                                    <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">Completed feedback updates sent back to AHMN.</p>
                                </div>
                            </div>

                            {/* Warnings */}
                            {result.warnings?.length > 0 && (
                                <div className="glass-panel rounded-xl p-4 border-l-4 border-l-amber-500">
                                    <p className="text-xs font-semibold text-amber-700 dark:text-amber-300 mb-1.5">Preflight Warnings</p>
                                    <ul className="space-y-1">
                                        {result.warnings.map((w, i) => (
                                            <li key={i} className="text-xs text-amber-600 dark:text-amber-400 flex items-start gap-1.5">
                                                <span className="mt-0.5">Ã¢Å¡Â </span> {w}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            {/* Tab Bar */}
                            <div className="glass-panel rounded-xl p-1.5 flex gap-1" role="tablist" aria-label="Result views">
                                {(["documents", "integration", "entities", "fulltext"] as const).map((tab) => (
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
                                        {tab === "documents" && `Journey (${result.docs.length})`}
                                        {tab === "entities" && `Fields (${result.entities?.length || 0})`}
                                        {tab === "fulltext" && "Extracted Text"}
                                        {tab === "integration" && "Policy + Feedback"}
                                    </button>
                                ))}
                            </div>

                            {/* Tab Content */}
                            <div className="space-y-3">
                                {activeTab === "documents" && result.docs.map((doc, docIndex) => (
                                    <JourneyDocCard key={doc.doc_id} doc={doc} expanded={expandedDoc === doc.doc_id}
                                        onToggle={() => setExpandedDoc(expandedDoc === doc.doc_id ? null : doc.doc_id)}
                                        guardrail={integration?.guardrails.find(g => g.document_id === doc.doc_id)}
                                        xai={integration?.xai_explanations.find(x => x.document_id === doc.doc_id)}
                                        advice={integration?.ahmn_advices?.[docIndex]}
                                        feedback={integration?.ahmn_feedbacks?.[docIndex]} />
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
                                                            })()})` : f === "high" ? "Ã¢â€°Â¥70%" : f === "medium" ? "50-70%" : "<50%"}
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
                                                        value: e.field_value || e.value || Object.values(e)[1] || "Ã¢â‚¬â€",
                                                        confidence: typeof e.confidence === "number" ? e.confidence : parseFloat(e.field_confidence) || 0,
                                                        source: e.source || e.field_source || "Ã¢â‚¬â€",
                                                        page: e.page,
                                                        is_explicit: false,
                                                        docName: "Ã¢â‚¬â€",
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
                                                                            <td className="px-4 py-2 text-slate-500 dark:text-gray-400 text-[10px]">{entity.source || "Ã¢â‚¬â€"}</td>
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
                                                                        className="px-2 py-1 rounded text-[10px] font-medium border border-slate-200 dark:border-gray-700 text-slate-500 dark:text-gray-400 hover:bg-slate-100 dark:hover:bg-gray-800 disabled:opacity-30 transition-all">Ã¢â€ Â Prev</button>
                                                                    <span className="px-2 py-1 text-[10px] font-semibold text-slate-600 dark:text-gray-300">{currentPage + 1}/{totalPages}</span>
                                                                    <button onClick={() => setEntityPage(Math.min(totalPages - 1, currentPage + 1))} disabled={currentPage >= totalPages - 1}
                                                                        className="px-2 py-1 rounded text-[10px] font-medium border border-slate-200 dark:border-gray-700 text-slate-500 dark:text-gray-400 hover:bg-slate-100 dark:hover:bg-gray-800 disabled:opacity-30 transition-all">Next Ã¢â€ â€™</button>
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
                                            No entities extracted Ã¢â‚¬â€ try adding extraction fields before processing
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
                                                            <span className="text-base">Ã°Å¸â€œâ€ž</span>
                                                            <p className="text-sm font-semibold text-slate-900 dark:text-white">{doc.filename || doc.doc_id}</p>
                                                            {doc.extracted_text && (
                                                                <span className="text-[10px] text-slate-400 dark:text-gray-500">
                                                                    {(doc.extracted_text.match(/--- Page \d+ ---/g) || []).length || 1} page{((doc.extracted_text.match(/--- Page \d+ ---/g) || []).length || 1) !== 1 ? "s" : ""}
                                                                    {" Ã‚Â· "}{doc.extracted_text.length.toLocaleString()} chars
                                                                </span>
                                                            )}
                                                        </div>
                                                        <div className="flex items-center gap-2">
                                                            <button
                                                                onClick={() => handleDownloadSingleExtractedDoc(doc)}
                                                                className="px-3 py-1.5 bg-cyan-50 dark:bg-cyan-500/10 border border-cyan-200 dark:border-cyan-500/20 text-cyan-700 dark:text-cyan-300 rounded-lg hover:bg-cyan-100 dark:hover:bg-cyan-500/20 text-xs font-medium transition-all"
                                                            >
                                                                Ã¢â€ â€œ Download Text
                                                            </button>
                                                            <button
                                                                onClick={() => {
                                                                    navigator.clipboard.writeText(doc.extracted_text || "");
                                                                }}
                                                                className="px-3 py-1.5 bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 rounded-lg hover:bg-brand-100 dark:hover:bg-brand-500/20 text-xs font-medium transition-all"
                                                            >
                                                                Ã°Å¸â€œâ€¹ Copy Text
                                                            </button>
                                                        </div>
                                                    </div>
                                                    <div className="p-5 max-h-[600px] overflow-y-auto">
                                                        <FormattedExtractedText text={doc.extracted_text || "No text extracted for this document."} />
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="glass-panel rounded-xl p-8 text-center text-slate-400 dark:text-gray-500 text-sm">
                                            No extracted text available Ã¢â‚¬â€ text will appear here after processing documents
                                        </div>
                                    )
                                )}

                                {activeTab === "integration" && integration && (
                                    <IntegrationPanel integration={integration} activeSubTab={integrationTab} onSubTabChange={setIntegrationTab} durationMs={result.metrics?.duration_ms} />
                                )}
                                {activeTab === "integration" && !integration && (
                                    <div className="glass-panel rounded-xl p-8 text-center text-slate-400 dark:text-gray-500 text-sm">
                                        No integration data Ã¢â‚¬â€ services may be unavailable
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

/* Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â */
/*  Sub-Components                                                          */
/* Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â */

function CycleStatusBadge({ integration }: { integration: PipelineIntegration }) {
    const safeRoutingOk = integration.ahmn_advices.some((advice) => advice.selected_policy_id || advice.policy_id);
    const stages = [
        { ok: !integration.ahmn_advice.error, label: "A" },
        { ok: safeRoutingOk, label: "S" },
        { ok: integration.guardrails.length === 0 || integration.guardrails.some(g => g.overall_passes), label: "G" },
        { ok: integration.ahmn_feedback.status === "logged", label: "F" },
    ];
    const allOk = stages.every(s => s.ok);
    return (
        <div className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium border ${allOk
            ? "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-300"
            : "bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-300"}`}>
            {stages.map((s, i) => (
                <span key={i} className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold ${s.ok ? "bg-emerald-500 text-white" : "bg-slate-300 dark:bg-gray-600 text-white"}`}>{s.label}</span>
            ))}
            <span className="ml-1">{allOk ? "Adaptive Safe" : "Partial"}</span>
        </div>
    );
}

function SummaryRow({ icon, label, value, status, detail }: { icon: string; label: string; value: string; status: boolean | null; detail?: string }) {
    return (
        <div className="flex items-start gap-2.5 px-3 py-2 bg-white/40 dark:bg-gray-800/30 rounded-lg">
            <span className="text-[11px] font-semibold text-slate-500 dark:text-gray-400 mt-0.5">{safeIconText(icon, label)}</span>
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
        { key: "advice" as const, icon: "Ã°Å¸Å½Â¯", label: "Advisor" },
        { key: "guardrails" as const, icon: "Ã°Å¸â€ºÂ¡Ã¯Â¸Â", label: "Guardrails" },
        { key: "xai" as const, icon: "Ã°Å¸â€œÅ ", label: "Explanations" },
        { key: "feedback" as const, icon: "Ã¯Â¿Â½", label: "Feedback" },
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
            {activeSubTab === "advice" && <AdvicePanel advices={integration.ahmn_advices || []} />}
            {activeSubTab === "guardrails" && <GuardrailsPanel results={integration.guardrails} skipped={integration.skipped_guardrails} />}
            {activeSubTab === "xai" && <XAIPanel explanations={integration.xai_explanations} skipped={integration.skipped_xai} />}
            {activeSubTab === "feedback" && <FeedbackPanel feedbacks={integration.ahmn_feedbacks || []} />}
        </div>
    );
}

function AdvicePanel({ advices }: { advices: AHMNAdvice[] }) {
    if (advices.length === 0) return <div className="glass-panel rounded-xl p-8 text-center text-slate-400 dark:text-gray-500 text-sm">No AHMN advice available</div>;

    const validAdvices = advices.filter(a => a && !a.error);
    const uniquePolicies = [...new Set(validAdvices.map(a => a.policy_id).filter(Boolean))];
    const avgConfidence = validAdvices.length > 0 ? validAdvices.reduce((sum, a) => sum + (a.confidence || 0), 0) / validAdvices.length : 0;

    return (
        <div className="space-y-3">
            {/* Summary Header */}
            <div className="glass-panel rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2"><span className="text-lg">Ã°Å¸Å½Â¯</span><p className="text-sm font-semibold text-slate-900 dark:text-white">Per-Document Top-1 Advice</p></div>
                
                    <span className="px-2.5 py-1 rounded-full text-[10px] font-medium border bg-brand-50 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300">
                        {validAdvices.length} doc{validAdvices.length !== 1 ? "s" : ""} Ã¢â‚¬Â¢ {uniquePolicies.length} polic{uniquePolicies.length !== 1 ? "ies" : "y"}
                    </span>
                </div>
                <div className="grid grid-cols-3 gap-3">
                    <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Avg Confidence</p>
                        <p className="text-sm font-medium text-slate-900 dark:text-white">{(avgConfidence * 100).toFixed(1)}%</p>
                    </div>
                    <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">RABI Used</p>
                        <p className="text-sm font-medium text-slate-900 dark:text-white">{validAdvices.filter(a => a.rabi_used).length}/{validAdvices.length}</p>
                    </div>
                    <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Unique Policies</p>
                        <p className="text-xs font-medium text-slate-900 dark:text-white truncate">{uniquePolicies.join(", ") || "Ã¢â‚¬â€"}</p>
                    </div>
                </div>
            </div>

            {/* Per-Document Advice Cards */}
            {advices.map((advice, idx) => (
                <div key={advice.advice_id || idx} className={`glass-panel rounded-xl p-4 border-l-4 ${advice.error ? "border-l-amber-500" : "border-l-brand-500"}`}>
                    <div className="flex items-center justify-between mb-2">
                        <p className="text-xs font-medium text-slate-900 dark:text-white">Document {idx + 1}</p>
                        {advice.error ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/20">{advice.error}</span>
                        ) : (
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-mono text-slate-600 dark:text-gray-300">{advice.policy_id}</span>
                                <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${advice.confidence >= 0.7 ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-slate-100 dark:bg-gray-700 text-slate-600 dark:text-gray-300"}`}>{(advice.confidence * 100).toFixed(0)}%</span>
                                {advice.rabi_used && <span className="px-1.5 py-0.5 bg-violet-100 dark:bg-violet-500/10 text-violet-700 dark:text-violet-300 rounded text-[9px] font-medium">RABI</span>}
                                <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-gray-700 text-slate-500 dark:text-gray-400 rounded text-[9px]">{advice.retrieval_source}</span>
                            </div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}

function GuardrailsPanel({ results, skipped }: { results: GuardrailDocResult[]; skipped?: boolean }) {
    if (skipped) return (
        <div className="glass-panel rounded-xl p-8 text-center">
            <span className="text-3xl block mb-3">Ã°Å¸â€ºÂ¡Ã¯Â¸Â</span>
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
                            <span className="text-base">Ã°Å¸â€ºÂ¡Ã¯Â¸Â</span>
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
        ahmn: "Ã°Å¸Å½Â¯",
        idpo: "Ã¢Å¡â„¢Ã¯Â¸Â",
        guardrails: "Ã°Å¸â€ºÂ¡Ã¯Â¸Â",
    };
    const bgClass = statusColors[comp.status as keyof typeof statusColors] || statusColors.info;
    const icon = icons[comp.component as keyof typeof icons] || "Ã°Å¸â€œâ€¹";

    return (
        <div className={`rounded-xl border-l-4 p-4 ${bgClass}`}>
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <span className="text-lg">{icon}</span>
                    <p className="text-sm font-semibold text-slate-900 dark:text-white">{comp.title}</p>
                </div>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium uppercase ${comp.status === "success" ? "bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" :
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
                            <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0 ${detail.passed === true ? "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300" :
                                detail.passed === false ? "bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300" :
                                    "bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-300"
                                }`}>{detail.step}</span>
                            <div className="flex-1 min-w-0">
                                <p className="font-medium text-slate-800 dark:text-gray-200">{detail.action}</p>
                                <p className="text-slate-500 dark:text-gray-400">{detail.description}</p>
                                <p className={`mt-0.5 ${detail.passed === true ? "text-emerald-600 dark:text-emerald-400" :
                                    detail.passed === false ? "text-red-600 dark:text-red-400" :
                                        "text-slate-600 dark:text-gray-300"
                                    }`}>Ã¢â€ â€™ {detail.outcome}</p>
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
            <span className="text-3xl block mb-3">Ã°Å¸â€œÅ </span>
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
                            <span className="text-base">Ã°Å¸â€œâ€ž</span>
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

function FeedbackPanel({ feedbacks }: { feedbacks: AHMNFeedback[] }) {
    if (feedbacks.length === 0) return <div className="glass-panel rounded-xl p-8 text-center text-slate-400 dark:text-gray-500 text-sm">No AHMN feedback available</div>;

    const loggedFeedbacks = feedbacks.filter(f => f?.status === "logged");
    const avgF1 = loggedFeedbacks.length > 0 ? loggedFeedbacks.reduce((sum, f) => sum + (f.metrics_sent?.f1_score || 0), 0) / loggedFeedbacks.length : 0;
    const avgPrecision = loggedFeedbacks.length > 0 ? loggedFeedbacks.reduce((sum, f) => sum + (f.metrics_sent?.precision || 0), 0) / loggedFeedbacks.length : 0;
    const avgRecall = loggedFeedbacks.length > 0 ? loggedFeedbacks.reduce((sum, f) => sum + (f.metrics_sent?.recall || 0), 0) / loggedFeedbacks.length : 0;

    return (
        <div className="space-y-3">
            {/* Summary Header */}
            <div className="glass-panel rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2"><span className="text-lg">Ã°Å¸â€œË†</span><p className="text-sm font-semibold text-slate-900 dark:text-white">Per-Document Feedback</p></div>
                    <span className={`px-2.5 py-1 rounded-full text-[10px] font-medium border ${loggedFeedbacks.length > 0 ? "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-300" : "bg-slate-100 dark:bg-gray-800 border-slate-200 dark:border-gray-700 text-slate-600 dark:text-gray-300"}`}>
                        {loggedFeedbacks.length}/{feedbacks.length} logged
                    </span>
                </div>
                <div className="grid grid-cols-3 gap-3">
                    <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Avg F1 Score</p>
                        <p className="text-lg font-bold text-slate-900 dark:text-white">{loggedFeedbacks.length > 0 ? `${(avgF1 * 100).toFixed(1)}%` : "Ã¢â‚¬â€"}</p>
                    </div>
                    <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Avg Precision</p>
                        <p className="text-lg font-bold text-slate-900 dark:text-white">{loggedFeedbacks.length > 0 ? `${(avgPrecision * 100).toFixed(1)}%` : "Ã¢â‚¬â€"}</p>
                    </div>
                    <div className="p-3 bg-slate-50 dark:bg-gray-800/50 rounded-lg border border-slate-200 dark:border-gray-700">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500 mb-1">Avg Recall</p>
                        <p className="text-lg font-bold text-slate-900 dark:text-white">{loggedFeedbacks.length > 0 ? `${(avgRecall * 100).toFixed(1)}%` : "Ã¢â‚¬â€"}</p>
                    </div>
                </div>
                {loggedFeedbacks.length > 0 && (
                    <div className="mt-3 p-3 bg-emerald-50/30 dark:bg-emerald-500/5 rounded-lg border border-emerald-100 dark:border-emerald-500/10">
                        <div className="flex items-start gap-2">
                            <svg className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                            <div>
                                <p className="text-xs font-medium text-emerald-700 dark:text-emerald-300">Bandit Updated ({loggedFeedbacks.length} doc{loggedFeedbacks.length !== 1 ? "s" : ""})</p>
                                <p className="text-[10px] text-emerald-600 dark:text-emerald-400 mt-0.5">
                                    AHMN has updated its Thompson Sampling posteriors for each document. Future advice will reflect this learning.
                                </p>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Per-Document Feedback Cards */}
            {feedbacks.map((feedback, idx) => (
                <div key={feedback.advice_id || idx} className={`glass-panel rounded-xl p-4 border-l-4 ${feedback.status === "logged" ? "border-l-emerald-500" : feedback.status === "failed" ? "border-l-red-500" : "border-l-slate-300"}`}>
                    <div className="flex items-center justify-between">
                        <p className="text-xs font-medium text-slate-900 dark:text-white">Document {idx + 1}</p>
                        <div className="flex items-center gap-2">
                            {feedback.status === "logged" && feedback.metrics_sent?.f1_score != null && (
                                <span className="text-xs text-slate-600 dark:text-gray-300">F1: {(feedback.metrics_sent.f1_score * 100).toFixed(0)}%</span>
                            )}
                            <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${feedback.status === "logged" ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : feedback.status === "failed" ? "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-300" : "bg-slate-100 dark:bg-gray-700 text-slate-600 dark:text-gray-300"}`}>{feedback.status}</span>
                            {feedback.policy_id_used && <span className="text-[10px] font-mono text-slate-500 dark:text-gray-400">{feedback.policy_id_used}</span>}
                        </div>
                    </div>
                    {feedback.error && <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-1">{feedback.error}</p>}
                </div>
            ))}
        </div>
    );
}

/* Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â */
/*  Document Card (enhanced with inline integration data)                   */
/* Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â */

function DocCard({ doc, expanded, onToggle, guardrail, xai, advice, feedback }: {
    doc: IDPODocRecord; expanded: boolean; onToggle: () => void;
    guardrail?: GuardrailDocResult; xai?: XAIDocExplanation;
    advice?: AHMNAdvice; feedback?: AHMNFeedback;
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
        if (src === "llm_cloud" || src === "llm_local") return "Ã°Å¸Â¤â€“";
        if (src === "rule" || src === "schema_regex") return "Ã°Å¸â€œÂ";
        if (src === "generic_kv") return "Ã°Å¸â€â€˜";
        if (src === "schema_match") return "Ã°Å¸â€â€”";
        if (src === "policy") return "Ã°Å¸â€œâ€¹";
        return "Ã¢Å¡Â¡";
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
            {/* Ã¢â€â‚¬Ã¢â€â‚¬ Card Header (always visible) Ã¢â€â‚¬Ã¢â€â‚¬ */}
            <button onClick={onToggle} className="w-full px-5 py-4 text-left hover:bg-white/40 dark:hover:bg-gray-800/30 transition-colors">
                <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-100 to-cyan-100 dark:from-brand-500/10 dark:to-cyan-500/10 border border-brand-200/50 dark:border-brand-500/20 flex items-center justify-center flex-shrink-0">
                            <span className="text-lg">Ã°Å¸â€œâ€ž</span>
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
                        {advice && !advice.error && (
                            <span className={`px-2 py-0.5 rounded text-[9px] font-medium ${advice.confidence >= 0.7 ? "bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-500/20" : "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/20"}`} title={`AHMN Policy: ${advice.policy_id} (${(advice.confidence * 100).toFixed(0)}%)`}>
                                {advice.policy_id?.replace(/_/g, " ").replace(/policy$/i, "").trim() || "default"}
                            </span>
                        )}
                        {guardrail && !guardrail.error && (
                            <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] ${guardrail.overall_passes ? "bg-emerald-100 dark:bg-emerald-500/10 ring-1 ring-emerald-200 dark:ring-emerald-500/20" : "bg-red-100 dark:bg-red-500/10 ring-1 ring-red-200 dark:ring-red-500/20"}`} title={guardrail.overall_passes ? "Guardrails passed" : "Guardrails failed"}>Ã°Å¸â€ºÂ¡Ã¯Â¸Â</span>
                        )}
                        {xai && !xai.error && <span className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] bg-violet-100 dark:bg-violet-500/10 ring-1 ring-violet-200 dark:ring-violet-500/20" title="XAI explanation available">Ã°Å¸â€Â</span>}
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

            {/* Ã¢â€â‚¬Ã¢â€â‚¬ Expanded Content Ã¢â€â‚¬Ã¢â€â‚¬ */}
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
                                )) : <span className="text-[10px] text-slate-400 dark:text-gray-500">Ã¢â‚¬â€</span>}
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
                                    Ã°Å¸Â¤â€“ {doc.model_used} ({doc.model_mode || "local"})
                                </span>
                            )}
                        </div>
                    )}

                    {/* Per-Document AHMN Policy */}
                    {advice && (
                        <div className={`p-4 rounded-xl border ${advice.error ? "bg-amber-50/50 dark:bg-amber-500/5 border-amber-200 dark:border-amber-500/20" : "bg-gradient-to-r from-brand-50/50 to-cyan-50/50 dark:from-brand-500/5 dark:to-cyan-500/5 border-brand-200 dark:border-brand-500/20"}`}>
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <span className="text-base">Ã°Å¸Å½Â¯</span>
                                    <p className="text-[10px] font-semibold text-slate-500 dark:text-gray-400 uppercase tracking-wider">AHMN Policy</p>
                                </div>
                                {!advice.error && (
                                    <span className={`px-2 py-0.5 rounded text-[9px] font-medium ${advice.confidence >= 0.7 ? "bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : advice.confidence >= 0.5 ? "bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300" : "bg-slate-100 dark:bg-gray-700 text-slate-600 dark:text-gray-300"}`}>
                                        {(advice.confidence * 100).toFixed(0)}% confidence
                                    </span>
                                )}
                            </div>
                            {advice.error ? (
                                <p className="text-xs text-amber-700 dark:text-amber-300">{advice.error}</p>
                            ) : (
                                <div className="space-y-1.5">
                                    <div className="flex items-center gap-3">
                                        <span className="text-sm font-semibold text-slate-900 dark:text-white">{advice.policy_id?.replace(/_/g, " ") || "default_policy"}</span>
                                        {advice.rabi_used && <span className="px-1.5 py-0.5 bg-violet-100 dark:bg-violet-500/10 text-violet-700 dark:text-violet-300 rounded text-[9px] font-medium">RABI</span>}
                                        <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-gray-700 text-slate-600 dark:text-gray-300 rounded text-[9px] font-medium">{advice.retrieval_source}</span>
                                    </div>
                                    {feedback && feedback.status === "logged" && (
                                        <div className="flex items-center gap-2 text-[10px] text-slate-500 dark:text-gray-400">
                                            <span>Feedback: F1 {((feedback.metrics_sent?.f1_score || 0) * 100).toFixed(1)}%</span>
                                            {feedback.metrics_sent?.precision != null && <span>| P: {(feedback.metrics_sent.precision * 100).toFixed(0)}%</span>}
                                            {feedback.metrics_sent?.recall != null && <span>| R: {(feedback.metrics_sent.recall * 100).toFixed(0)}%</span>}
                                        </div>
                                    )}
                                </div>
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

                    {/* Extracted Entities Ã¢â‚¬â€ show top 3, collapse rest */}
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
                                <span className="text-sm">Ã¢Å¡Â Ã¯Â¸Â</span>
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
                                <span className="text-sm">Ã°Å¸â€Â§</span>
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
                                        Ã°Å¸â€œâ€¹ Copy
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
                                    Ã°Å¸â€ºÂ¡Ã¯Â¸Â Guardrails: {guardrail.overall_passes ? "PASSED" : "FAILED"}
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
                                <span className="text-[10px] font-semibold text-violet-600 dark:text-violet-400 uppercase tracking-wider">Ã°Å¸â€œÅ  Component Explanations</span>
                                <span className="text-[9px] text-violet-500">{(xai.confidence * 100).toFixed(0)}% confident</span>
                            </summary>
                            <div className="mt-2 space-y-2">
                                <p className="text-xs text-slate-700 dark:text-gray-300 p-2 bg-slate-50 dark:bg-gray-800/50 rounded-lg">{xai.answer}</p>
                                {xai.component_explanations && xai.component_explanations.map((comp, i) => (
                                    <div key={i} className={`p-2.5 rounded-lg border-l-2 ${comp.status === "success" ? "border-l-emerald-500 bg-emerald-50/30 dark:bg-emerald-500/5" :
                                        comp.status === "warning" ? "border-l-amber-500 bg-amber-50/30 dark:bg-amber-500/5" :
                                            comp.status === "error" ? "border-l-red-500 bg-red-50/30 dark:bg-red-500/5" :
                                                "border-l-slate-400 bg-slate-50/30 dark:bg-slate-500/5"
                                        }`}>
                                        <div className="flex items-center gap-1.5 mb-1">
                                            <span className="text-sm">{comp.component === "ahmn" ? "Ã°Å¸Å½Â¯" : comp.component === "idpo" ? "Ã¢Å¡â„¢Ã¯Â¸Â" : "Ã°Å¸â€ºÂ¡Ã¯Â¸Â"}</span>
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

/* Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â */
function JourneyDocCard({ doc, expanded, onToggle, guardrail, xai, advice, feedback }: {
    doc: IDPODocRecord; expanded: boolean; onToggle: () => void;
    guardrail?: GuardrailDocResult; xai?: XAIDocExplanation;
    advice?: AHMNAdvice; feedback?: AHMNFeedback;
}) {
    const statusColor = doc.status === "success"
        ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/20"
        : doc.status === "error"
            ? "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-300 border-red-200 dark:border-red-500/20"
            : "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/20";

    const flattenedFields: IDPOEntityDetail[] = (doc.entity_details && doc.entity_details.length > 0)
        ? doc.entity_details
        : Object.entries(doc.entities || {}).map(([key, value]) => ({
            key,
            label: key,
            value: String(value),
            confidence: typeof doc.field_confidence?.[key] === "number" ? doc.field_confidence[key] : 0,
            source: "result",
            is_explicit: false,
        }));

    const previewFields = flattenedFields.slice(0, 6);
    const selectedPolicy = doc.policy_id || advice?.selected_policy_id || advice?.policy_id || "default";
    const advisorPolicy = advice?.advisor_recommendation?.policy_id || advice?.policy_id || doc.advisor_recommendation?.policy_id || null;
    const reviewStatus = doc.defer_status || (doc.escalated ? "requested" : "not_needed");
    const reviewReason = doc.defer_reason || doc.model_reason || null;
    const unseenVendor = !doc.vendor_cluster || /unknown|unseen|new/i.test(doc.vendor_cluster);
    const feedbackLogged = feedback?.status === "logged" || doc.feedback_status?.logged === true;
    const validationIssueCount = doc.validation_issues?.length || 0;
    const recoveredFieldCount = doc.recovered_fields ? Object.keys(doc.recovered_fields).length : 0;
    const executionStages = [
        {
            label: "Identify",
            status: "done",
            detail: [doc.doc_type, doc.vendor_cluster, doc.content_profile].filter(Boolean).join(" / ") || "Context derived from the uploaded document.",
        },
        {
            label: "Retrieve Advice",
            status: advice?.error ? "warning" : advisorPolicy ? "done" : "skipped",
            detail: advice?.error
                ? advice.error
                : advisorPolicy
                    ? `${formatPolicyLabel(advisorPolicy)} via ${advice?.retrieval_source || doc.retrieval_source || "advisor"}`
                    : "Static or local routing path.",
        },
        {
            label: "Select Policy",
            status: doc.fallback_reason ? "warning" : "done",
            detail: doc.fallback_reason
                ? `${formatPolicyLabel(selectedPolicy)} after fallback: ${doc.fallback_reason}`
                : formatPolicyLabel(selectedPolicy),
        },
        {
            label: "Execute",
            status: doc.status === "error" ? "error" : "done",
            detail: [doc.preprocess_route, doc.ocr_engine_used, doc.model_used].filter(Boolean).join(" / ") || "Extraction path completed.",
        },
        {
            label: "Evaluate",
            status: validationIssueCount > 0 ? "warning" : "done",
            detail: validationIssueCount > 0
                ? `${validationIssueCount} validation issue(s)`
                : `Schema ${doc.schema_valid === true ? "valid" : doc.schema_valid === false ? "needs review" : "pending"}`,
        },
        {
            label: "Update",
            status: feedbackLogged ? "done" : reviewStatus !== "not_needed" ? "review" : "pending",
            detail: feedbackLogged
                ? `Feedback logged for ${formatPolicyLabel(feedback?.policy_id_used || selectedPolicy)}`
                : reviewStatus !== "not_needed"
                    ? `Review ${reviewStatus}${reviewReason ? `: ${reviewReason}` : ""}`
                    : "Feedback not logged yet.",
        },
    ];

    const stageTone = (status: string) => {
        if (status === "done") return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
        if (status === "warning" || status === "review") return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20";
        if (status === "error") return "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
        return "bg-slate-100 text-slate-600 border-slate-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700";
    };

    return (
        <div className="glass-panel rounded-xl overflow-hidden transition-all duration-200 hover:shadow-lg hover:shadow-brand-500/5">
            <button onClick={onToggle} className="w-full px-5 py-4 text-left hover:bg-white/40 dark:hover:bg-gray-800/30 transition-colors">
                <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{doc.filename || doc.source || doc.doc_id}</p>
                            {(doc.category || doc.doc_type) && (
                                <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                                    {doc.category || doc.doc_type}
                                </span>
                            )}
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${statusColor}`}>{doc.status || "processed"}</span>
                            <span className="rounded-full border border-brand-200 bg-brand-50 px-2 py-0.5 text-[10px] font-medium text-brand-700 dark:border-brand-500/20 dark:bg-brand-500/10 dark:text-brand-300">
                                {formatPolicyLabel(selectedPolicy)}
                            </span>
                            {reviewStatus !== "not_needed" && (
                                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300">
                                    review: {reviewStatus}
                                </span>
                            )}
                        </div>
                        <p className="mt-1 text-xs text-slate-500 dark:text-gray-400">
                            {advisorPolicy ? `Advisor ${formatPolicyLabel(advisorPolicy)} -> selected ${formatPolicyLabel(selectedPolicy)}` : `Selected ${formatPolicyLabel(selectedPolicy)}`}
                            {doc.fallback_reason ? ` -> fallback: ${doc.fallback_reason}` : ""}
                            {doc.safety_status?.rollback_triggered ? ` -> rollback: ${doc.safety_status.rollback_reason || "triggered"}` : ""}
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-medium text-slate-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                            {flattenedFields.length} field{flattenedFields.length !== 1 ? "s" : ""}
                        </span>
                        <svg className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                        </svg>
                    </div>
                </div>
            </button>

            {expanded && (
                <div className="space-y-5 border-t border-slate-100 px-5 pb-5 pt-4 dark:border-gray-800">
                    <section className="space-y-3">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">1. Identify</h3>
                            {unseenVendor && (
                                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300">
                                    unseen vendor path
                                </span>
                            )}
                        </div>
                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Document Type</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{doc.doc_type || doc.category || "-"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Vendor</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{doc.vendor_cluster || "unknown_vendor"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Layout + Profile</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{[doc.layout_cluster_id, doc.content_profile].filter(Boolean).join(" / ") || "-"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Quality + Complexity</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{[doc.quality_bin, doc.complexity_bin].filter(Boolean).join(" / ") || "-"}</p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">analysis confidence {formatPercent(doc.analysis_confidence)}</p>
                            </div>
                        </div>
                        {unseenVendor && (
                            <p className="text-xs text-amber-700 dark:text-amber-300">
                                This document is currently taking the honest safe path for unseen vendors: use the default-backed policy path and log the outcome for future advice.
                            </p>
                        )}
                    </section>

                    <section className="space-y-3">
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">2. Policy Decision</h3>
                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                            <div className="rounded-xl border border-brand-200 bg-brand-50/70 p-3 dark:border-brand-500/20 dark:bg-brand-500/10">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-brand-600 dark:text-brand-300">Advisor Recommendation</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{advisorPolicy ? formatPolicyLabel(advisorPolicy) : "static or local path"}</p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">
                                    {advice?.error ? advice.error : `${formatPercent(advice?.confidence)} via ${advice?.retrieval_source || doc.retrieval_source || "advisor"}`}
                                </p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Selected Policy</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{formatPolicyLabel(selectedPolicy)}</p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">{doc.advice_source || advice?.advice_source || "runtime selection"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Safety Status</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">
                                    {doc.safety_status?.rollback_triggered ? "rollback triggered" : doc.fallback_reason ? "fallback used" : "clear"}
                                </p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">{doc.safety_status?.rollback_reason || doc.fallback_reason || "No safety intervention."}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Review / Defer</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{reviewStatus.replace(/_/g, " ")}</p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">{reviewReason || "No review requested."}</p>
                            </div>
                        </div>
                        {(doc.fallback_candidates && doc.fallback_candidates.length > 0) && (
                            <div className="rounded-xl border border-slate-200 bg-white/60 p-3 dark:border-gray-700 dark:bg-gray-800/40">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Fallback Candidates</p>
                                <div className="mt-2 flex flex-wrap gap-2">
                                    {doc.fallback_candidates.map((candidate, index) => (
                                        <span key={`${candidate.policy_id}-${index}`} className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] text-slate-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                                            {formatPolicyLabel(candidate.policy_id)}
                                            {candidate.reason ? ` - ${candidate.reason}` : ""}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </section>

                    <section className="space-y-3">
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">3. Execution Path</h3>
                        <div className="grid gap-2 lg:grid-cols-2">
                            {executionStages.map((stage) => (
                                <div key={stage.label} className="rounded-xl border border-slate-200 bg-white/60 p-3 dark:border-gray-700 dark:bg-gray-800/40">
                                    <div className="flex items-center justify-between gap-3">
                                        <p className="text-xs font-semibold text-slate-900 dark:text-white">{stage.label}</p>
                                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${stageTone(stage.status)}`}>
                                            {stage.status}
                                        </span>
                                    </div>
                                    <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">{stage.detail}</p>
                                </div>
                            ))}
                        </div>
                    </section>

                    <section className="space-y-3">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">4. Extracted Fields</h3>
                            <span className="text-[11px] text-slate-500 dark:text-gray-400">{flattenedFields.length} total</span>
                        </div>
                        {previewFields.length > 0 ? (
                            <div className="space-y-2">
                                {previewFields.map((field, index) => (
                                    <div key={`${field.key}-${index}`} className="rounded-xl border border-slate-200 bg-white/70 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                        <div className="flex flex-wrap items-start justify-between gap-3">
                                            <div className="min-w-0 flex-1">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">{field.label || field.key}</span>
                                                    {field.is_explicit && (
                                                        <span className="rounded-full border border-brand-200 bg-brand-50 px-2 py-0.5 text-[9px] font-medium text-brand-700 dark:border-brand-500/20 dark:bg-brand-500/10 dark:text-brand-300">
                                                            required
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white break-words">{field.value}</p>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-sm font-semibold text-slate-900 dark:text-white">{formatPercent(field.confidence)}</p>
                                                <p className="text-[10px] text-slate-500 dark:text-gray-400">{field.confidence_type || "confidence"}</p>
                                            </div>
                                        </div>
                                        <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-500 dark:text-gray-400">
                                            <span>source: {field.source || "-"}</span>
                                            {field.page != null && <span>page: {field.page}</span>}
                                            {field.span && <span>span: {field.span}</span>}
                                            {field.bbox && <span>bbox: [{field.bbox.join(", ")}]</span>}
                                        </div>
                                    </div>
                                ))}
                                {flattenedFields.length > previewFields.length && (
                                    <p className="text-[11px] text-slate-500 dark:text-gray-400">
                                        Open the run detail page for the full field list and deeper document evidence.
                                    </p>
                                )}
                            </div>
                        ) : (
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-400">
                                No extracted fields are available for this document yet.
                            </div>
                        )}
                    </section>

                    <section className="space-y-3">
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">5. Evaluation</h3>
                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Reward</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{typeof doc.reward === "number" ? doc.reward.toFixed(3) : "-"}</p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">{doc.reward_type || "task reward"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Schema</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">
                                    {doc.schema_valid === true ? "valid" : doc.schema_valid === false ? "review needed" : "-"}
                                </p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">coverage {formatPercent(doc.schema_coverage)} / grounded {formatPercent(doc.schema_grounding_coverage)}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Validation</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{validationIssueCount} issue(s)</p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">{recoveredFieldCount} recovered field(s)</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Required / Hallucinated</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">
                                    {doc.schema_missing_required_count ?? 0} missing / {doc.schema_hallucinated_field_count ?? 0} extra
                                </p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">Grounded fields matter more than raw field count.</p>
                            </div>
                        </div>
                        {validationIssueCount > 0 && (
                            <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-500/20 dark:bg-amber-500/10">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300">Validation Issues</p>
                                <div className="mt-2 space-y-1">
                                    {doc.validation_issues?.map((issue, index) => (
                                        <p key={`${issue.field}-${index}`} className="text-[11px] text-amber-700 dark:text-amber-300">
                                            <span className="font-medium">{issue.field}</span>: {issue.issue}
                                        </p>
                                    ))}
                                </div>
                            </div>
                        )}
                    </section>

                    <section className="space-y-3">
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">6. Feedback Update</h3>
                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Advice Id</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white break-all">{feedback?.advice_id || doc.advice_id || doc.feedback_status?.advice_id || "-"}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Policy Used</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{formatPolicyLabel(feedback?.policy_id_used || selectedPolicy)}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Feedback Status</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{feedback?.status || (feedbackLogged ? "logged" : "not logged")}</p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">{feedback?.error || doc.feedback_status?.error || "Outcome available for future advice."}</p>
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Metrics Sent</p>
                                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">F1 {formatPercent(feedback?.metrics_sent?.f1_score, 1)}</p>
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">P {formatPercent(feedback?.metrics_sent?.precision, 1)} / R {formatPercent(feedback?.metrics_sent?.recall, 1)}</p>
                            </div>
                        </div>
                    </section>

                    <details className="group">
                        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-slate-400 transition-colors hover:text-slate-600 dark:text-gray-500 dark:hover:text-gray-300">
                            Supporting diagnostics
                        </summary>
                        <div className="mt-3 space-y-3">
                            {guardrail && !guardrail.error && (
                                <div className={`rounded-xl border p-3 ${guardrail.overall_passes ? "border-emerald-200 bg-emerald-50/60 dark:border-emerald-500/20 dark:bg-emerald-500/10" : "border-red-200 bg-red-50/60 dark:border-red-500/20 dark:bg-red-500/10"}`}>
                                    <p className="text-xs font-medium text-slate-900 dark:text-white">Guardrails {guardrail.overall_passes ? "passed" : "failed"}</p>
                                    <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">{(guardrail.processing_time_ms / 1000).toFixed(1)}s processing time</p>
                                </div>
                            )}
                            {xai && !xai.error && (
                                <div className="rounded-xl border border-violet-200 bg-violet-50/60 p-3 dark:border-violet-500/20 dark:bg-violet-500/10">
                                    <p className="text-xs font-medium text-slate-900 dark:text-white">Supporting explanation available</p>
                                    <p className="mt-1 text-[11px] text-slate-500 dark:text-gray-400">{xai.answer}</p>
                                </div>
                            )}
                            {doc.extracted_text && (
                                <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3 dark:border-gray-700 dark:bg-gray-800/40">
                                    <div className="flex items-center justify-between gap-3">
                                        <p className="text-xs font-medium text-slate-900 dark:text-white">Extracted text</p>
                                        <button
                                            onClick={() => navigator.clipboard.writeText(doc.extracted_text || "")}
                                            className="rounded-md border border-brand-200 bg-brand-50 px-2 py-1 text-[10px] font-medium text-brand-700 transition-colors hover:bg-brand-100 dark:border-brand-500/20 dark:bg-brand-500/10 dark:text-brand-300 dark:hover:bg-brand-500/20"
                                        >
                                            Copy
                                        </button>
                                    </div>
                                    <div className="mt-2 max-h-[300px] overflow-y-auto rounded-lg border border-slate-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900/50">
                                        <FormattedExtractedText text={doc.extracted_text} />
                                    </div>
                                </div>
                            )}
                        </div>
                    </details>
                </div>
            )}
        </div>
    );
}

/*  Formatted Extracted Text (styled page separators)                       */
/* Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â */

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


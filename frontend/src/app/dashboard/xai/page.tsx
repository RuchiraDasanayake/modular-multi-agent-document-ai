"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { idpoApi } from "@/lib/idpo-api";
import { Icon } from "@/components/icons";
import type { ChatMessage, XAIExplanation } from "@/types";
import type { JobStatus } from "@/types/idpo";

const CUSTOM = "custom";
const MAX_DOCUMENTS = 40;
const EXAMPLE_QUESTIONS = ["What is the total amount?", "What is the date?", "Who issued this document?"];

interface QaDocument {
    key: string;
    jobId: string;
    jobName: string;
    fileId: string;
    fileName: string;
    runId: string;
}

interface DocumentText {
    status: "loading" | "ready" | "error";
    text: string;
    truncated: boolean;
}

type QaMessage = ChatMessage & { source?: string; failed?: boolean };

function processedDocuments(jobs: JobStatus[]): QaDocument[] {
    const docs: QaDocument[] = [];
    const newestFirst = [...jobs].sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
    for (const job of newestFirst) {
        for (const document of job.documents ?? []) {
            if (document.status !== "processed" || !document.latestRunId || !document.latestDocId) {
                continue;
            }
            docs.push({
                key: `${job.jobId}:${document.fileId}`,
                jobId: job.jobId,
                jobName: job.jobName || `Job ${job.jobId.slice(0, 8)}`,
                fileId: document.fileId,
                fileName: document.fileName,
                runId: document.latestRunId,
            });
            if (docs.length >= MAX_DOCUMENTS) {
                return docs;
            }
        }
    }
    return docs;
}

function groupByJob(docs: QaDocument[]): Array<{ jobId: string; jobName: string; docs: QaDocument[] }> {
    const groups = new Map<string, { jobId: string; jobName: string; docs: QaDocument[] }>();
    for (const doc of docs) {
        const group = groups.get(doc.jobId) ?? { jobId: doc.jobId, jobName: doc.jobName, docs: [] };
        group.docs.push(doc);
        groups.set(doc.jobId, group);
    }
    return [...groups.values()];
}

function timeNow(): string {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function confidenceTone(confidence: number): string {
    if (confidence >= 0.7) {
        return "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300";
    }
    if (confidence >= 0.4) {
        return "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300";
    }
    return "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300";
}

export default function XAIPage() {
    const [docs, setDocs] = useState<QaDocument[]>([]);
    const [docsStatus, setDocsStatus] = useState<"loading" | "ready" | "error">("loading");
    const [selectedKey, setSelectedKey] = useState("");
    const [texts, setTexts] = useState<Record<string, DocumentText>>({});
    const [customText, setCustomText] = useState("");
    const [showText, setShowText] = useState(false);

    const [messages, setMessages] = useState<QaMessage[]>([]);
    const [input, setInput] = useState("");
    const [isAsking, setIsAsking] = useState(false);
    const [slowAnswer, setSlowAnswer] = useState(false);
    const [currentExplanation, setCurrentExplanation] = useState<XAIExplanation | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const loadText = useCallback((doc: QaDocument) => {
        setTexts((prev) => ({ ...prev, [doc.key]: { status: "loading", text: "", truncated: false } }));
        idpoApi
            .getJobDocumentText(doc.jobId, doc.fileId)
            .then((payload) =>
                setTexts((prev) => ({
                    ...prev,
                    [doc.key]: { status: "ready", text: payload.text, truncated: payload.truncated },
                })),
            )
            .catch(() => setTexts((prev) => ({ ...prev, [doc.key]: { status: "error", text: "", truncated: false } })));
    }, []);

    useEffect(() => {
        let cancelled = false;
        idpoApi
            .listJobs()
            .then(({ jobs }) => {
                if (cancelled) {
                    return;
                }
                const found = processedDocuments(jobs);
                setDocs(found);
                setDocsStatus("ready");
                if (found.length > 0) {
                    setSelectedKey(found[0].key);
                    loadText(found[0]);
                } else {
                    setSelectedKey(CUSTOM);
                }
            })
            .catch(() => {
                if (!cancelled) {
                    setDocsStatus("error");
                    setSelectedKey(CUSTOM);
                }
            });
        return () => {
            cancelled = true;
        };
    }, [loadText]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, [messages, isAsking, slowAnswer]);

    useEffect(() => {
        if (!isAsking) {
            setSlowAnswer(false);
            return undefined;
        }
        const timer = window.setTimeout(() => setSlowAnswer(true), 8000);
        return () => window.clearTimeout(timer);
    }, [isAsking]);

    const selectedDoc = docs.find((doc) => doc.key === selectedKey) ?? null;
    const selectedText = selectedDoc ? texts[selectedDoc.key] : undefined;
    const contextText = selectedKey === CUSTOM ? customText : selectedText?.status === "ready" ? selectedText.text : "";
    const contextLabel = selectedKey === CUSTOM ? "your text" : selectedDoc?.fileName ?? "";
    const hasContext = contextText.trim().length > 0;
    const groups = groupByJob(docs);

    const selectDocument = (key: string) => {
        setSelectedKey(key);
        setShowText(false);
        const doc = docs.find((entry) => entry.key === key);
        if (doc && (!texts[doc.key] || texts[doc.key].status === "error")) {
            loadText(doc);
        }
    };

    const ask = async (question: string) => {
        const trimmed = question.trim();
        if (!trimmed || isAsking || !hasContext) {
            return;
        }
        const paragraph = contextText;
        const source = contextLabel;
        setMessages((prev) => [...prev, { id: `${Date.now()}-q`, role: "user", content: trimmed, timestamp: timeNow() }]);
        setInput("");
        setIsAsking(true);
        try {
            const response = await api.askQuestion(paragraph, trimmed);
            setMessages((prev) => [
                ...prev,
                {
                    id: `${Date.now()}-a`,
                    role: "bot",
                    content: response.answer,
                    timestamp: timeNow(),
                    confidence: response.confidence,
                    source,
                },
            ]);
            // The service reports confidence -1 for conversation, "no answer" and its own error fallback,
            // whose explanation is placeholder data.
            if (response.confidence < 0) {
                setCurrentExplanation(null);
                return;
            }
            setCurrentExplanation(response.explanation);
            sessionStorage.setItem("xai_explanation", JSON.stringify(response.explanation));
            sessionStorage.setItem("xai_question", trimmed);
            sessionStorage.setItem("xai_paragraph", paragraph);
            // The review page reads these after a reload or from another tab.
            localStorage.setItem("xai_explanation", JSON.stringify(response.explanation));
            localStorage.setItem("xai_question", trimmed);
            localStorage.setItem("xai_paragraph", paragraph);
        } catch (err) {
            setMessages((prev) => [
                ...prev,
                {
                    id: `${Date.now()}-e`,
                    role: "bot",
                    content: `The XAI service did not answer. Check that it is running, then try again.${err instanceof Error ? ` (${err.message})` : ""}`,
                    timestamp: timeNow(),
                    failed: true,
                },
            ]);
        } finally {
            setIsAsking(false);
        }
    };

    const inputPlaceholder = hasContext
        ? `Ask about ${contextLabel}`
        : selectedText?.status === "loading"
          ? "Loading the document text…"
          : selectedKey === CUSTOM
            ? "Paste some text above first"
            : "Pick a document with text first";

    return (
        <div className="max-w-4xl 3xl:max-w-5xl mx-auto space-y-4">
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6">
                <div className="absolute inset-0 bg-gradient-to-r from-violet-500/5 to-purple-500/5 dark:from-violet-500/[0.03] dark:to-purple-500/[0.03]" />
                <div className="relative">
                    <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                        <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-400 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-500/20 text-white">
                            <Icon name="chat" className="h-5 w-5" />
                        </span>
                        AI Q&A
                    </h1>
                    <p className="text-slate-600 dark:text-gray-300 mt-1.5 max-w-2xl text-sm">
                        Ask a question about the text of a processed document. The XAI service answers and can show
                        which words the answer relied on.
                    </p>
                </div>
            </div>

            <section className="glass-panel rounded-2xl p-5 space-y-3">
                <div className="flex flex-wrap items-end gap-x-3 gap-y-1">
                    <div className="min-w-[16rem] flex-1">
                        <label htmlFor="qa-document" className="block text-xs font-semibold text-slate-700 dark:text-gray-200">
                            Ask about
                        </label>
                        <select
                            id="qa-document"
                            value={selectedKey}
                            onChange={(event) => selectDocument(event.target.value)}
                            disabled={docsStatus === "loading"}
                            className="mt-1.5 w-full glass-input rounded-lg px-3 py-2 text-sm disabled:opacity-60"
                        >
                            {docsStatus === "loading" && <option value="">Loading your documents…</option>}
                            {groups.map((group) => (
                                <optgroup key={group.jobId} label={group.jobName}>
                                    {group.docs.map((doc) => (
                                        <option key={doc.key} value={doc.key}>
                                            {doc.fileName}
                                        </option>
                                    ))}
                                </optgroup>
                            ))}
                            {docsStatus !== "loading" && <option value={CUSTOM}>Paste your own text</option>}
                        </select>
                    </div>
                    {selectedDoc && (
                        <Link
                            href={`/dashboard/idpo/jobs/${encodeURIComponent(selectedDoc.jobId)}/docs/${encodeURIComponent(selectedDoc.fileId)}?runId=${encodeURIComponent(selectedDoc.runId)}`}
                            className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-medium text-brand-700 hover:bg-brand-50 dark:text-brand-300 dark:hover:bg-brand-500/10"
                        >
                            Open document
                            <Icon name="arrowRight" className="h-3.5 w-3.5" />
                        </Link>
                    )}
                </div>

                {docsStatus === "error" && (
                    <p className="text-xs text-amber-700 dark:text-amber-300">
                        Your processed documents could not be loaded. You can still paste text.
                    </p>
                )}
                {docsStatus === "ready" && docs.length === 0 && (
                    <p className="text-xs text-slate-600 dark:text-gray-300">
                        No processed documents yet.{" "}
                        <Link href="/dashboard/idpo/jobs" className="font-medium text-brand-700 underline-offset-2 hover:underline dark:text-brand-300">
                            Process a document
                        </Link>{" "}
                        first, or paste text below.
                    </p>
                )}

                {selectedKey === CUSTOM && docsStatus !== "loading" && (
                    <div>
                        <label htmlFor="qa-custom-text" className="sr-only">
                            Text to ask about
                        </label>
                        <textarea
                            id="qa-custom-text"
                            value={customText}
                            onChange={(event) => setCustomText(event.target.value)}
                            placeholder="Paste the text you want to ask about"
                            rows={6}
                            className="w-full glass-input rounded-lg px-3 py-2 text-sm resize-y"
                        />
                    </div>
                )}

                {selectedDoc && (
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600 dark:text-gray-300">
                        {selectedText?.status === "loading" && <span>Loading the document text…</span>}
                        {selectedText?.status === "error" && (
                            <>
                                <span className="text-rose-700 dark:text-rose-300">The text of this document could not be loaded.</span>
                                <button
                                    type="button"
                                    onClick={() => loadText(selectedDoc)}
                                    className="font-medium text-brand-700 hover:underline dark:text-brand-300"
                                >
                                    Try again
                                </button>
                            </>
                        )}
                        {selectedText?.status === "ready" && !hasContext && (
                            <span>No OCR text was saved for this document, so there is nothing to ask about.</span>
                        )}
                        {selectedText?.status === "ready" && hasContext && (
                            <>
                                <span>
                                    {contextText.length.toLocaleString()} characters of OCR text
                                    {selectedText.truncated ? " (the first part of the document)" : ""}
                                </span>
                                <button
                                    type="button"
                                    onClick={() => setShowText((value) => !value)}
                                    aria-expanded={showText}
                                    className="inline-flex items-center gap-1 font-medium text-brand-700 hover:underline dark:text-brand-300"
                                >
                                    {showText ? "Hide text" : "Show text"}
                                    <Icon name="chevronDown" className={`h-3.5 w-3.5 transition-transform ${showText ? "rotate-180" : ""}`} />
                                </button>
                            </>
                        )}
                    </div>
                )}

                {selectedDoc && showText && hasContext && (
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-4 font-sans text-xs leading-relaxed text-slate-700 dark:border-gray-700 dark:bg-gray-900/60 dark:text-gray-300">
                        {contextText}
                    </pre>
                )}
            </section>

            <section className="glass-panel rounded-2xl overflow-hidden flex flex-col h-[60vh] min-h-[420px] max-h-[640px]" aria-label="Conversation">
                <div className="flex-1 overflow-y-auto p-5 space-y-4" aria-live="polite">
                    {messages.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-center">
                            <span className="w-14 h-14 rounded-2xl bg-violet-50 dark:bg-violet-500/10 border border-violet-200/60 dark:border-violet-500/20 flex items-center justify-center text-violet-600 dark:text-violet-300">
                                <Icon name="chat" className="h-6 w-6" />
                            </span>
                            <p className="mt-3 text-base font-semibold text-slate-800 dark:text-gray-100">
                                {hasContext ? `Ask a question about ${contextLabel}` : "Choose what to ask about"}
                            </p>
                            <p className="mt-1 max-w-md text-sm text-slate-500 dark:text-gray-400">
                                {hasContext
                                    ? "Answers come only from this text. Try one of these:"
                                    : "Pick a processed document above, or paste your own text."}
                            </p>
                            {hasContext && (
                                <div className="mt-4 flex flex-wrap justify-center gap-2">
                                    {EXAMPLE_QUESTIONS.map((question) => (
                                        <button
                                            key={question}
                                            type="button"
                                            onClick={() => void ask(question)}
                                            disabled={isAsking}
                                            className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-violet-300 hover:bg-violet-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:border-violet-500/40 dark:hover:bg-violet-500/10"
                                        >
                                            {question}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    ) : (
                        messages.map((msg) => (
                            <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                                <div
                                    className={`max-w-[85%] rounded-2xl px-4 py-3 shadow-sm ${
                                        msg.role === "user"
                                            ? "bg-brand-600 text-white rounded-br-sm"
                                            : msg.failed
                                              ? "border border-rose-200 bg-rose-50 text-rose-900 rounded-bl-sm dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200"
                                              : "border border-slate-200 bg-white text-slate-800 rounded-bl-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                                    }`}
                                >
                                    <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] opacity-80">
                                        <span>{msg.timestamp}</span>
                                        {msg.source && <span>From {msg.source}</span>}
                                        {msg.confidence !== undefined && msg.confidence >= 0 && (
                                            <span className={`rounded-full border px-2 py-0.5 font-medium ${confidenceTone(msg.confidence)}`}>
                                                Confidence {(msg.confidence * 100).toFixed(0)}%
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                    {isAsking && (
                        <div className="flex justify-start">
                            <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
                                <div className="flex items-center gap-1.5">
                                    <span className="sr-only">Waiting for the answer</span>
                                    <span className="h-2 w-2 rounded-full bg-brand-400 animate-bounce" />
                                    <span className="h-2 w-2 rounded-full bg-brand-400 animate-bounce [animation-delay:0.2s]" />
                                    <span className="h-2 w-2 rounded-full bg-brand-400 animate-bounce [animation-delay:0.4s]" />
                                </div>
                                {slowAnswer && (
                                    <p className="mt-2 text-xs text-slate-600 dark:text-gray-300">
                                        Still working. The first answer after the XAI service starts can take up to a minute
                                        while it loads its model.
                                    </p>
                                )}
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                <form
                    onSubmit={(event) => {
                        event.preventDefault();
                        void ask(input);
                    }}
                    className="border-t border-slate-200 dark:border-gray-700 p-3 sm:p-4 bg-white/60 dark:bg-gray-900/50"
                >
                    <div className="flex gap-2">
                        <label htmlFor="qa-question" className="sr-only">
                            Question
                        </label>
                        <input
                            id="qa-question"
                            type="text"
                            value={input}
                            onChange={(event) => setInput(event.target.value)}
                            placeholder={inputPlaceholder}
                            disabled={isAsking || !hasContext}
                            className="min-w-0 flex-1 glass-input rounded-full px-5 py-3 text-sm disabled:opacity-60"
                        />
                        <button
                            type="submit"
                            disabled={isAsking || !input.trim() || !hasContext}
                            className="inline-flex shrink-0 items-center gap-2 rounded-full bg-brand-600 px-5 py-3 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            <Icon name="send" className="h-4 w-4" />
                            <span className="hidden sm:inline">Ask</span>
                        </button>
                    </div>
                </form>
            </section>

            {currentExplanation && (
                <div className="flex flex-wrap items-center justify-center gap-3">
                    <Link
                        href="/dashboard/xai/explanation"
                        className="inline-flex items-center gap-2 rounded-full bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-violet-700"
                    >
                        <Icon name="search" className="h-4 w-4" />
                        See how the last answer was found
                    </Link>
                    <Link
                        href="/dashboard/hitl"
                        className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    >
                        <Icon name="userCheck" className="h-4 w-4" />
                        Rate the last answer
                    </Link>
                </div>
            )}
        </div>
    );
}

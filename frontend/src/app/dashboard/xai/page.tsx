"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useToast } from "@/components/toast";
import type { ChatMessage, XAIExplanation } from "@/types";

interface ExtractedDoc {
    id: string;
    filename: string;
    text: string;
}

const XAI_MESSAGES_KEY = "xai_chat_messages";
const XAI_PENDING_KEY = "xai_pending_request";
const XAI_LOADING_KEY = "xai_chat_loading";

function saveMessages(msgs: ChatMessage[]) {
    try { sessionStorage.setItem(XAI_MESSAGES_KEY, JSON.stringify(msgs)); } catch { /* */ }
}

export default function XAIPage() {
    const { addToast } = useToast();
    const [messages, setMessages] = useState<ChatMessage[]>(() => {
        if (typeof window === "undefined") return [];
        try {
            const stored = sessionStorage.getItem(XAI_MESSAGES_KEY);
            return stored ? JSON.parse(stored) : [];
        } catch { return []; }
    });
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(() => {
        if (typeof window === "undefined") return false;
        return sessionStorage.getItem(XAI_LOADING_KEY) === "true";
    });
    const [showParagraph, setShowParagraph] = useState(false);
    const [currentExplanation, setCurrentExplanation] = useState<XAIExplanation | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const mountedRef = useRef(true);

    // Document context management - only from IDPO extractions
    const [extractedDocs, setExtractedDocs] = useState<ExtractedDoc[]>([]);
    const [selectedDocId, setSelectedDocId] = useState<string>("");
    const [customText, setCustomText] = useState("");
    const [showDocSelector, setShowDocSelector] = useState(false);

    useEffect(() => {
        mountedRef.current = true;
        return () => { mountedRef.current = false; };
    }, []);

    // On mount, check if a background request completed while we were away
    useEffect(() => {
        try {
            const pending = sessionStorage.getItem(XAI_PENDING_KEY);
            if (pending) {
                const { paragraph, question, userMessageId } = JSON.parse(pending);
                // Re-fire the request if still pending
                if (sessionStorage.getItem(XAI_LOADING_KEY) === "true") {
                    setIsLoading(true);
                    api.askQuestion(paragraph, question).then((response) => {
                        const botMessage: ChatMessage = {
                            id: (parseInt(userMessageId) + 1).toString(),
                            role: "bot",
                            content: response.answer,
                            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                            confidence: response.confidence,
                        };
                        setMessages((prev) => {
                            const updated = [...prev, botMessage];
                            saveMessages(updated);
                            return updated;
                        });
                        setCurrentExplanation(response.explanation);
                        sessionStorage.setItem("xai_explanation", JSON.stringify(response.explanation));
                        sessionStorage.setItem("xai_question", question);
                        sessionStorage.setItem("xai_paragraph", paragraph);
                        localStorage.setItem("xai_explanation", JSON.stringify(response.explanation));
                        localStorage.setItem("xai_question", question);
                        localStorage.setItem("xai_paragraph", paragraph);
                    }).catch((err) => {
                        const errorMessage: ChatMessage = {
                            id: (parseInt(userMessageId) + 1).toString(),
                            role: "bot",
                            content: `Unable to process your question. Error: ${err instanceof Error ? err.message : "Unknown error"}`,
                            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                        };
                        setMessages((prev) => {
                            const updated = [...prev, errorMessage];
                            saveMessages(updated);
                            return updated;
                        });
                    }).finally(() => {
                        setIsLoading(false);
                        sessionStorage.removeItem(XAI_PENDING_KEY);
                        sessionStorage.removeItem(XAI_LOADING_KEY);
                    });
                }
            }
        } catch { /* */ }
    }, []);

    // Load extracted documents from sessionStorage (saved by IDPO page after processing)
    useEffect(() => {
        try {
            const stored = sessionStorage.getItem("idpo_extracted_docs");
            if (stored) {
                const docs: ExtractedDoc[] = JSON.parse(stored);
                if (docs.length > 0) {
                    setExtractedDocs(docs);
                    setSelectedDocId(docs[0].id);
                }
            }
        } catch {
            // Silently fail
        }
    }, []);

    // Get the active paragraph text based on selection (only extracted docs or custom text)
    const getActiveParagraph = (): string => {
        if (selectedDocId === "custom") return customText;
        const doc = extractedDocs.find(d => d.id === selectedDocId);
        return doc?.text || "";
    };

    const getActiveLabel = (): string => {
        if (selectedDocId === "custom") return "Custom Text";
        const doc = extractedDocs.find(d => d.id === selectedDocId);
        return doc?.filename || "No document selected";
    };

    // Check if we have a valid context for Q&A
    const hasValidContext = (): boolean => {
        if (selectedDocId === "custom") return customText.trim().length > 0;
        return extractedDocs.some(d => d.id === selectedDocId);
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isLoading || !hasValidContext()) return;

        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            role: "user",
            content: input.trim(),
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        };

        const activeParagraph = getActiveParagraph();

        setMessages((prev) => {
            const updated = [...prev, userMessage];
            saveMessages(updated);
            return updated;
        });
        setInput("");
        setIsLoading(true);

        // Save pending request so it can be resumed if user navigates away
        sessionStorage.setItem(XAI_PENDING_KEY, JSON.stringify({
            paragraph: activeParagraph,
            question: userMessage.content,
            userMessageId: userMessage.id,
        }));
        sessionStorage.setItem(XAI_LOADING_KEY, "true");

        try {
            const response = await api.askQuestion(activeParagraph, userMessage.content);

            const botMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                role: "bot",
                content: response.answer,
                timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                confidence: response.confidence,
            };

            // Always persist to storage (even if unmounted)
            const currentMsgs = JSON.parse(sessionStorage.getItem(XAI_MESSAGES_KEY) || "[]");
            currentMsgs.push(botMessage);
            saveMessages(currentMsgs);

            sessionStorage.setItem("xai_explanation", JSON.stringify(response.explanation));
            sessionStorage.setItem("xai_question", userMessage.content);
            sessionStorage.setItem("xai_paragraph", activeParagraph);
            localStorage.setItem("xai_explanation", JSON.stringify(response.explanation));
            localStorage.setItem("xai_question", userMessage.content);
            localStorage.setItem("xai_paragraph", activeParagraph);

            if (mountedRef.current) {
                setMessages((prev) => [...prev, botMessage]);
                setCurrentExplanation(response.explanation);
                if (response.confidence >= 0) {
                    addToast({ type: "success", title: "Answer received", message: `Confidence: ${(response.confidence * 100).toFixed(0)}%` });
                }
            }
        } catch (err) {
            const errorMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                role: "bot",
                content: `Unable to process your question. Please ensure the XAI service is running. Error: ${err instanceof Error ? err.message : "Unknown error"}`,
                timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            };

            const currentMsgs = JSON.parse(sessionStorage.getItem(XAI_MESSAGES_KEY) || "[]");
            currentMsgs.push(errorMessage);
            saveMessages(currentMsgs);

            if (mountedRef.current) {
                setMessages((prev) => [...prev, errorMessage]);
                addToast({ type: "error", title: "XAI Error", message: "Could not get answer from XAI service" });
            }
        } finally {
            sessionStorage.removeItem(XAI_PENDING_KEY);
            sessionStorage.removeItem(XAI_LOADING_KEY);
            if (mountedRef.current) {
                setIsLoading(false);
            }
        }
    };

    return (
        <div className="max-w-4xl 3xl:max-w-5xl mx-auto">
            {/* Header */}
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6 mb-6">
                <div className="absolute inset-0 bg-gradient-to-r from-violet-500/5 to-purple-500/5 dark:from-violet-500/[0.03] dark:to-purple-500/[0.03]" />
                <div className="relative flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-400 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-500/20">
                                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                            </div>
                            XAI Q&A System
                        </h1>
                        <p className="text-slate-500 dark:text-gray-400 mt-1.5 text-sm">
                            Ask questions about your documents and see explainable AI analysis
                        </p>
                    </div>
                    <Link
                        href="/dashboard/hitl"
                        className="px-4 py-2.5 bg-amber-50 dark:bg-amber-500/10 border border-amber-200/60 dark:border-amber-500/20 text-amber-700 dark:text-amber-300 rounded-xl hover:bg-amber-100 dark:hover:bg-amber-500/20 transition-all duration-200 text-sm font-semibold shadow-sm"
                    >
                        👤 Expert Review
                    </Link>
                </div>
            </div>

            {/* Document Context Selector */}
            <div className="mb-4 space-y-3">
                <button
                    onClick={() => setShowDocSelector(!showDocSelector)}
                    className="w-full px-4 py-3 glass-panel rounded-lg text-left hover:bg-white/80 dark:hover:bg-gray-800/60 transition-all duration-150"
                >
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className="text-sm">📄</span>
                            <span className="text-slate-700 dark:text-gray-300 text-sm font-medium">
                                Context: {getActiveLabel()}
                            </span>
                            {extractedDocs.length > 0 && selectedDocId !== "default" && (
                                <span className="px-2 py-0.5 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-300 rounded-full text-[10px] font-medium">
                                    Connected
                                </span>
                            )}
                        </div>
                        <span className="text-slate-400 dark:text-gray-500 transition-transform duration-150" style={{ transform: showDocSelector ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
                    </div>
                </button>

                {showDocSelector && (
                    <div className="glass-panel rounded-lg p-4 space-y-3">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Select Extracted Document</p>
                        {extractedDocs.length > 0 ? (
                            <div className="space-y-1.5">
                                {extractedDocs.map(doc => (
                                    <button
                                        key={doc.id}
                                        onClick={() => setSelectedDocId(doc.id)}
                                        className={`w-full text-left px-3 py-2.5 rounded-lg text-xs font-medium transition-all border ${selectedDocId === doc.id
                                            ? "bg-brand-50 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300"
                                            : "border-transparent text-slate-600 dark:text-gray-400 hover:bg-slate-50 dark:hover:bg-gray-800"}`}
                                    >
                                        📄 {doc.filename} <span className="text-slate-400 dark:text-gray-500 ml-1">({(doc.text.length / 1000).toFixed(1)}k chars)</span>
                                    </button>
                                ))}
                                <button
                                    onClick={() => setSelectedDocId("custom")}
                                    className={`w-full text-left px-3 py-2.5 rounded-lg text-xs font-medium transition-all border ${selectedDocId === "custom"
                                        ? "bg-brand-50 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300"
                                        : "border-transparent text-slate-600 dark:text-gray-400 hover:bg-slate-50 dark:hover:bg-gray-800"}`}
                                >
                                    ✏️ Custom Text
                                </button>
                            </div>
                        ) : (
                            <div className="p-4 bg-amber-50/50 dark:bg-amber-500/5 rounded-lg border border-amber-200 dark:border-amber-500/10 text-center">
                                <span className="text-2xl block mb-2">📄</span>
                                <p className="text-sm font-medium text-amber-700 dark:text-amber-300 mb-1">No Extracted Documents</p>
                                <p className="text-[11px] text-amber-600 dark:text-amber-400 mb-3">
                                    Process documents in the Document Extraction page first to ask questions about them.
                                </p>
                                <Link
                                    href="/dashboard/idpo"
                                    className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand-500 text-white rounded-lg text-xs font-medium hover:bg-brand-600 transition-colors"
                                >
                                    Go to Document Extraction →
                                </Link>
                            </div>
                        )}
                        {selectedDocId === "custom" && (
                            <textarea
                                value={customText}
                                onChange={(e) => setCustomText(e.target.value)}
                                placeholder="Paste your own text here to ask questions about it..."
                                rows={5}
                                className="w-full glass-input px-3 py-2 text-xs rounded-lg resize-none"
                            />
                        )}
                    </div>
                )}
            </div>

            {/* Context Paragraph Toggle */}
            <button
                onClick={() => setShowParagraph(!showParagraph)}
                className="w-full mb-4 px-4 py-3 glass-panel rounded-lg text-left hover:bg-white/80 dark:hover:bg-gray-800/60 transition-all duration-150"
            >
                <div className="flex items-center justify-between">
                    <span className="text-slate-700 dark:text-gray-300 text-sm font-medium">View Context Text</span>
                    <span className="text-slate-400 dark:text-gray-500 transition-transform duration-150" style={{ transform: showParagraph ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
                </div>
            </button>

            {showParagraph && (
                <div className="mb-6 p-5 glass-panel rounded-lg border-l-4 border-l-brand-500 max-h-[300px] overflow-y-auto">
                    <p className="text-slate-700 dark:text-gray-300 leading-relaxed text-sm whitespace-pre-wrap">{getActiveParagraph()}</p>
                </div>
            )}

            {/* Chat Container */}
            <div className="glass-panel rounded-2xl overflow-hidden flex flex-col h-[600px]">
                {/* Messages Area */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6 scroll-smooth">
                    {messages.length === 0 ? (
                        <div className="h-full flex items-center justify-center">
                            {!hasValidContext() ? (
                                <div className="text-center text-slate-400 max-w-md">
                                    <div className="w-16 h-16 mx-auto rounded-2xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200/60 dark:border-amber-500/20 flex items-center justify-center mb-4">
                                        <span className="text-3xl">📄</span>
                                    </div>
                                    <p className="text-lg font-bold text-slate-600 dark:text-gray-300">No Document Context</p>
                                    <p className="text-sm mt-2 text-slate-500 dark:text-gray-500 mb-4">
                                        Extract documents using the IDPO pipeline first, then come back here to ask questions about the extracted content.
                                    </p>
                                    <Link
                                        href="/dashboard/idpo"
                                        className="inline-flex items-center gap-2 px-5 py-2.5 bg-brand-500 text-white rounded-lg text-sm font-medium hover:bg-brand-600 transition-colors"
                                    >
                                        <span>📋</span> Go to Document Extraction
                                    </Link>
                                </div>
                            ) : (
                                <div className="text-center text-slate-400">
                                    <div className="w-16 h-16 mx-auto rounded-2xl bg-violet-50 dark:bg-violet-500/10 border border-violet-200/60 dark:border-violet-500/20 flex items-center justify-center mb-4">
                                        <span className="text-3xl">💬</span>
                                    </div>
                                    <p className="text-lg font-bold text-slate-600 dark:text-gray-300">Ask a question about your document</p>
                                    <p className="text-sm mt-2 text-slate-500 dark:text-gray-500">
                                        Using: {getActiveLabel()}
                                    </p>
                                </div>
                            )}
                        </div>
                    ) : (
                        messages.map((msg) => (
                            <div
                                key={msg.id}
                                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                            >
                                <div
                                    className={`max-w-[80%] rounded-2xl px-5 py-4 shadow-sm ${msg.role === "user"
                                        ? "bg-brand-600/90 backdrop-blur-md text-white rounded-br-sm border border-brand-500/20"
                                        : "bg-white/80 dark:bg-gray-800/80 backdrop-blur-md text-slate-800 dark:text-gray-200 rounded-bl-sm border border-slate-200 dark:border-gray-700"
                                        }`}
                                >
                                    <p className="text-sm leading-relaxed">{msg.content}</p>
                                    <div className="flex items-center justify-between mt-3 gap-4">
                                        <span className="text-[10px] opacity-60 font-medium tracking-wider uppercase">{msg.timestamp}</span>
                                        {msg.confidence !== undefined && msg.confidence >= 0 && (
                                            <span
                                                className={`text-[10px] px-2.5 py-1 rounded-full font-medium tracking-wide border ${msg.confidence >= 0.7
                                                    ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20"
                                                    : msg.confidence >= 0.4
                                                        ? "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/20"
                                                        : "bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-500/20"
                                                    }`}
                                            >
                                                {(msg.confidence * 100).toFixed(0)}% confidence
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                    {isLoading && (
                        <div className="flex justify-start">
                            <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-md border border-slate-200 dark:border-gray-700 rounded-2xl rounded-bl-sm px-5 py-4 shadow-sm">
                                <div className="flex items-center gap-2">
                                    <div className="w-2 h-2 bg-brand-400 rounded-full animate-bounce" />
                                    <div className="w-2 h-2 bg-brand-400 rounded-full animate-bounce [animation-delay:0.2s]" />
                                    <div className="w-2 h-2 bg-brand-400 rounded-full animate-bounce [animation-delay:0.4s]" />
                                </div>
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                {/* Input Area */}
                <form onSubmit={handleSubmit} className="border-t border-slate-200 dark:border-gray-700 p-4 bg-white/50 dark:bg-gray-900/50 backdrop-blur-xl">
                    <div className="flex gap-3">
                        <input
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder={hasValidContext() ? "Type your question about the extracted document..." : "Extract a document first to ask questions..."}
                            disabled={isLoading || !hasValidContext()}
                            className="flex-1 glass-input rounded-full px-6 py-3.5 text-sm disabled:opacity-50"
                        />
                        <button
                            type="submit"
                            disabled={isLoading || !input.trim() || !hasValidContext()}
                            className="px-8 py-3.5 glass-button rounded-full disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                            <span>Send</span>
                            <span className="text-lg leading-none">↗</span>
                        </button>
                    </div>
                </form>
            </div>

            {/* XAI Button */}
            {currentExplanation && (
                <div className="mt-6 text-center">
                    <Link
                        href="/dashboard/xai/explanation"
                        className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-purple-500 to-indigo-600 text-white font-medium rounded-full hover:from-purple-400 hover:to-indigo-500 transition-all shadow-lg shadow-purple-500/20"
                    >
                        <span>✨</span>
                        See How the Answer Was Derived
                        <span>→</span>
                    </Link>
                </div>
            )}

            {/* Footer */}
            <div className="mt-8 text-center text-slate-400 dark:text-gray-600 text-xs font-medium tracking-wider uppercase">
                Document Q&A with Explainable AI
            </div>
        </div>
    );
}


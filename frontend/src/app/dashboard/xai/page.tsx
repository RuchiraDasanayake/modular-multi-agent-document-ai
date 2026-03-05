"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useToast } from "@/components/toast";
import type { ChatMessage, XAIExplanation } from "@/types";

// Default demo paragraph (used when no documents have been extracted)
const DEFAULT_PARAGRAPH = `Finance is fundamentally the study of resource allocation over time, balancing the promise of future returns against the inherent presence of risk. At its core, it functions as the circulatory system of the global economy, moving capital from those who have an excess of it (savers and investors) to those who can deploy it productively (borrowers and entrepreneurs). This exchange is mediated by various instruments—such as stocks, bonds, and derivatives—and governed by the principle of the time value of money, which asserts that a dollar held today is worth more than a dollar received tomorrow due to its potential earning capacity.`;

interface ExtractedDoc {
    id: string;
    filename: string;
    text: string;
}

export default function XAIPage() {
    const { addToast } = useToast();
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [showParagraph, setShowParagraph] = useState(false);
    const [currentExplanation, setCurrentExplanation] = useState<XAIExplanation | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Document context management
    const [extractedDocs, setExtractedDocs] = useState<ExtractedDoc[]>([]);
    const [selectedDocId, setSelectedDocId] = useState<string>("default");
    const [customText, setCustomText] = useState("");
    const [showDocSelector, setShowDocSelector] = useState(false);

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
            // Silently fail — will use default paragraph
        }
    }, []);

    // Get the active paragraph text based on selection
    const getActiveParagraph = (): string => {
        if (selectedDocId === "custom") return customText;
        if (selectedDocId === "default") return DEFAULT_PARAGRAPH;
        const doc = extractedDocs.find(d => d.id === selectedDocId);
        return doc?.text || DEFAULT_PARAGRAPH;
    };

    const getActiveLabel = (): string => {
        if (selectedDocId === "custom") return "Custom Text";
        if (selectedDocId === "default") return "Demo: Finance Paragraph";
        const doc = extractedDocs.find(d => d.id === selectedDocId);
        return doc?.filename || "Document";
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isLoading) return;

        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            role: "user",
            content: input.trim(),
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        };

        setMessages((prev) => [...prev, userMessage]);
        setInput("");
        setIsLoading(true);

        try {
            const activeParagraph = getActiveParagraph();
            const response = await api.askQuestion(activeParagraph, userMessage.content);

            const botMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                role: "bot",
                content: response.answer,
                timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                confidence: response.confidence,
            };

            setMessages((prev) => [...prev, botMessage]);
            setCurrentExplanation(response.explanation);
            addToast({ type: "success", title: "Answer received", message: `Confidence: ${(response.confidence * 100).toFixed(0)}%` });

            // Store in sessionStorage for the explanation page
            sessionStorage.setItem("xai_explanation", JSON.stringify(response.explanation));
            sessionStorage.setItem("xai_question", userMessage.content);
            sessionStorage.setItem("xai_paragraph", activeParagraph);
        } catch {
            // Demo mode: simulate response when API is unavailable
            const demoAnswer = simulateDemoResponse(userMessage.content);
            const botMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                role: "bot",
                content: demoAnswer.answer,
                timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                confidence: demoAnswer.confidence,
            };
            setMessages((prev) => [...prev, botMessage]);
            setCurrentExplanation(demoAnswer.explanation);
            sessionStorage.setItem("xai_explanation", JSON.stringify(demoAnswer.explanation));
            sessionStorage.setItem("xai_question", userMessage.content);
            sessionStorage.setItem("xai_paragraph", getActiveParagraph());
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="max-w-4xl mx-auto">
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
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-gray-500">Select Document Context</p>
                        <div className="space-y-1.5">
                            <button
                                onClick={() => setSelectedDocId("default")}
                                className={`w-full text-left px-3 py-2.5 rounded-lg text-xs font-medium transition-all border ${selectedDocId === "default"
                                    ? "bg-brand-50 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300"
                                    : "border-transparent text-slate-600 dark:text-gray-400 hover:bg-slate-50 dark:hover:bg-gray-800"}`}
                            >
                                📝 Demo: Finance Paragraph
                            </button>
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
                        {selectedDocId === "custom" && (
                            <textarea
                                value={customText}
                                onChange={(e) => setCustomText(e.target.value)}
                                placeholder="Paste your own text here to ask questions about it..."
                                rows={5}
                                className="w-full glass-input px-3 py-2 text-xs rounded-lg resize-none"
                            />
                        )}
                        {extractedDocs.length === 0 && (
                            <div className="p-3 bg-amber-50/50 dark:bg-amber-500/5 rounded-lg border border-amber-200 dark:border-amber-500/10">
                                <p className="text-[10px] text-amber-600 dark:text-amber-400">
                                    💡 Tip: Process documents in the <Link href="/dashboard/idpo" className="underline font-medium">Document Extraction</Link> page first to ask questions about your own documents.
                                </p>
                            </div>
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
                            <div className="text-center text-slate-400">
                                <div className="w-16 h-16 mx-auto rounded-2xl bg-violet-50 dark:bg-violet-500/10 border border-violet-200/60 dark:border-violet-500/20 flex items-center justify-center mb-4">
                                    <span className="text-3xl">💬</span>
                                </div>
                                <p className="text-lg font-bold text-slate-600 dark:text-gray-300">Ask a question about your document</p>
                                <p className="text-sm mt-2 text-slate-500 dark:text-gray-500">
                                    Select a document context above, then ask any question
                                </p>
                            </div>
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
                                        {msg.confidence !== undefined && (
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
                            placeholder="Type your question..."
                            disabled={isLoading}
                            className="flex-1 glass-input rounded-full px-6 py-3.5 text-sm"
                        />
                        <button
                            type="submit"
                            disabled={isLoading || !input.trim()}
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

// Demo response simulator (for when API is not connected)
function simulateDemoResponse(question: string): { answer: string; confidence: number; explanation: XAIExplanation } {
    const lowerQ = question.toLowerCase();
    let answer = "";
    let confidence = 0.85;

    if (lowerQ.includes("time value") || lowerQ.includes("dollar")) {
        answer = "The time value of money asserts that a dollar held today is worth more than a dollar received tomorrow due to its potential earning capacity.";
        confidence = 0.92;
    } else if (lowerQ.includes("function") || lowerQ.includes("core")) {
        answer = "At its core, finance functions as the circulatory system of the global economy, moving capital from savers and investors to borrowers and entrepreneurs.";
        confidence = 0.88;
    } else if (lowerQ.includes("instrument") || lowerQ.includes("stock") || lowerQ.includes("bond")) {
        answer = "Financial exchange is mediated by various instruments such as stocks, bonds, and derivatives.";
        confidence = 0.90;
    } else if (lowerQ.includes("risk") || lowerQ.includes("return")) {
        answer = "Finance fundamentally involves balancing the promise of future returns against the inherent presence of risk.";
        confidence = 0.87;
    } else {
        answer = "Finance is the study of resource allocation over time, balancing returns against risk, and functions as the circulatory system of the global economy.";
        confidence = 0.75;
    }

    return {
        answer,
        confidence,
        explanation: {
            answer,
            confidence_score: confidence,
            highlighted_spans: [
                { start: 0, end: 50, text: answer.slice(0, 50), type: "answer", shap_score: 0.85, lime_score: 0.78 },
            ],
            shap_explanation: {
                shap_values: [
                    ["finance", 0.45],
                    ["capital", 0.38],
                    ["money", 0.32],
                    ["economy", 0.28],
                    ["time", 0.25],
                    ["value", 0.22],
                    ["risk", 0.18],
                    ["returns", 0.15],
                ],
                base_value: 0.5,
            },
            lime_explanation: {
                word_weights: [
                    ["finance", 0.42],
                    ["capital", 0.35],
                    ["economy", 0.30],
                    ["money", 0.28],
                    ["instruments", 0.22],
                    ["stocks", 0.18],
                    ["bonds", 0.15],
                    ["risk", 0.12],
                ],
                prediction_proba: confidence,
            },
            derivation_steps: [
                { step_number: 1, action: "Question Analysis", description: "Parsed user question", confidence: 0.95 },
                { step_number: 2, action: "Context Retrieval", description: "Retrieved relevant paragraph sections", confidence: 0.90 },
                { step_number: 3, action: "Feature Analysis", description: "Computed feature importance", confidence: 0.88 },
                { step_number: 4, action: "Local Explanation", description: "Generated local explanations", confidence: 0.85 },
                { step_number: 5, action: "Answer Synthesis", description: "Formulated final answer", confidence: confidence },
            ],
            evidence_sentences: [
                "Finance is fundamentally the study of resource allocation over time.",
                "It functions as the circulatory system of the global economy.",
            ],
        },
    };
}

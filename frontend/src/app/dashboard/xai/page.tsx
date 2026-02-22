"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { ChatMessage, XAIExplanation } from "@/types";

// Default demo paragraph
const DEFAULT_PARAGRAPH = `Finance is fundamentally the study of resource allocation over time, balancing the promise of future returns against the inherent presence of risk. At its core, it functions as the circulatory system of the global economy, moving capital from those who have an excess of it (savers and investors) to those who can deploy it productively (borrowers and entrepreneurs). This exchange is mediated by various instruments—such as stocks, bonds, and derivatives—and governed by the principle of the time value of money, which asserts that a dollar held today is worth more than a dollar received tomorrow due to its potential earning capacity.`;

export default function XAIPage() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [showParagraph, setShowParagraph] = useState(false);
    const [currentExplanation, setCurrentExplanation] = useState<XAIExplanation | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

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
            const response = await api.askQuestion(DEFAULT_PARAGRAPH, userMessage.content);

            const botMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                role: "bot",
                content: response.answer,
                timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                confidence: response.confidence,
            };

            setMessages((prev) => [...prev, botMessage]);
            setCurrentExplanation(response.explanation);

            // Store in sessionStorage for the explanation page
            sessionStorage.setItem("xai_explanation", JSON.stringify(response.explanation));
            sessionStorage.setItem("xai_question", userMessage.content);
            sessionStorage.setItem("xai_paragraph", DEFAULT_PARAGRAPH);
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
            sessionStorage.setItem("xai_paragraph", DEFAULT_PARAGRAPH);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="max-w-4xl mx-auto">
            {/* Header */}
            <div className="glass-panel rounded-xl p-6 mb-6">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
                            <span className="text-3xl drop-shadow-sm">🧠</span>
                            XAI Q&A System
                        </h1>
                        <p className="text-slate-500 dark:text-gray-400 mt-1">
                            Ask questions about finance and see explainable AI analysis
                        </p>
                    </div>
                    <Link
                        href="/dashboard/hitl"
                        className="px-4 py-2 bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 rounded-lg hover:bg-brand-100 dark:hover:bg-brand-500/20 transition-all duration-150 text-sm font-medium shadow-sm shadow-brand-500/5"
                    >
                        👤 HITL Review
                    </Link>
                </div>
            </div>

            {/* Context Paragraph Toggle */}
            <button
                onClick={() => setShowParagraph(!showParagraph)}
                className="w-full mb-4 px-4 py-3 glass-panel rounded-lg text-left hover:bg-white/80 dark:hover:bg-gray-800/60 transition-all duration-150"
            >
                <div className="flex items-center justify-between">
                    <span className="text-slate-700 dark:text-gray-300 text-sm font-medium">View Context Paragraph</span>
                    <span className="text-slate-400 dark:text-gray-500 transition-transform duration-150" style={{ transform: showParagraph ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
                </div>
            </button>

            {showParagraph && (
                <div className="mb-6 p-5 glass-panel rounded-lg border-l-4 border-l-brand-500">
                    <p className="text-slate-700 dark:text-gray-300 leading-relaxed text-sm">{DEFAULT_PARAGRAPH}</p>
                </div>
            )}

            {/* Chat Container */}
            <div className="glass-panel rounded-xl overflow-hidden flex flex-col h-[600px]">
                {/* Messages Area */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6 scroll-smooth">
                    {messages.length === 0 ? (
                        <div className="h-full flex items-center justify-center">
                            <div className="text-center text-slate-400">
                                <span className="text-5xl mb-4 block drop-shadow-sm">💬</span>
                                <p className="text-lg font-medium text-slate-600 dark:text-gray-300">Ask a question about the finance paragraph</p>
                                <p className="text-sm mt-2 text-slate-500 dark:text-gray-500">
                                    Try: &ldquo;What is the time value of money?&rdquo;
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
            <div className="mt-8 text-center text-gray-500 text-sm">
                Finance Q&A with Explainable AI | Powered by SHAP & LIME
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
                { step_number: 3, action: "SHAP Analysis", description: "Computed feature importance", confidence: 0.88 },
                { step_number: 4, action: "LIME Analysis", description: "Generated local explanations", confidence: 0.85 },
                { step_number: 5, action: "Answer Synthesis", description: "Formulated final answer", confidence: confidence },
            ],
            evidence_sentences: [
                "Finance is fundamentally the study of resource allocation over time.",
                "It functions as the circulatory system of the global economy.",
            ],
        },
    };
}

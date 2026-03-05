"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import type { XAIExplanation } from "@/types";

export default function ExplanationPage() {
    const [explanation, setExplanation] = useState<XAIExplanation | null>(null);
    const [question, setQuestion] = useState("");
    const [paragraph, setParagraph] = useState("");
    const [activeTab, setActiveTab] = useState<"shap" | "lime" | "derivation">("shap");

    useEffect(() => {
        // Load from sessionStorage
        const storedExplanation = sessionStorage.getItem("xai_explanation");
        const storedQuestion = sessionStorage.getItem("xai_question");
        const storedParagraph = sessionStorage.getItem("xai_paragraph");

        if (storedExplanation) {
            try { setExplanation(JSON.parse(storedExplanation)); } catch { /* invalid data */ }
        }
        if (storedQuestion) setQuestion(storedQuestion);
        if (storedParagraph) setParagraph(storedParagraph);
    }, []);

    if (!explanation) {
        return (
            <div className="max-w-4xl mx-auto">
                <div className="bg-white/80 dark:bg-gray-800/50 border border-slate-200 dark:border-gray-700 rounded-xl p-8 text-center">
                    <span className="text-5xl mb-4 block">🔍</span>
                    <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">No Explanation Available</h2>
                    <p className="text-slate-500 dark:text-gray-400 mb-6">Please ask a question first to see the XAI analysis.</p>
                    <Link
                        href="/dashboard/xai"
                        className="inline-flex items-center gap-2 px-6 py-3 bg-brand-500 text-slate-900 dark:text-white font-medium rounded-lg hover:bg-brand-400 transition-colors"
                    >
                        ← Back to Q&A
                    </Link>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-5xl mx-auto space-y-6">
            {/* Header */}
            <div className="bg-white/80 dark:bg-gray-800/50 border border-slate-200 dark:border-gray-700 rounded-xl p-6">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
                            <span className="text-3xl">✨</span>
                            Explanation Details
                        </h1>
                        <p className="text-slate-500 dark:text-gray-400 mt-1">How the answer was derived</p>
                    </div>
                    <div className="flex gap-3">
                        <Link
                            href="/dashboard/xai"
                            className="px-4 py-2 bg-slate-200 dark:bg-gray-700 text-slate-600 dark:text-gray-300 rounded-lg hover:bg-slate-200 dark:hover:bg-gray-600 transition-colors text-sm font-medium"
                        >
                            ← Back to Q&A
                        </Link>
                        <Link
                            href="/dashboard/hitl"
                            className="px-4 py-2 bg-brand-500/10 text-brand-400 rounded-lg hover:bg-brand-500/20 transition-colors text-sm font-medium"
                        >
                            👤 Expert Review
                        </Link>
                    </div>
                </div>
            </div>

            {/* Question & Answer Cards */}
            <div className="grid md:grid-cols-2 gap-4">
                {/* Question */}
                <div className="bg-white/60 dark:bg-gray-800/30 border border-slate-200 dark:border-gray-700 rounded-xl p-5">
                    <div className="text-xs font-semibold text-brand-400 uppercase tracking-wide mb-2">
                        Question
                    </div>
                    <p className="text-slate-900 dark:text-white text-lg font-medium">{question}</p>
                </div>

                {/* Answer */}
                <div className="bg-white/60 dark:bg-gray-800/30 border border-slate-200 dark:border-gray-700 rounded-xl p-5">
                    <div className="text-xs font-semibold text-green-400 uppercase tracking-wide mb-2">
                        Answer
                    </div>
                    <p className="text-slate-700 dark:text-gray-200">{explanation.answer}</p>
                    <div className="mt-3">
                        <span
                            className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${explanation.confidence_score >= 0.7
                                ? "bg-green-500/20 text-green-400"
                                : explanation.confidence_score >= 0.4
                                    ? "bg-yellow-500/20 text-yellow-400"
                                    : "bg-red-500/20 text-red-400"
                                }`}
                        >
                            Confidence: {(explanation.confidence_score * 100).toFixed(0)}%
                        </span>
                    </div>
                </div>
            </div>

            {/* Highlighted Context */}
            <div className="bg-white/60 dark:bg-gray-800/30 border border-slate-200 dark:border-gray-700 rounded-xl p-5">
                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Highlighted Context</h3>

                {/* Legend */}
                <div className="flex flex-wrap gap-4 mb-4 text-sm">
                    <div className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-yellow-500/30 border-b-2 border-yellow-500" />
                        <span className="text-slate-500 dark:text-gray-400">Model Answer</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-green-500/30 border-b-2 border-green-500" />
                        <span className="text-slate-500 dark:text-gray-400">Positive Contribution</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-red-500/30 border-b-2 border-red-500" />
                        <span className="text-slate-500 dark:text-gray-400">Negative Contribution</span>
                    </div>
                </div>

                {/* Paragraph with highlights */}
                <div className="bg-slate-50 dark:bg-gray-900/50 rounded-lg p-4 leading-relaxed text-slate-600 dark:text-gray-300">
                    <HighlightedParagraph text={paragraph} spans={explanation.highlighted_spans} />
                </div>
            </div>

            {/* Tabs for Analysis */}
            <div className="bg-white/60 dark:bg-gray-800/30 border border-slate-200 dark:border-gray-700 rounded-xl overflow-hidden">
                {/* Tab Headers */}
                <div className="flex border-b border-slate-200 dark:border-gray-700">
                    {[
                        { id: "shap" as const, label: "Feature Importance", icon: "📊" },
                        { id: "lime" as const, label: "Word Analysis", icon: "🍋" },
                        { id: "derivation" as const, label: "Derivation Logic", icon: "🔬" },
                    ].map((tab) => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${activeTab === tab.id
                                ? "bg-brand-500/10 text-brand-400 border-b-2 border-brand-500"
                                : "text-slate-500 dark:text-gray-400 hover:text-slate-700 dark:text-gray-200 hover:bg-slate-100 dark:hover:bg-slate-50 dark:bg-gray-800/50"
                                }`}
                        >
                            <span className="mr-2">{tab.icon}</span>
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* Tab Content */}
                <div className="p-5">
                    {activeTab === "shap" && (
                        <SHAPAnalysis values={explanation.shap_explanation.shap_values} />
                    )}
                    {activeTab === "lime" && (
                        <LIMEAnalysis
                            weights={explanation.lime_explanation.word_weights}
                            proba={explanation.lime_explanation.prediction_proba}
                        />
                    )}
                    {activeTab === "derivation" && (
                        <DerivationLogic
                            steps={explanation.derivation_steps}
                            evidence={explanation.evidence_sentences}
                        />
                    )}
                </div>
            </div>

            {/* Footer */}
            <div className="text-center text-slate-500 dark:text-gray-500 text-sm py-4">
                Finance Q&A with Explainable AI | AI-Powered Analysis
            </div>
        </div>
    );
}

// ── Sub-components ──

function HighlightedParagraph({
    text,
    spans,
}: {
    text: string;
    spans: XAIExplanation["highlighted_spans"];
}) {
    if (!spans || spans.length === 0) {
        return <span>{text}</span>;
    }

    // Highlight keywords using React elements (safe, no XSS risk)
    const keywords = ["finance", "capital", "economy", "money", "risk", "returns", "time value"];
    const pattern = new RegExp(`(${keywords.join("|")})`, "gi");
    const parts = text.split(pattern);

    return (
        <span>
            {parts.map((part, i) =>
                keywords.some((kw) => kw.toLowerCase() === part.toLowerCase()) ? (
                    <mark key={i} className="bg-yellow-500/30 text-yellow-200 px-1 rounded">{part}</mark>
                ) : (
                    <span key={i}>{part}</span>
                )
            )}
        </span>
    );
}

function SHAPAnalysis({ values }: { values: Array<[string, number]> }) {
    const maxValue = Math.max(...values.map(([, v]) => Math.abs(v)));

    return (
        <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">Feature Importance</h3>
            <p className="text-slate-500 dark:text-gray-400 text-sm mb-4">
                Shows how each feature contributes to the prediction.
            </p>

            <div className="space-y-3">
                {values.slice(0, 10).map(([word, value], idx) => (
                    <div key={idx} className="flex items-center gap-3">
                        <span className="w-24 text-sm text-slate-600 dark:text-gray-300 font-medium truncate">{word}</span>
                        <div className="flex-1 h-6 bg-slate-100 dark:bg-gray-800 rounded-full overflow-hidden relative">
                            <div
                                className={`h-full rounded-full transition-all ${value >= 0 ? "bg-green-500" : "bg-red-500"
                                    }`}
                                style={{
                                    width: `${(Math.abs(value) / maxValue) * 100}%`,
                                    marginLeft: value < 0 ? "auto" : 0,
                                }}
                            />
                        </div>
                        <span
                            className={`w-16 text-sm font-mono ${value >= 0 ? "text-green-400" : "text-red-400"
                                }`}
                        >
                            {value >= 0 ? "+" : ""}
                            {value.toFixed(3)}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}

function LIMEAnalysis({
    weights,
    proba,
}: {
    weights: Array<[string, number]>;
    proba: number;
}) {
    const maxWeight = Math.max(...weights.map(([, w]) => Math.abs(w)));

    return (
        <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">Word-Level Explanation</h3>
            <p className="text-slate-500 dark:text-gray-400 text-sm mb-4">
                Shows word-level contribution to the prediction.
            </p>

            <div className="mb-6 inline-flex items-center px-4 py-2 bg-brand-500/10 rounded-lg">
                <span className="text-slate-500 dark:text-gray-400 text-sm mr-2">Prediction Probability:</span>
                <span className="text-brand-400 font-semibold">{(proba * 100).toFixed(1)}%</span>
            </div>

            <div className="space-y-3">
                {weights.slice(0, 10).map(([word, weight], idx) => (
                    <div key={idx} className="flex items-center gap-3">
                        <span className="w-24 text-sm text-slate-600 dark:text-gray-300 font-medium truncate">{word}</span>
                        <div className="flex-1 h-6 bg-slate-100 dark:bg-gray-800 rounded-full overflow-hidden">
                            <div
                                className={`h-full rounded-full transition-all ${weight >= 0 ? "bg-green-500" : "bg-red-500"
                                    }`}
                                style={{ width: `${(Math.abs(weight) / maxWeight) * 100}%` }}
                            />
                        </div>
                        <span
                            className={`w-16 text-sm font-mono ${weight >= 0 ? "text-green-400" : "text-red-400"
                                }`}
                        >
                            {weight >= 0 ? "+" : ""}
                            {weight.toFixed(3)}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}

function DerivationLogic({
    steps,
    evidence,
}: {
    steps: XAIExplanation["derivation_steps"];
    evidence: string[];
}) {
    return (
        <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">Derivation Logic</h3>
            <p className="text-slate-500 dark:text-gray-400 text-sm mb-4">Step-by-step reasoning process.</p>

            {/* Steps */}
            <div className="space-y-3 mb-6">
                {steps.map((step) => (
                    <div
                        key={step.step_number}
                        className="bg-slate-50 dark:bg-gray-800/50 border-l-4 border-brand-500 rounded-r-lg p-4"
                    >
                        <div className="flex items-center justify-between mb-1">
                            <span className="font-semibold text-slate-900 dark:text-white">
                                Step {step.step_number}: {step.action}
                            </span>
                            <span className="px-2 py-0.5 bg-green-500/20 text-green-400 text-xs rounded-full">
                                {(step.confidence * 100).toFixed(0)}%
                            </span>
                        </div>
                        <p className="text-slate-500 dark:text-gray-400 text-sm">{step.description}</p>
                        {step.details && (
                            <p className="text-slate-500 dark:text-gray-500 text-xs mt-2 bg-gray-900/50 p-2 rounded">
                                {step.details}
                            </p>
                        )}
                    </div>
                ))}
            </div>

            {/* Evidence */}
            <div>
                <h4 className="font-semibold text-slate-900 dark:text-white mb-3">Evidence Sentences</h4>
                <div className="space-y-2">
                    {evidence.map((ev, idx) => (
                        <div
                            key={idx}
                            className="bg-yellow-500/10 border-l-4 border-yellow-500 rounded-r-lg p-3"
                        >
                            <span className="text-yellow-200 text-sm">
                                <strong>Evidence {idx + 1}:</strong> {ev}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useToast } from "@/components/toast";
import type { XAIExplanation, FeedbackType, HITLFeedback } from "@/types";

export default function HITLPage() {
    const { addToast } = useToast();
    const [explanation, setExplanation] = useState<XAIExplanation | null>(null);
    const [question, setQuestion] = useState("");
    const [paragraph, setParagraph] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitted, setSubmitted] = useState(false);
    const [feedbackId, setFeedbackId] = useState("");
    const [showHistory, setShowHistory] = useState(false);
    const [history, setHistory] = useState<HITLFeedback[]>([]);

    // Form state
    const [feedbackType, setFeedbackType] = useState<FeedbackType>("correct");
    const [correctedAnswer, setCorrectedAnswer] = useState("");
    const [explanationQuality, setExplanationQuality] = useState(3);
    const [highlightAccuracy, setHighlightAccuracy] = useState(3);
    const [xaiHelpfulness, setXaiHelpfulness] = useState(3);
    const [additionalComments, setAdditionalComments] = useState("");
    const [knowledgeSuggestion, setKnowledgeSuggestion] = useState("");

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

        // Load history from localStorage
        const storedHistory = localStorage.getItem("hitl_history");
        if (storedHistory) {
            try { setHistory(JSON.parse(storedHistory)); } catch { /* invalid data */ }
        }
    }, []);

    /** Build a local HITLFeedback record for the history list. */
    const buildFeedback = (id: string): HITLFeedback => ({
        feedback_id: id,
        timestamp: new Date().toISOString(),
        question,
        original_answer: explanation!.answer,
        feedback_type: feedbackType,
        is_answer_correct: feedbackType === "correct",
        corrected_answer: correctedAnswer || undefined,
        ratings: {
            explanation_quality: explanationQuality,
            highlight_accuracy: highlightAccuracy,
            xai_helpfulness: xaiHelpfulness,
        },
        additional_context: additionalComments || undefined,
        knowledge_update: knowledgeSuggestion || undefined,
        priority: "medium",
        tags: [],
    });

    /** Persist a feedback entry to local history. */
    const persistFeedback = (feedback: HITLFeedback) => {
        const updated = [...history, feedback];
        setHistory(updated);
        localStorage.setItem("hitl_history", JSON.stringify(updated));
    };

    const handleSubmit = async () => {
        if (!explanation) return;

        setIsSubmitting(true);

        try {
            const response = await api.submitFeedback({
                question,
                original_answer: explanation.answer,
                feedback_type: feedbackType,
                corrected_answer: correctedAnswer || undefined,
                explanation_quality: explanationQuality,
                highlight_accuracy: highlightAccuracy,
                xai_helpfulness: xaiHelpfulness,
                additional_context: additionalComments || undefined,
                knowledge_update: knowledgeSuggestion || undefined,
            });

            setFeedbackId(response.feedback_id);
            setSubmitted(true);
            persistFeedback(buildFeedback(response.feedback_id));
            addToast({ type: "success", title: "Feedback submitted", message: "Thank you for helping improve the system" });
        } catch {
            // Demo mode — simulate success when the API is unavailable
            const demoId = `fb_${Date.now()}`;
            setFeedbackId(demoId);
            setSubmitted(true);
            persistFeedback(buildFeedback(demoId));
            addToast({ type: "info", title: "Demo mode", message: "Feedback saved locally" });
        } finally {
            setIsSubmitting(false);
        }
    };

    if (!explanation) {
        return (
            <div className="max-w-4xl mx-auto">
                <div className="bg-white/80 dark:bg-gray-800/50 border border-slate-200 dark:border-gray-700 rounded-2xl p-8 text-center">
                    <div className="w-16 h-16 mx-auto rounded-2xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200/60 dark:border-amber-500/20 flex items-center justify-center mb-4">
                        <span className="text-3xl">👤</span>
                    </div>
                    <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">No Q&A to Review</h2>
                    <p className="text-slate-500 dark:text-gray-400 mb-6">
                        Please ask a question first to provide feedback.
                    </p>
                    <Link
                        href="/dashboard/xai"
                        className="inline-flex items-center gap-2 px-6 py-3 bg-brand-500 text-slate-900 dark:text-white font-medium rounded-lg hover:bg-brand-400 transition-colors"
                    >
                        ← Go to Q&A
                    </Link>
                </div>
            </div>
        );
    }

    if (submitted) {
        return (
            <div className="max-w-4xl mx-auto">
                <div className="glass-panel rounded-2xl p-8 text-center border-green-500/20">
                    <div className="w-20 h-20 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-green-400 to-emerald-500 flex items-center justify-center shadow-lg shadow-green-500/20">
                        <svg className="w-10 h-10 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                    </div>
                    <h2 className="text-2xl font-extrabold text-slate-900 dark:text-white mb-2">Feedback Submitted!</h2>
                    <p className="text-slate-500 dark:text-gray-400 mb-2">Thank you for helping improve the system.</p>
                    <p className="text-slate-400 dark:text-gray-500 text-sm mb-6 font-mono">ID: {feedbackId}</p>

                    <div className="flex gap-4 justify-center">
                        <Link
                            href="/dashboard/xai"
                            className="px-6 py-3 bg-gradient-to-r from-brand-500 to-cyan-500 text-white font-semibold rounded-xl hover:shadow-lg hover:shadow-brand-500/25 transition-all duration-200"
                        >
                            ← Back to Q&A
                        </Link>
                        <button
                            onClick={() => setShowHistory(true)}
                            className="px-6 py-3 bg-white/80 dark:bg-gray-800/50 border border-slate-200 dark:border-gray-700 text-slate-600 dark:text-gray-300 font-semibold rounded-xl hover:bg-slate-50 dark:hover:bg-gray-700/50 transition-all duration-200"
                        >
                            View History
                        </button>
                    </div>
                </div>

                {showHistory && <FeedbackHistory history={history} />}
            </div>
        );
    }

    return (
        <div className="max-w-4xl mx-auto space-y-6">
            {/* Header */}
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6">
                <div className="absolute inset-0 bg-gradient-to-r from-amber-500/5 to-orange-500/5 dark:from-amber-500/[0.03] dark:to-orange-500/[0.03]" />
                <div className="relative flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-lg shadow-amber-500/20">
                                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                </svg>
                            </div>
                            Human Expert Review
                        </h1>
                        <p className="text-slate-500 dark:text-gray-400 mt-1.5 text-sm">
                            Provide feedback to improve the Q&A system
                        </p>
                    </div>
                    <Link
                        href="/dashboard/xai"
                        className="px-4 py-2.5 bg-violet-50 dark:bg-violet-500/10 border border-violet-200/60 dark:border-violet-500/20 text-violet-700 dark:text-violet-300 rounded-xl hover:bg-violet-100 dark:hover:bg-violet-500/20 transition-all duration-200 text-sm font-semibold shadow-sm"
                    >
                        ← Back to Q&A
                    </Link>
                </div>

                {/* Workflow Progress */}
                <div className="flex items-center justify-center gap-2 mt-6 flex-wrap">
                    {[
                        { label: "Retrieval", done: true },
                        { label: "Q&A", done: true },
                        { label: "XAI Analysis", done: true },
                        { label: "Expert Review", current: true },
                        { label: "Knowledge Update", pending: true },
                    ].map((step, idx) => (
                        <div key={idx} className="flex items-center gap-2">
                            <span
                                className={`px-3 py-1 rounded-full text-xs font-medium ${step.current
                                    ? "bg-brand-500 text-slate-900 dark:text-white"
                                    : step.done
                                        ? "bg-green-500/20 text-green-400"
                                        : "bg-slate-200 dark:bg-gray-700 text-slate-500 dark:text-gray-500"
                                    }`}
                            >
                                {step.label}
                            </span>
                            {idx < 4 && <span className="text-slate-600 dark:text-gray-600">→</span>}
                        </div>
                    ))}
                </div>
            </div>

            {/* Context Cards */}
            <div className="grid md:grid-cols-2 gap-4">
                <div className="bg-white/60 dark:bg-gray-800/30 border border-l-4 border-l-brand-500 border-slate-200 dark:border-gray-700 rounded-xl p-5">
                    <div className="text-xs font-semibold text-brand-400 uppercase tracking-wide mb-2">
                        Question
                    </div>
                    <p className="text-slate-900 dark:text-white font-medium">{question}</p>
                </div>

                <div className="bg-white/60 dark:bg-gray-800/30 border border-l-4 border-l-green-500 border-slate-200 dark:border-gray-700 rounded-xl p-5">
                    <div className="text-xs font-semibold text-green-400 uppercase tracking-wide mb-2">
                        Model Answer
                    </div>
                    <p className="text-slate-700 dark:text-gray-200 text-sm">{explanation.answer}</p>
                    <span className="inline-block mt-2 px-2 py-0.5 bg-green-500/20 text-green-400 text-xs rounded-full">
                        {(explanation.confidence_score * 100).toFixed(0)}% confidence
                    </span>
                </div>
            </div>

            {/* Feedback Form */}
            <div className="bg-white/60 dark:bg-gray-800/30 border border-slate-200 dark:border-gray-700 rounded-xl p-6 space-y-6">
                {/* Section 1: Answer Correctness */}
                <div>
                    <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4 pb-2 border-b border-slate-200 dark:border-gray-700">
                        1. Is the answer correct?
                    </h3>
                    <div className="grid sm:grid-cols-2 gap-3">
                        {[
                            { value: "correct" as FeedbackType, label: "Correct", desc: "The answer is accurate" },
                            { value: "incorrect" as FeedbackType, label: "Incorrect", desc: "The answer is wrong" },
                            { value: "partially_correct" as FeedbackType, label: "Partially Correct", desc: "Some parts are right" },
                            { value: "needs_more_context" as FeedbackType, label: "Needs More Context", desc: "Answer is incomplete" },
                        ].map((option) => (
                            <button
                                key={option.value}
                                onClick={() => setFeedbackType(option.value)}
                                className={`p-4 rounded-lg border text-left transition-all ${feedbackType === option.value
                                    ? "border-brand-500 bg-brand-500/10"
                                    : "border-slate-200 dark:border-gray-700 hover:border-gray-600"
                                    }`}
                            >
                                <div className="font-medium text-slate-900 dark:text-white">{option.label}</div>
                                <div className="text-slate-500 dark:text-gray-400 text-sm">{option.desc}</div>
                            </button>
                        ))}
                    </div>

                    {(feedbackType === "incorrect" || feedbackType === "partially_correct") && (
                        <div className="mt-4">
                            <label className="block text-sm font-medium text-slate-600 dark:text-gray-300 mb-2">
                                Please provide the correct answer:
                            </label>
                            <textarea
                                value={correctedAnswer}
                                onChange={(e) => setCorrectedAnswer(e.target.value)}
                                placeholder="Enter the correct or improved answer here..."
                                className="w-full bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-4 py-3 text-slate-800 dark:text-gray-100 placeholder-slate-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50"
                                rows={3}
                            />
                        </div>
                    )}
                </div>

                {/* Section 2: XAI Quality Ratings */}
                <div>
                    <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4 pb-2 border-b border-slate-200 dark:border-gray-700">
                        2. Rate the XAI Explanation Quality
                    </h3>
                    <div className="grid md:grid-cols-3 gap-6">
                        <RatingSlider
                            label="Explanation Clarity"
                            value={explanationQuality}
                            onChange={setExplanationQuality}
                            lowLabel="Confusing"
                            highLabel="Very Clear"
                        />
                        <RatingSlider
                            label="Highlight Accuracy"
                            value={highlightAccuracy}
                            onChange={setHighlightAccuracy}
                            lowLabel="Irrelevant"
                            highLabel="Spot On"
                        />
                        <RatingSlider
                            label="Overall Helpfulness"
                            value={xaiHelpfulness}
                            onChange={setXaiHelpfulness}
                            lowLabel="Not Helpful"
                            highLabel="Very Helpful"
                        />
                    </div>
                </div>

                {/* Section 3: Additional Comments */}
                <div>
                    <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4 pb-2 border-b border-slate-200 dark:border-gray-700">
                        3. Additional Comments (Optional)
                    </h3>
                    <textarea
                        value={additionalComments}
                        onChange={(e) => setAdditionalComments(e.target.value)}
                        placeholder="Share any additional thoughts or suggestions..."
                        className="w-full bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-4 py-3 text-slate-800 dark:text-gray-100 placeholder-slate-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 mb-4"
                        rows={3}
                    />

                    <label className="block text-sm font-medium text-slate-600 dark:text-gray-300 mb-2">
                        Suggest Knowledge Update (Optional):
                    </label>
                    <textarea
                        value={knowledgeSuggestion}
                        onChange={(e) => setKnowledgeSuggestion(e.target.value)}
                        placeholder="If there's missing or incorrect information, suggest updates here..."
                        className="w-full bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-4 py-3 text-slate-800 dark:text-gray-100 placeholder-slate-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50"
                        rows={2}
                    />
                </div>
            </div>

            {/* Submit Button */}
            <div className="text-center">
                <button
                    onClick={handleSubmit}
                    disabled={isSubmitting}
                    className="px-8 py-4 bg-gradient-to-r from-brand-500 to-brand-600 text-slate-900 dark:text-white font-semibold rounded-full hover:from-brand-400 hover:to-brand-500 transition-all shadow-lg shadow-brand-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {isSubmitting ? "Submitting..." : "Submit Feedback"}
                </button>
            </div>

            {/* View History Button */}
            {history.length > 0 && (
                <div className="text-center">
                    <button
                        onClick={() => setShowHistory(!showHistory)}
                        className="text-slate-500 dark:text-gray-400 hover:text-slate-700 dark:text-gray-200 text-sm"
                    >
                        {showHistory ? "Hide" : "View"} Feedback History ({history.length})
                    </button>
                </div>
            )}

            {showHistory && <FeedbackHistory history={history} />}
        </div>
    );
}

// ── Sub-components ──

function RatingSlider({
    label,
    value,
    onChange,
    lowLabel,
    highLabel,
}: {
    label: string;
    value: number;
    onChange: (v: number) => void;
    lowLabel: string;
    highLabel: string;
}) {
    return (
        <div className="bg-slate-50 dark:bg-gray-800/50 rounded-lg p-4">
            <div className="font-medium text-slate-900 dark:text-white mb-3">{label}</div>
            <div className="flex gap-2 mb-2">
                {[1, 2, 3, 4, 5].map((n) => (
                    <button
                        key={n}
                        onClick={() => onChange(n)}
                        className={`flex-1 py-2 rounded-lg font-medium transition-all ${value === n
                            ? "bg-brand-500 text-slate-900 dark:text-white"
                            : "bg-slate-200 dark:bg-gray-700 text-slate-500 dark:text-gray-400 hover:bg-slate-200 dark:hover:bg-gray-600"
                            }`}
                    >
                        {n}
                    </button>
                ))}
            </div>
            <div className="flex justify-between text-xs text-slate-500 dark:text-gray-500">
                <span>{lowLabel}</span>
                <span>{highLabel}</span>
            </div>
        </div>
    );
}

function FeedbackHistory({ history }: { history: HITLFeedback[] }) {
    const total = history.length;
    const correct = history.filter((f) => f.is_answer_correct).length;
    const accuracy = total > 0 ? (correct / total) * 100 : 0;

    return (
        <div className="mt-6 bg-white/60 dark:bg-gray-800/30 border border-slate-200 dark:border-gray-700 rounded-xl p-6">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Feedback History</h3>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="bg-slate-50 dark:bg-gray-800/50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-slate-900 dark:text-white">{total}</div>
                    <div className="text-slate-500 dark:text-gray-400 text-sm">Total Feedback</div>
                </div>
                <div className="bg-slate-50 dark:bg-gray-800/50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-green-400">{correct}</div>
                    <div className="text-slate-500 dark:text-gray-400 text-sm">Correct Answers</div>
                </div>
                <div className="bg-slate-50 dark:bg-gray-800/50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-brand-400">{accuracy.toFixed(1)}%</div>
                    <div className="text-slate-500 dark:text-gray-400 text-sm">Accuracy Rate</div>
                </div>
            </div>

            {/* List */}
            <div className="space-y-3 max-h-[400px] overflow-y-auto">
                {[...history].reverse().map((feedback) => (
                    <div
                        key={feedback.feedback_id}
                        className="bg-white/80 dark:bg-gray-800/50 border border-slate-200 dark:border-gray-700 rounded-lg p-4"
                    >
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-xs font-mono text-slate-500 dark:text-gray-500">{feedback.feedback_id}</span>
                            <span
                                className={`px-2 py-0.5 rounded-full text-xs ${feedback.is_answer_correct
                                    ? "bg-green-500/20 text-green-400"
                                    : "bg-red-500/20 text-red-400"
                                    }`}
                            >
                                {feedback.feedback_type}
                            </span>
                        </div>
                        <p className="text-slate-600 dark:text-gray-300 text-sm mb-1">
                            <strong>Q:</strong> {feedback.question}
                        </p>
                        <p className="text-slate-500 dark:text-gray-400 text-sm truncate">
                            <strong>A:</strong> {feedback.original_answer}
                        </p>
                        <div className="mt-2 text-xs text-slate-500 dark:text-gray-500">
                            Ratings: {feedback.ratings.explanation_quality}/5 |{" "}
                            {feedback.ratings.highlight_accuracy}/5 | {feedback.ratings.xai_helpfulness}/5
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useToast } from "@/components/toast";
import { Icon } from "@/components/icons";
import type { XAIExplanation, FeedbackType, HITLFeedback } from "@/types";

const VERDICTS: Array<{ value: FeedbackType; label: string; description: string }> = [
    { value: "correct", label: "Correct", description: "The answer is right" },
    { value: "partially_correct", label: "Partly correct", description: "Some of it is right" },
    { value: "incorrect", label: "Wrong", description: "The answer is wrong" },
    { value: "needs_more_context", label: "Needs more context", description: "The answer is incomplete" },
];

const VERDICT_LABELS: Record<FeedbackType, string> = Object.fromEntries(
    VERDICTS.map((verdict) => [verdict.value, verdict.label]),
) as Record<FeedbackType, string>;

const CARD = "rounded-2xl border border-slate-200 bg-white/70 p-5 dark:border-gray-700 dark:bg-gray-800/40";
const FIELD =
    "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500";

function readStored(key: string): string | null {
    return sessionStorage.getItem(key) ?? localStorage.getItem(key);
}

export default function HITLPage() {
    const { addToast } = useToast();
    const [loaded, setLoaded] = useState(false);
    const [explanation, setExplanation] = useState<XAIExplanation | null>(null);
    const [question, setQuestion] = useState("");
    const [adviceId, setAdviceId] = useState("");
    const [history, setHistory] = useState<HITLFeedback[]>([]);
    const [showHistory, setShowHistory] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [feedbackId, setFeedbackId] = useState("");

    const [feedbackType, setFeedbackType] = useState<FeedbackType | null>(null);
    const [correctedAnswer, setCorrectedAnswer] = useState("");
    const [explanationQuality, setExplanationQuality] = useState(3);
    const [highlightAccuracy, setHighlightAccuracy] = useState(3);
    const [xaiHelpfulness, setXaiHelpfulness] = useState(3);
    const [additionalComments, setAdditionalComments] = useState("");
    const [knowledgeSuggestion, setKnowledgeSuggestion] = useState("");

    useEffect(() => {
        try {
            const raw = readStored("xai_explanation");
            setExplanation(raw ? (JSON.parse(raw) as XAIExplanation) : null);
        } catch {
            setExplanation(null);
        }
        setQuestion(readStored("xai_question") ?? "");
        setAdviceId(readStored("xai_advice_id") ?? "");
        try {
            const storedHistory = localStorage.getItem("hitl_history");
            setHistory(storedHistory ? (JSON.parse(storedHistory) as HITLFeedback[]) : []);
        } catch {
            setHistory([]);
        }
        setLoaded(true);
    }, []);

    const handleSubmit = async () => {
        if (!explanation || !feedbackType) {
            return;
        }
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

            if (adviceId) {
                try {
                    const bridge = await api.forwardIDPOHITLCorrection(adviceId, feedbackType);
                    if (bridge.status !== "forwarded") {
                        addToast({
                            type: "warning",
                            title: "Rating saved, AHMN not updated",
                            message: bridge.error || "The rating was saved, but it could not be passed on to AHMN.",
                        });
                    }
                } catch (bridgeErr) {
                    addToast({
                        type: "warning",
                        title: "Rating saved, AHMN not updated",
                        message: bridgeErr instanceof Error ? bridgeErr.message : "The rating could not be passed on to AHMN.",
                    });
                }
            }

            const entry: HITLFeedback = {
                feedback_id: response.feedback_id,
                timestamp: new Date().toISOString(),
                question,
                original_answer: explanation.answer,
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
            };
            const updated = [...history, entry];
            setHistory(updated);
            localStorage.setItem("hitl_history", JSON.stringify(updated));
            setFeedbackId(response.feedback_id);
            addToast({ type: "success", title: "Rating saved", message: "Thank you. The XAI service has your rating." });
        } catch (err) {
            addToast({
                type: "error",
                title: "Rating not saved",
                message: err instanceof Error ? err.message : "The XAI service did not accept the rating.",
            });
        } finally {
            setIsSubmitting(false);
        }
    };

    if (!loaded) {
        return <div className="max-w-4xl 3xl:max-w-5xl mx-auto h-64 rounded-2xl bg-slate-100 dark:bg-gray-800/50 animate-pulse" />;
    }

    if (!explanation) {
        return (
            <div className="max-w-4xl 3xl:max-w-5xl mx-auto space-y-6">
                <div className={`${CARD} p-8 text-center`}>
                    <span className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-amber-200/60 bg-amber-50 text-amber-600 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300">
                        <Icon name="userCheck" className="h-6 w-6" />
                    </span>
                    <h1 className="text-xl font-bold text-slate-900 dark:text-white">No answer to review yet</h1>
                    <p className="mt-2 mb-6 text-sm text-slate-600 dark:text-gray-300">
                        Ask a question in AI Q&A, then come back here to rate the answer and its explanation.
                    </p>
                    <Link
                        href="/dashboard/xai"
                        className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
                    >
                        Go to AI Q&A
                    </Link>
                </div>
                {history.length > 0 && <FeedbackHistory history={history} />}
            </div>
        );
    }

    if (feedbackId) {
        return (
            <div className="max-w-4xl 3xl:max-w-5xl mx-auto space-y-6">
                <div className={`${CARD} p-8 text-center`}>
                    <span className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-600 text-white">
                        <Icon name="check" className="h-7 w-7" />
                    </span>
                    <h1 className="text-xl font-bold text-slate-900 dark:text-white">Rating saved</h1>
                    <p className="mt-2 text-sm text-slate-600 dark:text-gray-300">Thank you for reviewing this answer.</p>
                    <p className="mt-1 mb-6 font-mono text-xs text-slate-500 dark:text-gray-400">Reference {feedbackId}</p>
                    <div className="flex flex-wrap justify-center gap-3">
                        <Link
                            href="/dashboard/xai"
                            className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
                        >
                            Ask another question
                        </Link>
                        <button
                            type="button"
                            onClick={() => setShowHistory((value) => !value)}
                            aria-expanded={showHistory}
                            className="rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                        >
                            {showHistory ? "Hide your ratings" : "Show your ratings"}
                        </button>
                    </div>
                </div>
                {showHistory && <FeedbackHistory history={history} />}
            </div>
        );
    }

    const needsCorrection = feedbackType === "incorrect" || feedbackType === "partially_correct";

    return (
        <div className="max-w-4xl 3xl:max-w-5xl mx-auto space-y-5">
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6">
                <div className="absolute inset-0 bg-gradient-to-r from-amber-500/5 to-orange-500/5 dark:from-amber-500/[0.03] dark:to-orange-500/[0.03]" />
                <div className="relative flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0">
                        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                            <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-lg shadow-amber-500/20 text-white">
                                <Icon name="userCheck" className="h-5 w-5" />
                            </span>
                            Expert review
                        </h1>
                        <p className="mt-1.5 max-w-2xl text-sm text-slate-600 dark:text-gray-300">
                            Rate the last AI Q&A answer and its explanation. Ratings are sent to the XAI service; the list
                            of your ratings is kept in this browser.
                        </p>
                    </div>
                    <Link
                        href="/dashboard/xai/explanation"
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    >
                        <Icon name="search" className="h-4 w-4" />
                        See the explanation
                    </Link>
                </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
                <div className={CARD}>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-gray-400">Question</p>
                    <p className="mt-2 font-medium text-slate-900 dark:text-white">{question || "—"}</p>
                </div>
                <div className={CARD}>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-gray-400">Answer</p>
                    <p className="mt-2 text-sm text-slate-800 dark:text-gray-100">{explanation.answer || "—"}</p>
                    {explanation.confidence_score >= 0 && (
                        <span className="mt-2 inline-flex rounded-full border border-slate-200 px-2.5 py-0.5 text-xs text-slate-600 dark:border-gray-600 dark:text-gray-300">
                            Confidence {(explanation.confidence_score * 100).toFixed(0)}%
                        </span>
                    )}
                </div>
            </div>

            <form
                className={`${CARD} space-y-6`}
                onSubmit={(event) => {
                    event.preventDefault();
                    void handleSubmit();
                }}
            >
                <fieldset>
                    <legend className="mb-3 text-base font-semibold text-slate-900 dark:text-white">1. Is the answer correct?</legend>
                    <div role="radiogroup" aria-label="Is the answer correct?" className="grid gap-3 sm:grid-cols-2">
                        {VERDICTS.map((option) => {
                            const selected = feedbackType === option.value;
                            return (
                                <button
                                    key={option.value}
                                    type="button"
                                    role="radio"
                                    aria-checked={selected}
                                    onClick={() => setFeedbackType(option.value)}
                                    className={`rounded-lg border p-4 text-left transition-colors ${
                                        selected
                                            ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500 dark:bg-brand-500/10"
                                            : "border-slate-200 hover:border-slate-300 hover:bg-slate-50 dark:border-gray-700 dark:hover:border-gray-600 dark:hover:bg-gray-800"
                                    }`}
                                >
                                    <span className="block font-medium text-slate-900 dark:text-white">{option.label}</span>
                                    <span className="block text-sm text-slate-600 dark:text-gray-400">{option.description}</span>
                                </button>
                            );
                        })}
                    </div>
                    {needsCorrection && (
                        <div className="mt-4">
                            <label htmlFor="hitl-correction" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-gray-200">
                                What should the answer be?
                            </label>
                            <textarea
                                id="hitl-correction"
                                value={correctedAnswer}
                                onChange={(event) => setCorrectedAnswer(event.target.value)}
                                placeholder="The correct or more complete answer"
                                rows={3}
                                className={FIELD}
                            />
                        </div>
                    )}
                </fieldset>

                <fieldset>
                    <legend className="mb-3 text-base font-semibold text-slate-900 dark:text-white">2. How good is the explanation?</legend>
                    <div className="grid gap-4 md:grid-cols-3">
                        <RatingScale label="Clarity" value={explanationQuality} onChange={setExplanationQuality} lowLabel="Confusing" highLabel="Very clear" />
                        <RatingScale
                            label="Highlighted words"
                            value={highlightAccuracy}
                            onChange={setHighlightAccuracy}
                            lowLabel="Irrelevant"
                            highLabel="Spot on"
                        />
                        <RatingScale label="Helpfulness" value={xaiHelpfulness} onChange={setXaiHelpfulness} lowLabel="Not helpful" highLabel="Very helpful" />
                    </div>
                </fieldset>

                <fieldset className="space-y-4">
                    <legend className="mb-3 text-base font-semibold text-slate-900 dark:text-white">3. Anything else? (optional)</legend>
                    <div>
                        <label htmlFor="hitl-comments" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-gray-200">
                            Comments
                        </label>
                        <textarea
                            id="hitl-comments"
                            value={additionalComments}
                            onChange={(event) => setAdditionalComments(event.target.value)}
                            placeholder="Anything that would help judge this answer"
                            rows={3}
                            className={FIELD}
                        />
                    </div>
                    <div>
                        <label htmlFor="hitl-knowledge" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-gray-200">
                            Missing or wrong information
                        </label>
                        <textarea
                            id="hitl-knowledge"
                            value={knowledgeSuggestion}
                            onChange={(event) => setKnowledgeSuggestion(event.target.value)}
                            placeholder="Facts the answer should have used"
                            rows={2}
                            className={FIELD}
                        />
                    </div>
                </fieldset>

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-5 dark:border-gray-700">
                    {history.length > 0 ? (
                        <button
                            type="button"
                            onClick={() => setShowHistory((value) => !value)}
                            aria-expanded={showHistory}
                            className="text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-gray-300 dark:hover:text-white"
                        >
                            {showHistory ? "Hide" : "Show"} your ratings ({history.length})
                        </button>
                    ) : (
                        <span />
                    )}
                    <div className="flex items-center gap-3">
                        {!feedbackType && <span className="text-sm text-slate-500 dark:text-gray-400">Choose whether the answer is correct first.</span>}
                        <button
                            type="submit"
                            disabled={isSubmitting || !feedbackType}
                            className="shrink-0 whitespace-nowrap rounded-lg bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {isSubmitting ? "Saving…" : "Save rating"}
                        </button>
                    </div>
                </div>
            </form>

            {showHistory && <FeedbackHistory history={history} />}
        </div>
    );
}

function RatingScale({
    label,
    value,
    onChange,
    lowLabel,
    highLabel,
}: {
    label: string;
    value: number;
    onChange: (value: number) => void;
    lowLabel: string;
    highLabel: string;
}) {
    return (
        <div className="rounded-lg bg-slate-50 p-4 dark:bg-gray-800/60">
            <p className="mb-3 text-sm font-medium text-slate-900 dark:text-white">{label}</p>
            <div role="radiogroup" aria-label={`${label}, 1 (${lowLabel}) to 5 (${highLabel})`} className="mb-2 flex gap-1.5">
                {[1, 2, 3, 4, 5].map((n) => (
                    <button
                        key={n}
                        type="button"
                        role="radio"
                        aria-checked={value === n}
                        onClick={() => onChange(n)}
                        className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
                            value === n
                                ? "bg-brand-600 text-white"
                                : "bg-white text-slate-600 hover:bg-slate-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
                        }`}
                    >
                        {n}
                    </button>
                ))}
            </div>
            <div className="flex justify-between text-xs text-slate-500 dark:text-gray-400">
                <span>{lowLabel}</span>
                <span>{highLabel}</span>
            </div>
        </div>
    );
}

function FeedbackHistory({ history }: { history: HITLFeedback[] }) {
    const total = history.length;
    const correct = history.filter((entry) => entry.is_answer_correct).length;

    return (
        <section className={CARD}>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Your ratings</h2>
            <p className="mt-1 text-xs text-slate-500 dark:text-gray-400">Kept in this browser.</p>
            <dl className="mt-4 grid grid-cols-3 gap-3">
                <div className="rounded-lg bg-slate-50 p-3 text-center dark:bg-gray-800/60">
                    <dt className="text-xs text-slate-500 dark:text-gray-400">Ratings</dt>
                    <dd className="mt-1 text-xl font-bold tabular-nums text-slate-900 dark:text-white">{total}</dd>
                </div>
                <div className="rounded-lg bg-slate-50 p-3 text-center dark:bg-gray-800/60">
                    <dt className="text-xs text-slate-500 dark:text-gray-400">Answers rated correct</dt>
                    <dd className="mt-1 text-xl font-bold tabular-nums text-slate-900 dark:text-white">{correct}</dd>
                </div>
                <div className="rounded-lg bg-slate-50 p-3 text-center dark:bg-gray-800/60">
                    <dt className="text-xs text-slate-500 dark:text-gray-400">Share rated correct</dt>
                    <dd className="mt-1 text-xl font-bold tabular-nums text-slate-900 dark:text-white">
                        {total > 0 ? `${((correct / total) * 100).toFixed(0)}%` : "—"}
                    </dd>
                </div>
            </dl>
            <ul className="mt-4 max-h-[400px] space-y-3 overflow-y-auto">
                {[...history].reverse().map((entry) => (
                    <li key={entry.feedback_id} className="rounded-lg border border-slate-200 p-4 dark:border-gray-700">
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                            <span className="text-xs text-slate-500 dark:text-gray-400">
                                {new Date(entry.timestamp).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}
                            </span>
                            <span
                                className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
                                    entry.is_answer_correct
                                        ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300"
                                        : "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
                                }`}
                            >
                                {VERDICT_LABELS[entry.feedback_type] ?? entry.feedback_type}
                            </span>
                        </div>
                        <p className="text-sm text-slate-700 dark:text-gray-200">
                            <span className="font-semibold">Q:</span> {entry.question}
                        </p>
                        <p className="truncate text-sm text-slate-600 dark:text-gray-400">
                            <span className="font-semibold">A:</span> {entry.original_answer}
                        </p>
                        <p className="mt-2 text-xs text-slate-500 dark:text-gray-400">
                            Clarity {entry.ratings.explanation_quality}/5 · Highlighted words {entry.ratings.highlight_accuracy}/5 · Helpfulness{" "}
                            {entry.ratings.xai_helpfulness}/5
                        </p>
                    </li>
                ))}
            </ul>
        </section>
    );
}

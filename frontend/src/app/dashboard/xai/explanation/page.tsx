"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Icon } from "@/components/icons";
import type { HighlightSpan, XAIExplanation } from "@/types";

type Tab = "shap" | "lime" | "derivation";
type SpanKind = "answer" | "supports" | "against" | "some";

const TABS: Array<{ id: Tab; label: string }> = [
    { id: "shap", label: "Word importance (SHAP)" },
    { id: "lime", label: "Local explanation (LIME)" },
    { id: "derivation", label: "Reasoning steps" },
];

const SPAN_STYLES: Record<SpanKind, { label: string; className: string }> = {
    answer: {
        label: "The answer",
        className: "bg-amber-200 text-amber-950 dark:bg-amber-400/30 dark:text-amber-50",
    },
    supports: {
        label: "Supports the answer",
        className: "bg-emerald-200 text-emerald-950 dark:bg-emerald-400/25 dark:text-emerald-50",
    },
    against: {
        label: "Works against the answer",
        className: "bg-rose-200 text-rose-950 dark:bg-rose-400/25 dark:text-rose-50",
    },
    some: {
        label: "Some influence, no clear direction",
        className: "bg-sky-200 text-sky-950 dark:bg-sky-400/25 dark:text-sky-50",
    },
};

const CARD = "rounded-2xl border border-slate-200 bg-white/70 p-5 dark:border-gray-700 dark:bg-gray-800/40";

function readStored(key: string): string | null {
    return sessionStorage.getItem(key) ?? localStorage.getItem(key);
}

function hasWordWeights(explanation: XAIExplanation): boolean {
    return (
        (explanation.shap_explanation?.shap_values?.length ?? 0) > 0 ||
        (explanation.lime_explanation?.word_weights?.length ?? 0) > 0
    );
}

function spanKind(span: HighlightSpan): SpanKind {
    if (span.type === "answer") {
        return "answer";
    }
    const average = ((span.shap_score ?? 0) + (span.lime_score ?? 0)) / 2;
    if (average > 0.1) {
        return "supports";
    }
    if (average < -0.1) {
        return "against";
    }
    return "some";
}

function signed(value: number): string {
    const text = Math.abs(value).toFixed(3);
    return value < 0 ? `\u2212${text}` : `+${text}`;
}

function stepTitle(action: string): string {
    return action.replace(/^[^A-Za-z0-9]+/, "").trim() || action;
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

export default function ExplanationPage() {
    const [loaded, setLoaded] = useState(false);
    const [explanation, setExplanation] = useState<XAIExplanation | null>(null);
    const [question, setQuestion] = useState("");
    const [paragraph, setParagraph] = useState("");
    const [activeTab, setActiveTab] = useState<Tab>("shap");
    const [isLoadingWeights, setIsLoadingWeights] = useState(false);
    const [weightsError, setWeightsError] = useState("");

    useEffect(() => {
        const storedQuestion = readStored("xai_question") ?? "";
        const storedParagraph = readStored("xai_paragraph") ?? "";
        let parsed: XAIExplanation | null = null;
        try {
            const raw = readStored("xai_explanation");
            parsed = raw ? (JSON.parse(raw) as XAIExplanation) : null;
        } catch {
            parsed = null;
        }
        setQuestion(storedQuestion);
        setParagraph(storedParagraph);
        setExplanation(parsed);
        setLoaded(true);

        if (!parsed || hasWordWeights(parsed) || !storedQuestion || !storedParagraph || !parsed.answer) {
            return;
        }
        const base = parsed;
        setIsLoadingWeights(true);
        api.fetchXAIExplanation(storedParagraph, storedQuestion, base.answer)
            .then((weights) => {
                const updated = {
                    ...base,
                    shap_explanation: weights.shap_explanation,
                    lime_explanation: weights.lime_explanation,
                    highlighted_spans: base.highlighted_spans?.length ? base.highlighted_spans : (weights.highlighted_spans ?? []),
                };
                setExplanation(updated);
                sessionStorage.setItem("xai_explanation", JSON.stringify(updated));
            })
            .catch((err: unknown) => {
                setWeightsError(err instanceof Error ? err.message : "The XAI service did not respond.");
            })
            .finally(() => setIsLoadingWeights(false));
    }, []);

    if (!loaded) {
        return <div className="max-w-5xl 3xl:max-w-6xl mx-auto h-64 rounded-2xl bg-slate-100 dark:bg-gray-800/50 animate-pulse" />;
    }

    if (!explanation) {
        return (
            <div className="max-w-4xl 3xl:max-w-5xl mx-auto">
                <div className={`${CARD} p-8 text-center`}>
                    <span className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-violet-200/60 bg-violet-50 text-violet-600 dark:border-violet-500/20 dark:bg-violet-500/10 dark:text-violet-300">
                        <Icon name="search" className="h-6 w-6" />
                    </span>
                    <h1 className="text-xl font-bold text-slate-900 dark:text-white">No answer to explain yet</h1>
                    <p className="mt-2 mb-6 text-sm text-slate-600 dark:text-gray-300">
                        Ask a question in AI Q&A first. This page then shows which words the answer relied on.
                    </p>
                    <Link
                        href="/dashboard/xai"
                        className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
                    >
                        Go to AI Q&A
                    </Link>
                </div>
            </div>
        );
    }

    const shapValues = explanation.shap_explanation?.shap_values ?? [];
    const limeWeights = explanation.lime_explanation?.word_weights ?? [];
    const noWeightsMessage = weightsError
        ? `Word weights could not be computed: ${weightsError}`
        : "The service returned no word weights for this answer.";
    const noHighlightsMessage = isLoadingWeights
        ? "Finding the words the answer relied on…"
        : weightsError
          ? "No highlights: the word weights could not be computed."
          : "No word in this text scored high enough to highlight.";

    return (
        <div className="max-w-5xl 3xl:max-w-6xl mx-auto space-y-5">
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6">
                <div className="absolute inset-0 bg-gradient-to-r from-violet-500/5 to-purple-500/5 dark:from-violet-500/[0.03] dark:to-purple-500/[0.03]" />
                <div className="relative flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0">
                        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
                            <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-400 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-500/20 text-white">
                                <Icon name="search" className="h-5 w-5" />
                            </span>
                            How the answer was found
                        </h1>
                        <p className="mt-1.5 max-w-2xl text-sm text-slate-600 dark:text-gray-300">
                            SHAP and LIME estimate which words the model relied on for the last AI Q&A answer. They
                            explain the model&apos;s choice; they do not show that the answer is correct.
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <Link
                            href="/dashboard/xai"
                            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                        >
                            Back to AI Q&A
                        </Link>
                        <Link
                            href="/dashboard/hitl"
                            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
                        >
                            <Icon name="userCheck" className="h-4 w-4" />
                            Rate this answer
                        </Link>
                    </div>
                </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
                <div className={CARD}>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-gray-400">Question</p>
                    <p className="mt-2 text-lg font-medium text-slate-900 dark:text-white">{question || "—"}</p>
                </div>
                <div className={CARD}>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-gray-400">Answer</p>
                    <p className="mt-2 text-slate-800 dark:text-gray-100">{explanation.answer || "—"}</p>
                    {explanation.confidence_score >= 0 && (
                        <span
                            className={`mt-3 inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${confidenceTone(explanation.confidence_score)}`}
                        >
                            Confidence {(explanation.confidence_score * 100).toFixed(0)}%
                        </span>
                    )}
                </div>
            </div>

            <section className={CARD}>
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">The text, with highlights</h2>
                <HighlightedText text={paragraph} spans={explanation.highlighted_spans ?? []} emptyMessage={noHighlightsMessage} />
            </section>

            <section className={`${CARD} p-0 overflow-hidden`}>
                <div role="tablist" aria-label="Explanation views" className="flex overflow-x-auto border-b border-slate-200 dark:border-gray-700">
                    {TABS.map((tab) => (
                        <button
                            key={tab.id}
                            id={`xai-tab-${tab.id}`}
                            type="button"
                            role="tab"
                            aria-selected={activeTab === tab.id}
                            aria-controls={`xai-panel-${tab.id}`}
                            onClick={() => setActiveTab(tab.id)}
                            className={`flex-1 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                                activeTab === tab.id
                                    ? "border-brand-600 bg-brand-50 text-brand-800 dark:border-brand-400 dark:bg-brand-500/10 dark:text-brand-200"
                                    : "border-transparent text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white"
                            }`}
                        >
                            {tab.label}
                        </button>
                    ))}
                </div>

                <div role="tabpanel" id={`xai-panel-${activeTab}`} aria-labelledby={`xai-tab-${activeTab}`} className="p-5">
                    {activeTab === "shap" &&
                        (isLoadingWeights ? (
                            <LoadingWeights />
                        ) : (
                            <WeightBars
                                title="Word importance (SHAP)"
                                description="How much each word pushed the model towards this answer (positive) or away from it (negative)."
                                values={shapValues}
                                emptyMessage={noWeightsMessage}
                            />
                        ))}
                    {activeTab === "lime" &&
                        (isLoadingWeights ? (
                            <LoadingWeights />
                        ) : (
                            <WeightBars
                                title="Local explanation (LIME)"
                                description="Weights from a simple model fitted around this one answer by removing words and watching the answer change."
                                values={limeWeights}
                                emptyMessage={noWeightsMessage}
                                footnote={
                                    limeWeights.length > 0
                                        ? `The simple model gives this answer a probability of ${((explanation.lime_explanation?.prediction_proba ?? 0) * 100).toFixed(1)}%.`
                                        : undefined
                                }
                            />
                        ))}
                    {activeTab === "derivation" && (
                        <ReasoningSteps steps={explanation.derivation_steps ?? []} evidence={explanation.evidence_sentences ?? []} />
                    )}
                </div>
            </section>
        </div>
    );
}

function HighlightedText({ text, spans, emptyMessage }: { text: string; spans: HighlightSpan[]; emptyMessage: string }) {
    if (!text) {
        return <p className="mt-3 text-sm text-slate-500 dark:text-gray-400">The text for this answer was not kept.</p>;
    }

    const valid: Array<HighlightSpan & { kind: SpanKind }> = [];
    let cursor = 0;
    for (const span of [...spans].sort((a, b) => a.start - b.start)) {
        const inRange = span.start >= cursor && span.end > span.start && span.end <= text.length;
        if (inRange && text.slice(span.start, span.end) === span.text) {
            valid.push({ ...span, kind: spanKind(span) });
            cursor = span.end;
        }
    }

    const parts: ReactNode[] = [];
    let position = 0;
    valid.forEach((span, index) => {
        if (span.start > position) {
            parts.push(<span key={`t${index}`}>{text.slice(position, span.start)}</span>);
        }
        parts.push(
            <mark
                key={`m${index}`}
                title={span.kind === "answer" ? "Answer" : `SHAP ${signed(span.shap_score ?? 0)} · LIME ${signed(span.lime_score ?? 0)}`}
                className={`rounded px-0.5 ${SPAN_STYLES[span.kind].className}`}
            >
                {text.slice(span.start, span.end)}
            </mark>,
        );
        position = span.end;
    });
    if (position < text.length) {
        parts.push(<span key="tail">{text.slice(position)}</span>);
    }

    const kinds = (Object.keys(SPAN_STYLES) as SpanKind[]).filter((kind) => valid.some((span) => span.kind === kind));

    return (
        <>
            {kinds.length > 0 ? (
                <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-slate-600 dark:text-gray-300">
                    {kinds.map((kind) => (
                        <li key={kind} className="flex items-center gap-2">
                            <span className={`h-3.5 w-3.5 rounded ${SPAN_STYLES[kind].className}`} aria-hidden="true" />
                            {SPAN_STYLES[kind].label}
                        </li>
                    ))}
                </ul>
            ) : (
                <p className="mt-2 text-xs text-slate-500 dark:text-gray-400">{emptyMessage}</p>
            )}
            <div className="mt-3 max-h-80 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm leading-relaxed text-slate-700 dark:bg-gray-900/60 dark:text-gray-300">
                {parts}
            </div>
        </>
    );
}

function WeightBars({
    title,
    description,
    values,
    emptyMessage,
    footnote,
}: {
    title: string;
    description: string;
    values: Array<[string, number]>;
    emptyMessage: string;
    footnote?: string;
}) {
    if (values.length === 0) {
        return (
            <div className="flex items-start gap-2 text-sm text-slate-600 dark:text-gray-300">
                <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                {emptyMessage}
            </div>
        );
    }
    const top = values.slice(0, 10);
    const largest = Math.max(...top.map(([, value]) => Math.abs(value)), 1e-9);

    return (
        <div>
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">{title}</h3>
            <p className="mt-1 mb-4 text-sm text-slate-600 dark:text-gray-300">{description}</p>
            <ul className="space-y-2.5">
                {top.map(([word, value], index) => (
                    <li key={`${word}-${index}`} className="flex items-center gap-3">
                        <span className="w-28 truncate text-sm font-medium text-slate-700 dark:text-gray-200" title={word}>
                            {word}
                        </span>
                        <span className="relative h-4 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-gray-800">
                            <span
                                className={`absolute inset-y-0 left-0 rounded-full ${value >= 0 ? "bg-emerald-500" : "bg-rose-500"}`}
                                style={{ width: `${(Math.abs(value) / largest) * 100}%` }}
                            />
                        </span>
                        <span
                            className={`w-16 text-right font-mono text-sm tabular-nums ${
                                value >= 0 ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300"
                            }`}
                        >
                            {signed(value)}
                        </span>
                    </li>
                ))}
            </ul>
            {footnote && <p className="mt-4 text-xs text-slate-500 dark:text-gray-400">{footnote}</p>}
        </div>
    );
}

function ReasoningSteps({ steps, evidence }: { steps: XAIExplanation["derivation_steps"]; evidence: string[] }) {
    if (steps.length === 0 && evidence.length === 0) {
        return <p className="text-sm text-slate-600 dark:text-gray-300">The service returned no reasoning steps for this answer.</p>;
    }
    return (
        <div className="space-y-6">
            {steps.length > 0 && (
                <ol className="space-y-3">
                    {steps.map((step) => (
                        <li
                            key={step.step_number}
                            className="rounded-r-lg border-l-4 border-brand-500 bg-slate-50 p-4 dark:bg-gray-800/60"
                        >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <span className="font-semibold text-slate-900 dark:text-white">
                                    {step.step_number}. {stepTitle(step.action)}
                                </span>
                                <span className="rounded-full border border-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:border-gray-600 dark:text-gray-300">
                                    Confidence {(step.confidence * 100).toFixed(0)}%
                                </span>
                            </div>
                            <p className="mt-1 text-sm text-slate-600 dark:text-gray-300">{step.description}</p>
                            {step.details && (
                                <p className="mt-2 rounded bg-white p-2 text-xs text-slate-700 dark:bg-gray-900/60 dark:text-gray-200">{step.details}</p>
                            )}
                        </li>
                    ))}
                </ol>
            )}
            {evidence.length > 0 && (
                <div>
                    <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">Sentences used as evidence</h3>
                    <ul className="space-y-2">
                        {evidence.map((sentence, index) => (
                            <li
                                key={index}
                                className="rounded-r-lg border-l-4 border-amber-400 bg-amber-50 p-3 text-sm text-slate-700 dark:bg-amber-500/10 dark:text-gray-200"
                            >
                                {sentence}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

function LoadingWeights() {
    return (
        <div className="flex flex-col items-center justify-center py-10 text-center" role="status">
            <span className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-brand-500 dark:border-gray-700 dark:border-t-brand-400" />
            <p className="mt-3 text-sm font-medium text-slate-700 dark:text-gray-200">Computing word weights</p>
            <p className="mt-1 text-xs text-slate-500 dark:text-gray-400">This can take up to a minute.</p>
        </div>
    );
}

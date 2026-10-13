"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { SignupLink } from "@/components/signup-link";

const coreFeatures = [
    {
        color: "text-brand-500",
        bgColor: "bg-brand-50 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/20",
        title: "Automatic Schema Proposals",
        desc: "The opt-in product workflow proposes a schema for each document. It uses local heuristics by default and can use a configured chat model for field and value proposals.",
        bullets: [
            "Per-document field proposals",
            "No per-template training required",
            "Optional model-assisted proposals",
            "Unapproved schemas require review",
        ],
    },
    {
        color: "text-violet-500",
        bgColor: "bg-violet-50 dark:bg-violet-500/10 border-violet-200 dark:border-violet-500/20",
        title: "Grounded Validation",
        desc: "Machine-accepted values require an exact source-text quote and a matching typed value. A matching quote confirms source presence, not that the field is semantically correct.",
        bullets: [
            "Exact source-text evidence check",
            "Typed-value validation",
            "Missing values marked for review",
            "Uncertain values remain pending",
        ],
    },
    {
        color: "text-amber-500",
        bgColor: "bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20",
        title: "Human-in-the-Loop Review",
        desc: "Reviewers can correct or remove proposed fields, add missed fields, and save a document-level review. Corrections are recorded but do not automatically configure later extraction.",
        bullets: [
            "Document-level review page",
            "Source text alongside proposals",
            "Revisioned correction history",
            "Corrected structured result",
        ],
    },
    {
        color: "text-emerald-500",
        bgColor: "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20",
        title: "Linked Row Review",
        desc: "A configured model can propose bounded repeated columns linked by row ordinal. Linked rows and cells remain pending human review.",
        bullets: [
            "Repeated-column proposals",
            "Per-cell text evidence",
            "Reviewer row corrections",
            "No automatic row acceptance",
        ],
    },
    {
        color: "text-blue-500",
        bgColor: "bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20",
        title: "Local OCR",
        desc: "Digital PDFs use their native text layer when available. Scanned PDF pages and raster images use local OCR; Tesseract is the current product default.",
        bullets: [
            "Scanned and image-only PDFs",
            "Common raster image formats",
            "Native text layer for digital PDFs",
            "Per-page PDF renderer provenance",
        ],
    },
    {
        color: "text-rose-500",
        bgColor: "bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/20",
        title: "Inspectable Runs",
        desc: "Each product run stores source hashes, OCR pages, proposed fields, model-call telemetry, and review history for inspection.",
        bullets: [
            "Source and result receipts",
            "OCR and model-call provenance",
            "Review audit history",
            "Structured JSON results",
        ],
    },
];

const technicalSpecs = [
    { label: "Inputs", value: "PDF, image, text" },
    { label: "Schema", value: "Per-document proposal" },
    { label: "Model", value: "Optional chat API" },
    { label: "OCR default", value: "Tesseract" },
    { label: "Review", value: "Human approval" },
    { label: "Outputs", value: "JSON and audit trail" },
];

export default function FeaturesPage() {
    return (
        <div className="relative overflow-hidden">
            {/* Hero */}
            <section className="relative py-24 lg:py-32">
                <div className="absolute top-0 right-1/4 w-[600px] h-[600px] bg-violet-500/15 dark:bg-violet-500/5 rounded-full blur-[150px] pointer-events-none" />
                <div className="max-w-7xl mx-auto px-6 lg:px-8 relative text-center">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5 }}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/20 text-violet-700 dark:text-violet-300 text-sm font-medium mb-6"
                    >
                        Platform Capabilities
                    </motion.div>
                    <motion.h1
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: 0.1 }}
                        className="text-4xl lg:text-6xl font-extrabold text-slate-900 dark:text-white tracking-tight leading-[1.1]"
                    >
                        Built for{" "}
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                            reviewable extraction
                        </span>
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: 0.2 }}
                        className="text-lg text-slate-600 dark:text-gray-400 mt-6 max-w-3xl mx-auto leading-relaxed"
                    >
                        These are the current opt-in automatic extraction capabilities. The separate AHMN
                        research runner supports Thompson Sampling policy routing and configurable OCR;
                        automatic extraction does not use that router.
                    </motion.p>
                </div>
            </section>

            {/* Technical Specs Bar */}
            <section className="relative z-10 border-y border-slate-200/60 dark:border-white/10 bg-white/60 dark:bg-gray-900/30 backdrop-blur-md">
                <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8">
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-6">
                        {technicalSpecs.map((spec, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 10 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.05 }}
                                className="flex items-center gap-3"
                            >
                                <div className="w-10 h-10 rounded-lg bg-slate-100 dark:bg-gray-800 border border-slate-200 dark:border-gray-700 flex items-center justify-center text-brand-500 dark:text-brand-400 shrink-0">

                                </div>
                                <div>
                                    <div className="text-xs text-slate-500 dark:text-gray-500 uppercase tracking-wider">{spec.label}</div>
                                    <div className="text-sm font-semibold text-slate-900 dark:text-white">{spec.value}</div>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Feature Details */}
            <section className="relative z-10 py-24 lg:py-32">
                <div className="max-w-7xl mx-auto px-6 lg:px-8">
                    <div className="space-y-16">
                        {coreFeatures.map((feature, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 30 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: 0.1 }}
                                className={`glass-panel rounded-3xl p-8 lg:p-12 flex flex-col ${i % 2 === 0 ? "lg:flex-row" : "lg:flex-row-reverse"
                                    } gap-10 items-center`}
                            >
                                {/* Content */}
                                <div className="flex-1 space-y-5">
                                    <div className={`inline-flex items-center gap-2.5 px-4 py-2 rounded-xl border ${feature.bgColor} ${feature.color}`}>

                                        <span className="font-semibold">{feature.title}</span>
                                    </div>
                                    <p className="text-slate-600 dark:text-gray-400 leading-relaxed text-lg">
                                        {feature.desc}
                                    </p>
                                    <ul className="space-y-3 pt-2">
                                        {feature.bullets.map((bullet, j) => (
                                            <li key={j} className="flex items-center gap-3 text-slate-700 dark:text-gray-300">
                                                <div className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 ${feature.bgColor}`}>
                                                    <div className={`w-1.5 h-1.5 rounded-full ${feature.color.replace("text-", "bg-")}`} />
                                                </div>
                                                {bullet}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                                {/* Visual Placeholder */}
                                <div className="flex-1 w-full">
                                    <div className="aspect-[4/3] rounded-2xl bg-gradient-to-br from-slate-100 to-slate-50 dark:from-gray-800/50 dark:to-gray-900/50 border border-slate-200/60 dark:border-white/5 flex items-center justify-center">
                                        <div className={`${feature.color} opacity-20 dark:opacity-10`}>
                                            {/* Clone icon at large size */}
                                            <div className="w-32 h-32 flex items-center justify-center">

                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className="relative z-10 py-24 border-t border-slate-200/60 dark:border-white/10 bg-white/40 dark:bg-gray-900/20">
                <div className="max-w-4xl mx-auto px-6 lg:px-8 text-center">
                    <h2 className="text-3xl lg:text-4xl font-extrabold text-slate-900 dark:text-white tracking-tight mb-4">
                        Ready to see it in action?
                    </h2>
                    <p className="text-lg text-slate-600 dark:text-gray-400 mb-8">
                        Upload documents, propose a schema, and review each structured result.
                    </p>
                    <div className="flex items-center justify-center gap-4 flex-wrap">
                        <SignupLink className="px-8 py-4 glass-button rounded-xl text-lg flex items-center gap-2">
                            Try Extraction
                        </SignupLink>
                        <Link href="/docs" className="px-8 py-4 bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 text-slate-700 dark:text-gray-300 hover:bg-slate-50 dark:hover:bg-gray-800 rounded-xl text-lg font-medium transition-all shadow-sm">
                            Read the Docs
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}

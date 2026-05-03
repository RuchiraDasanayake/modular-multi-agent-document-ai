"use client";

import Link from "next/link";
import { motion } from "framer-motion";

const coreFeatures = [
    {
        color: "text-brand-500",
        bgColor: "bg-brand-50 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/20",
        title: "Explainable AI",
        desc: "Understand exactly why the AI made each extraction decision. Every output includes confidence scores and clear, readable explanations. Build trust and meet compliance requirements with full transparency.",
        bullets: [
            "Visual explanation of key decisions",
            "Word-level importance highlighting",
            "Confidence scoring with calibration",
            "Audit-ready explanation reports",
        ],
    },
    {
        color: "text-violet-500",
        bgColor: "bg-violet-50 dark:bg-violet-500/10 border-violet-200 dark:border-violet-500/20",
        title: "Intelligent Quality Checks",
        desc: "Multi-layered validation ensures extracted data passes format, meaning, and business rule checks before reaching your systems. Catch errors before they propagate.",
        bullets: [
            "Format and structure validation",
            "Meaning and consistency checks",
            "Cross-field dependency validation",
            "Configurable quality thresholds",
        ],
    },
    {
        color: "text-amber-500",
        bgColor: "bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20",
        title: "Expert Review Workflow",
        desc: "Automatically route uncertain extractions to domain experts. Every human correction feeds back into the AI, creating a cycle of continuous improvement.",
        bullets: [
            "Smart routing based on confidence",
            "Easy annotation and correction tools",
            "Continuous learning from feedback",
            "Quality metrics dashboard",
        ],
    },
    {
        color: "text-emerald-500",
        bgColor: "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20",
        title: "Adaptive Learning Engine",
        desc: "Our AI maintains document context across multiple levels — from words to paragraphs to full documents — and adapts as your documents evolve over time.",
        bullets: [
            "Multi-level document understanding",
            "Smart context awareness",
            "Automatic change detection",
            "Continuous accuracy improvement",
        ],
    },
    {
        color: "text-blue-500",
        bgColor: "bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20",
        title: "Smart Model Selection",
        desc: "The system automatically picks the best extraction approach for each document based on type, complexity, and past performance — no manual configuration needed.",
        bullets: [
            "Automatic strategy selection",
            "Performance-based optimization",
            "Multi-strategy comparison",
            "Per-document-type tuning",
        ],
    },
    {
        color: "text-rose-500",
        bgColor: "bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/20",
        title: "Layout-Aware Processing",
        desc: "Our AI understands document layouts and adjusts its focus in real-time based on where the most important information lives, ensuring maximum precision.",
        bullets: [
            "Layout-aware reading",
            "Adaptive focus regions",
            "Smart section detection",
            "Real-time adjustment",
        ],
    },
];

const technicalSpecs = [
    { label: "Processing", value: "Multiple formats" },
    { label: "Throughput", value: "High throughput" },
    { label: "Accuracy", value: "High accuracy" },
    { label: "Languages", value: "Multi-language" },
    { label: "Security", value: "Enterprise-grade" },
    { label: "Speed", value: "Low latency" },
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
                        Features built for{" "}
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                            enterprise AI
                        </span>
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: 0.2 }}
                        className="text-lg text-slate-600 dark:text-gray-400 mt-6 max-w-3xl mx-auto leading-relaxed"
                    >
                        Every component of Modular Doc AI is designed for transparency, reliability, and continuous improvement.
                        Explore the capabilities that power our document intelligence platform.
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
                        Start with our free tier and experience the full power of Modular Doc AI.
                    </p>
                    <div className="flex items-center justify-center gap-4 flex-wrap">
                        <Link href="/signup" className="px-8 py-4 glass-button rounded-xl text-lg flex items-center gap-2">
                            Get Started Free
                        </Link>
                        <Link href="/pricing" className="px-8 py-4 bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 text-slate-700 dark:text-gray-300 hover:bg-slate-50 dark:hover:bg-gray-800 rounded-xl text-lg font-medium transition-all shadow-sm">
                            View Pricing
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}

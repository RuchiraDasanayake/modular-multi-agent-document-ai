"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { SignupLink } from "@/components/signup-link";

const values = [
    {
        title: "Precision First",
        desc: "We believe every extraction should be accurate, verified, and trustworthy. No guesswork.",
    },
    {
        title: "Transparent AI",
        desc: "AI decisions should be explainable. We make every model output interpretable and auditable.",
    },
    {
        title: "Human-Centered",
        desc: "Technology empowers people, not replaces them. Humans and AI work better together.",
    },
    {
        title: "Open & Modular",
        desc: "Built with a modular architecture so you can use what you need and extend as you grow.",
    },
];

const techStack = [
    { category: "Pipeline", items: ["Python 3.10", "PaddleOCR + Tesseract", "Ollama (local LLM)", "PDFium"] },
    { category: "Intelligence", items: ["Thompson Sampling", "RABI Cold Start", "DAAF Drift Detection", "Grounded Validation"] },
    { category: "Frontend", items: ["Next.js 16", "React 19", "Tailwind CSS", "Framer Motion"] },
    { category: "Services", items: ["FastAPI Gateway", "JWT Auth", "PostgreSQL", "Docker Compose"] },
];

const milestones = [
    { year: "2025 Sep", title: "Research Foundation", desc: "AHMN routing designed around Thompson Sampling, with RABI cold-start and DAAF drift detection evaluated in controlled bandit simulations." },
    { year: "2025 Oct", title: "Pipeline Development", desc: "Policy-driven extraction pipeline built: document analysis, OCR, LLM extraction, validation, and field-level recovery." },
    { year: "2025 Nov", title: "Integration & Testing", desc: "Adaptive routing wired into the pipeline, with human-in-the-loop review and benchmarking on CORD and FUNSD." },
    { year: "2025 Dec", title: "Research Demo", desc: "Web dashboard for uploading jobs, inspecting per-document routing decisions, reviewing fields, and exporting results." },
];

export default function AboutPage() {
    return (
        <div className="relative overflow-hidden">
            {/* Hero */}
            <section className="relative py-24 lg:py-32">
                <div className="absolute top-0 left-1/3 w-[600px] h-[600px] bg-brand-500/15 dark:bg-brand-500/5 rounded-full blur-[150px] pointer-events-none" />
                <div className="max-w-7xl mx-auto px-6 lg:px-8 relative">
                    <div className="max-w-3xl">
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5 }}
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 text-sm font-medium mb-6"
                        >
                            4th Year Research Project
                        </motion.div>
                        <motion.h1
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: 0.1 }}
                            className="text-4xl lg:text-6xl font-extrabold text-slate-900 dark:text-white tracking-tight leading-[1.1] mb-6"
                        >
                            Building the future of{" "}
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                                document intelligence
                            </span>
                        </motion.h1>
                        <motion.p
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: 0.2 }}
                            className="text-lg text-slate-600 dark:text-gray-400 leading-relaxed"
                        >
                            Modular Doc AI is a 4th-year undergraduate research project that explores how multi-agent AI systems
                            can extract, validate, and learn from complex documents without per-template training. It combines
                            adaptive Bayesian policy routing (AHMN), source-grounded validation, and human-in-the-loop feedback
                            so that every extraction decision can be inspected.
                        </motion.p>
                    </div>
                </div>
            </section>

            {/* Mission & Vision */}
            <section className="relative z-10 border-y border-slate-200/60 dark:border-white/10 bg-white/50 dark:bg-gray-900/20 backdrop-blur-sm py-24">
                <div className="max-w-7xl mx-auto px-6 lg:px-8">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
                        <motion.div
                            initial={{ opacity: 0, x: -20 }}
                            whileInView={{ opacity: 1, x: 0 }}
                            viewport={{ once: true }}
                            className="glass-panel rounded-3xl p-10"
                        >
                            <div className="w-14 h-14 rounded-xl bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 flex items-center justify-center mb-6">
                            </div>
                            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-4">Research Objective</h2>
                            <p className="text-slate-600 dark:text-gray-400 leading-relaxed text-lg">
                                To investigate and demonstrate how modular multi-agent architectures combined with
                                adaptive Bayesian learning can improve zero-shot document extraction over a fixed
                                processing policy. The router learns from every document outcome through Thompson
                                Sampling; RABI cold-start and DAAF drift handling are studied in simulation.
                            </p>
                        </motion.div>
                        <motion.div
                            initial={{ opacity: 0, x: 20 }}
                            whileInView={{ opacity: 1, x: 0 }}
                            viewport={{ once: true }}
                            className="glass-panel rounded-3xl p-10"
                        >
                            <div className="w-14 h-14 rounded-xl bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/20 flex items-center justify-center mb-6">
                            </div>
                            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-4">Academic Contribution</h2>
                            <p className="text-slate-600 dark:text-gray-400 leading-relaxed text-lg">
                                This research contributes a novel Adaptive Hierarchical Memory Network (AHMN)
                                that combines short-term, medium-term, and long-term memory tiers with a
                                multi-armed bandit framework, and evaluates adaptive routing against a static
                                single-policy baseline on public receipt and form datasets.
                            </p>
                        </motion.div>
                    </div>
                </div>
            </section>

            {/* Values */}
            <section className="relative z-10 py-24 lg:py-32">
                <div className="max-w-7xl mx-auto px-6 lg:px-8">
                    <div className="text-center mb-16">
                        <motion.h2
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            className="text-3xl lg:text-4xl font-extrabold text-slate-900 dark:text-white tracking-tight"
                        >
                            What drives us
                        </motion.h2>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                        {values.map((value, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.08 }}
                                className="glass-card rounded-2xl p-8 text-center"
                            >
                                <div className="w-14 h-14 rounded-xl bg-slate-50 dark:bg-gray-900 border border-slate-200 dark:border-gray-800 flex items-center justify-center mb-5 mx-auto shadow-sm">

                                </div>
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">{value.title}</h3>
                                <p className="text-sm text-slate-600 dark:text-gray-400 leading-relaxed">{value.desc}</p>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Timeline */}
            <section className="relative z-10 py-24 border-t border-slate-200/60 dark:border-white/10 bg-white/40 dark:bg-gray-900/20">
                <div className="max-w-7xl mx-auto px-6 lg:px-8">
                    <div className="text-center mb-16">
                        <motion.h2
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            className="text-3xl lg:text-4xl font-extrabold text-slate-900 dark:text-white tracking-tight"
                        >
                            Our journey
                        </motion.h2>
                    </div>
                    <div className="relative">
                        {/* Timeline line */}
                        <div className="hidden lg:block absolute left-1/2 top-0 bottom-0 w-px bg-slate-200 dark:bg-gray-800 -translate-x-1/2" />
                        <div className="space-y-12 lg:space-y-0">
                            {milestones.map((ms, i) => (
                                <motion.div
                                    key={i}
                                    initial={{ opacity: 0, y: 20 }}
                                    whileInView={{ opacity: 1, y: 0 }}
                                    viewport={{ once: true }}
                                    transition={{ delay: i * 0.1 }}
                                    className={`relative lg:flex lg:items-center lg:gap-8 lg:py-8 ${i % 2 === 0 ? "lg:flex-row" : "lg:flex-row-reverse"
                                        }`}
                                >
                                    <div className={`flex-1 ${i % 2 === 0 ? "lg:text-right" : "lg:text-left"}`}>
                                        <div className="glass-card rounded-2xl p-6 inline-block text-left">
                                            <div className="text-sm font-bold text-brand-500 dark:text-brand-400 mb-1">{ms.year}</div>
                                            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">{ms.title}</h3>
                                            <p className="text-sm text-slate-600 dark:text-gray-400 leading-relaxed">{ms.desc}</p>
                                        </div>
                                    </div>
                                    {/* Center dot */}
                                    <div className="hidden lg:flex w-4 h-4 rounded-full bg-brand-500 border-4 border-white dark:border-gray-950 shadow-md shrink-0 z-10" />
                                    <div className="flex-1" />
                                </motion.div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {/* Tech Stack */}
            <section className="relative z-10 py-24 border-t border-slate-200/60 dark:border-white/10">
                <div className="max-w-7xl mx-auto px-6 lg:px-8">
                    <div className="text-center mb-16">
                        <motion.h2
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            className="text-3xl lg:text-4xl font-extrabold text-slate-900 dark:text-white tracking-tight"
                        >
                            Technology stack
                        </motion.h2>
                        <motion.p
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: 0.1 }}
                            className="text-lg text-slate-600 dark:text-gray-400 mt-4"
                        >
                            Open-source components, running locally on a single host.
                        </motion.p>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                        {techStack.map((stack, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.08 }}
                                className="glass-card rounded-2xl p-6"
                            >
                                <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4 uppercase tracking-wider">
                                    {stack.category}
                                </h3>
                                <div className="space-y-2">
                                    {stack.items.map((item, j) => (
                                        <div
                                            key={j}
                                            className="flex items-center gap-2 text-sm text-slate-600 dark:text-gray-400"
                                        >
                                            <div className="w-1.5 h-1.5 rounded-full bg-brand-500" />
                                            {item}
                                        </div>
                                    ))}
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
                        Explore the research
                    </h2>
                    <p className="text-lg text-slate-600 dark:text-gray-400 mb-8">
                        Interested in the system architecture, algorithms, or contributing to the project? We welcome collaboration.
                    </p>
                    <div className="flex items-center justify-center gap-4 flex-wrap">
                        <SignupLink className="px-8 py-4 glass-button rounded-xl text-lg flex items-center gap-2">
                            Try the Demo
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

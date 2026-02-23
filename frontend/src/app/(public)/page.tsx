"use client";

import Link from "next/link";
import { motion, useMotionValue, useTransform, useSpring } from "framer-motion";
import { useEffect, useState } from "react";
import {
    FileText,
    ScanLine,
    Sparkles,
    ArrowRight,
    Shield,
    Brain,
    Zap,
    BarChart3,
    Globe,
    Lock,
    CheckCircle2,
    ChevronRight,
} from "lucide-react";

const stats = [
    { value: "99.2%", label: "Extraction Accuracy" },
    { value: "<500ms", label: "Avg. Latency" },
    { value: "50+", label: "Document Types" },
    { value: "10M+", label: "Documents Processed" },
];

const features = [
    {
        icon: <Brain className="w-7 h-7 text-brand-500" />,
        title: "Transparent Results",
        desc: "Every extraction comes with confidence scores and clear explanations so you always know why the AI made its decisions.",
    },
    {
        icon: <Shield className="w-7 h-7 text-violet-500" />,
        title: "Built-in Quality Checks",
        desc: "Automatic validation ensures extracted data is accurate and complete before it reaches your workflow.",
    },
    {
        icon: <Zap className="w-7 h-7 text-amber-500" />,
        title: "Expert Review When Needed",
        desc: "Uncertain results are automatically flagged for human review, so nothing slips through the cracks.",
    },
    {
        icon: <BarChart3 className="w-7 h-7 text-emerald-500" />,
        title: "Self-Improving AI",
        desc: "Our system learns and improves with every document you process, getting smarter over time.",
    },
    {
        icon: <Globe className="w-7 h-7 text-blue-500" />,
        title: "Multi-Format Support",
        desc: "Process PDFs, scanned images, invoices, contracts, medical records, and more — all in one place.",
    },
    {
        icon: <Lock className="w-7 h-7 text-rose-500" />,
        title: "Enterprise Security",
        desc: "Bank-grade security with role-based access, audit trails, and end-to-end encryption.",
    },
];

const steps = [
    {
        step: "01",
        title: "Upload Documents",
        desc: "Drag-and-drop your files. We support PDFs, images, Word docs, and 50+ other formats.",
    },
    {
        step: "02",
        title: "AI Extraction",
        desc: "Our AI reads and understands your documents, pulling out key data like names, dates, amounts, and more.",
    },
    {
        step: "03",
        title: "Validation & Review",
        desc: "Results are automatically checked for accuracy. Uncertain items are flagged for expert review.",
    },
    {
        step: "04",
        title: "Export & Integrate",
        desc: "Download your clean, structured data or connect directly to your existing tools and workflows.",
    },
];

export default function HomePage() {
    const [mounted, setMounted] = useState(false);

    const x = useMotionValue(0);
    const y = useMotionValue(0);
    const mouseXSpring = useSpring(x, { stiffness: 300, damping: 15 });
    const mouseYSpring = useSpring(y, { stiffness: 300, damping: 15 });
    const rotateX = useTransform(mouseYSpring, [-0.5, 0.5], ["15deg", "-15deg"]);
    const rotateY = useTransform(mouseXSpring, [-0.5, 0.5], ["-15deg", "15deg"]);

    useEffect(() => {
        setMounted(true);
        const handleMouseMove = (e: MouseEvent) => {
            const width = document.body.clientWidth;
            const height = document.body.clientHeight;
            x.set(e.clientX / width - 0.5);
            y.set(e.clientY / height - 0.5);
        };
        window.addEventListener("mousemove", handleMouseMove);
        return () => window.removeEventListener("mousemove", handleMouseMove);
    }, [x, y]);

    if (!mounted) return null;

    return (
        <div className="relative overflow-hidden">
            {/* ── Hero Section ── */}
            <section className="relative min-h-[90vh] flex items-center">
                {/* Background ambient glow */}
                <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-brand-500/20 dark:bg-brand-500/10 rounded-full blur-[150px] pointer-events-none" />
                <div className="absolute bottom-0 right-1/4 w-[600px] h-[600px] bg-violet-500/20 dark:bg-violet-500/10 rounded-full blur-[150px] pointer-events-none" />

                <div className="relative z-10 max-w-7xl mx-auto px-6 lg:px-8 py-20 flex flex-col lg:flex-row items-center justify-between gap-16 w-full">
                    {/* Left Content */}
                    <div className="flex-1 space-y-8 text-center lg:text-left">
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5 }}
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/20 text-brand-700 dark:text-brand-300 text-sm font-medium"
                        >
                            <Sparkles className="w-4 h-4" />
                            Next-Gen Document Extraction
                        </motion.div>

                        <motion.h1
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: 0.1 }}
                            className="text-5xl lg:text-7xl font-extrabold text-slate-900 dark:text-white tracking-tight leading-[1.1]"
                        >
                            Understand your <br />
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                                documents with AI
                            </span>
                        </motion.h1>

                        <motion.p
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: 0.2 }}
                            className="text-lg text-slate-600 dark:text-gray-400 max-w-2xl mx-auto lg:mx-0 leading-relaxed"
                        >
                            Intelligent document processing powered by AI you can trust.
                            Extract, analyze, and validate complex documents with unmatched accuracy.
                        </motion.p>

                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: 0.3 }}
                            className="flex items-center justify-center lg:justify-start gap-4 pt-4"
                        >
                            <Link
                                href="/signup"
                                className="px-8 py-4 glass-button rounded-xl text-lg flex items-center gap-2"
                            >
                                Start Extracting <ArrowRight className="w-5 h-5" />
                            </Link>
                            <Link
                                href="/features"
                                className="px-8 py-4 bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 text-slate-700 dark:text-gray-300 hover:bg-slate-50 dark:hover:bg-gray-800 rounded-xl text-lg font-medium transition-all shadow-sm"
                            >
                                Learn More
                            </Link>
                        </motion.div>
                    </div>

                    {/* Right 3D Interactive Element */}
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 0.6, delay: 0.2 }}
                        className="flex-1 flex justify-center perspective-1000"
                    >
                        <motion.div
                            style={{ rotateX, rotateY, transformStyle: "preserve-3d" }}
                            className="relative w-full max-w-md aspect-[4/5] rounded-3xl border border-white/40 dark:border-white/10 bg-white/60 dark:bg-gray-900/40 backdrop-blur-xl shadow-2xl shadow-slate-200/50 dark:shadow-2xl flex flex-col items-center justify-center p-8"
                        >
                            <motion.div
                                style={{ transform: "translateZ(60px)" }}
                                className="relative w-40 h-52 bg-white dark:bg-gray-900/80 border border-brand-500/20 dark:border-brand-500/30 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-2xl flex items-center justify-center overflow-hidden"
                            >
                                <FileText className="w-20 h-20 text-brand-500 dark:text-brand-400/80" strokeWidth={1.5} />
                                <motion.div
                                    animate={{ top: ["-10%", "110%"] }}
                                    transition={{ duration: 2.5, repeat: Infinity, ease: "linear" }}
                                    className="absolute left-0 right-0 h-0.5 bg-brand-400 shadow-[0_0_15px_3px_rgba(56,189,248,0.6)] dark:shadow-[0_0_15px_3px_rgba(56,189,248,0.8)] z-10"
                                />
                                <motion.div
                                    animate={{ top: ["-10%", "110%"] }}
                                    transition={{ duration: 2.5, repeat: Infinity, ease: "linear" }}
                                    className="absolute left-0 right-0 h-24 bg-gradient-to-b from-transparent to-brand-500/10 dark:to-brand-500/20 -translate-y-full"
                                />
                            </motion.div>

                            <motion.div style={{ transform: "translateZ(40px)" }} className="mt-10 text-center w-full">
                                <div className="h-2 w-3/4 bg-slate-200 dark:bg-gray-800 rounded-full mx-auto mb-3 overflow-hidden">
                                    <motion.div
                                        animate={{ width: ["0%", "100%"] }}
                                        transition={{ duration: 2.5, repeat: Infinity, ease: "linear" }}
                                        className="h-full bg-brand-500 rounded-full"
                                    />
                                </div>
                                <h2 className="text-xl font-bold text-slate-900 dark:text-white tracking-wide flex items-center justify-center gap-2">
                                    <ScanLine className="w-5 h-5 text-brand-500 dark:text-brand-400" />
                                    Processing Document
                                </h2>
                                <p className="text-sm text-slate-500 dark:text-gray-400 mt-2">
                                    Extracting key data...
                                </p>
                            </motion.div>
                        </motion.div>
                    </motion.div>
                </div>
            </section>

            {/* ── Stats Bar ── */}
            <section className="relative z-10 border-y border-slate-200/60 dark:border-white/10 bg-white/60 dark:bg-gray-900/30 backdrop-blur-md">
                <div className="max-w-7xl mx-auto px-6 lg:px-8 py-12">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
                        {stats.map((stat, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.1 }}
                                className="text-center"
                            >
                                <div className="text-3xl lg:text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                                    {stat.value}
                                </div>
                                <div className="text-sm text-slate-600 dark:text-gray-400 mt-1 font-medium">
                                    {stat.label}
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── Features Grid ── */}
            <section className="relative z-10 py-24 lg:py-32">
                <div className="absolute top-1/2 left-0 w-[500px] h-[500px] bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-[150px] pointer-events-none -translate-y-1/2" />
                <div className="max-w-7xl mx-auto px-6 lg:px-8 relative">
                    <div className="text-center mb-16">
                        <motion.h2
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            className="text-3xl lg:text-5xl font-extrabold text-slate-900 dark:text-white tracking-tight"
                        >
                            Everything you need for{" "}
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                                intelligent extraction
                            </span>
                        </motion.h2>
                        <motion.p
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: 0.1 }}
                            className="text-lg text-slate-600 dark:text-gray-400 mt-4 max-w-2xl mx-auto"
                        >
                            A powerful, enterprise-ready platform that combines smart AI with human expertise.
                        </motion.p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {features.map((feature, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.08 }}
                                className="glass-card rounded-2xl p-8"
                            >
                                <div className="w-14 h-14 rounded-xl bg-slate-50 dark:bg-gray-900 border border-slate-200 dark:border-gray-800 flex items-center justify-center mb-6 shadow-sm">
                                    {feature.icon}
                                </div>
                                <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">{feature.title}</h3>
                                <p className="text-slate-600 dark:text-gray-400 leading-relaxed">{feature.desc}</p>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── How It Works ── */}
            <section className="relative z-10 py-24 lg:py-32 border-t border-slate-200/60 dark:border-white/10 bg-white/40 dark:bg-gray-900/20 backdrop-blur-sm">
                <div className="max-w-7xl mx-auto px-6 lg:px-8">
                    <div className="text-center mb-16">
                        <motion.h2
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            className="text-3xl lg:text-5xl font-extrabold text-slate-900 dark:text-white tracking-tight"
                        >
                            How it works
                        </motion.h2>
                        <motion.p
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: 0.1 }}
                            className="text-lg text-slate-600 dark:text-gray-400 mt-4 max-w-2xl mx-auto"
                        >
                            From upload to structured output in four simple steps.
                        </motion.p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
                        {steps.map((step, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.1 }}
                                className="relative"
                            >
                                <div className="text-6xl font-black text-brand-500/10 dark:text-brand-500/5 mb-4">
                                    {step.step}
                                </div>
                                <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-2">{step.title}</h3>
                                <p className="text-slate-600 dark:text-gray-400 leading-relaxed">{step.desc}</p>
                                {i < steps.length - 1 && (
                                    <ChevronRight className="hidden lg:block absolute top-8 -right-4 w-6 h-6 text-slate-300 dark:text-gray-700" />
                                )}
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── CTA Section ── */}
            <section className="relative z-10 py-24 lg:py-32">
                <div className="absolute inset-0 bg-gradient-to-b from-transparent via-brand-500/5 to-transparent dark:via-brand-500/5 pointer-events-none" />
                <div className="max-w-4xl mx-auto px-6 lg:px-8 text-center relative">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        className="glass-panel rounded-3xl p-12 lg:p-16"
                    >
                        <h2 className="text-3xl lg:text-5xl font-extrabold text-slate-900 dark:text-white tracking-tight mb-6">
                            Ready to transform your{" "}
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                                document workflow?
                            </span>
                        </h2>
                        <p className="text-lg text-slate-600 dark:text-gray-400 mb-8 max-w-2xl mx-auto">
                            Join thousands of teams using Modular Doc AI to extract, validate, and understand their documents
                            with unprecedented accuracy.
                        </p>
                        <div className="flex items-center justify-center gap-4 flex-wrap">
                            <Link
                                href="/signup"
                                className="px-8 py-4 glass-button rounded-xl text-lg flex items-center gap-2"
                            >
                                Get Started Free <ArrowRight className="w-5 h-5" />
                            </Link>
                            <Link
                                href="/contact"
                                className="px-8 py-4 bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 text-slate-700 dark:text-gray-300 hover:bg-slate-50 dark:hover:bg-gray-800 rounded-xl text-lg font-medium transition-all shadow-sm"
                            >
                                Talk to Sales
                            </Link>
                        </div>
                        <div className="mt-8 flex items-center justify-center gap-6 text-sm text-slate-500 dark:text-gray-500">
                            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> Free tier available</span>
                            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> No credit card required</span>
                            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-emerald-500" /> Setup in 5 minutes</span>
                        </div>
                    </motion.div>
                </div>
            </section>
        </div>
    );
}

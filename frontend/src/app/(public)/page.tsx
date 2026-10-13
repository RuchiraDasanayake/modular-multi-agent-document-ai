"use client";

import Link from "next/link";
import { motion, useMotionValue, useTransform, useSpring } from "framer-motion";
import { useEffect, useState } from "react";
import { SignupLink } from "@/components/signup-link";

const stats = [
    { value: "Zero-shot", label: "No per-template training" },
    { value: "Per document", label: "Schema proposals" },
    { value: "Local", label: "OCR and evidence checks" },
    { value: "Human", label: "Field review" },
];

const features = [
    {
        title: "Confirm Your Schema",
        desc: "Describe what you need, ask AI to suggest fields from sample files, and confirm what each field means before extraction.",
    },
    {
        title: "Source Evidence",
        desc: "Inspect the text supporting each proposed value alongside the original document. Text matches still need a check for the right meaning.",
    },
    {
        title: "Human-in-the-Loop Review",
        desc: "Reviewers can correct, remove, or add fields. Their decisions are recorded with the run for later inspection.",
    },
    {
        title: "Linked Row Review",
        desc: "A configured model can propose repeated columns with row links; proposed rows stay pending human review.",
    },
    {
        title: "Scans, Photos, and PDFs",
        desc: "Read supported digital files and scanned pages, with local text extraction and the original available for review.",
    },
    {
        title: "Inspectable Runs",
        desc: "Run artifacts retain source hashes, OCR pages, proposals, and review history so operators can inspect each result.",
    },
];

const steps = [
    {
        step: "01",
        title: "Upload Documents",
        desc: "Create a job and upload supported PDFs, images, text, or Office files.",
    },
    {
        step: "02",
        title: "Define Fields",
        desc: "Enter the information you need, choose representative samples, and confirm field names and meanings.",
    },
    {
        step: "03",
        title: "Preview & Extract",
        desc: "Review the sample results first, then process the remaining files with the same confirmed schema.",
    },
    {
        step: "04",
        title: "Review & Export",
        desc: "Check values against their sources, save corrections, and download the reviewed structured JSON.",
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

                <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-20 flex flex-col lg:flex-row items-center justify-between gap-10 lg:gap-16 w-full">
                    {/* Left Content */}
                    <div className="flex-1 space-y-8 text-center lg:text-left">
                        <motion.h1
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: 0.1 }}
                            className="text-4xl sm:text-5xl lg:text-7xl font-extrabold text-slate-900 dark:text-white tracking-tight leading-[1.1]"
                        >
                            Understand your{" "}
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                                documents
                            </span>
                            <br />with structured extraction
                        </motion.h1>

                        <motion.p
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: 0.2 }}
                            className="text-lg text-slate-600 dark:text-gray-400 max-w-2xl mx-auto lg:mx-0 leading-relaxed"
                        >
                            Upload documents, get proposed fields and values, check their source evidence, and review the structured result. A configured model can assist with schema discovery.
                        </motion.p>

                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: 0.3 }}
                            className="flex flex-col sm:flex-row items-center justify-center lg:justify-start gap-3 sm:gap-4 pt-4"
                        >
                            <SignupLink className="w-full sm:w-auto px-8 py-4 glass-button rounded-xl text-lg flex items-center justify-center gap-2">
                                Start Extracting
                            </SignupLink>
                            <Link
                                href="/features"
                                className="w-full sm:w-auto px-8 py-4 bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 text-slate-700 dark:text-gray-300 hover:bg-slate-50 dark:hover:bg-gray-800 rounded-xl text-lg font-medium transition-all shadow-sm text-center"
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
                        className="hidden sm:flex flex-1 justify-center perspective-1000"
                    >
                        <motion.div
                            style={{ rotateX, rotateY, transformStyle: "preserve-3d" }}
                            className="relative w-full max-w-md aspect-[4/5] rounded-3xl border border-white/40 dark:border-white/10 bg-white/60 dark:bg-gray-900/40 backdrop-blur-xl shadow-2xl shadow-slate-200/50 dark:shadow-2xl flex flex-col items-center justify-center p-8"
                        >
                            <motion.div
                                style={{ transform: "translateZ(60px)" }}
                                className="relative w-40 h-52 bg-white dark:bg-gray-900/80 border border-brand-500/20 dark:border-brand-500/30 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-2xl flex items-center justify-center overflow-hidden"
                            >
                                <span className="text-4xl font-bold text-brand-500 dark:text-brand-400/80">AI</span>
                            </motion.div>

                            <motion.div style={{ transform: "translateZ(40px)" }} className="mt-10 text-center w-full">
                                <div className="h-2 w-3/4 bg-slate-200 dark:bg-gray-800 rounded-full mx-auto mb-3 overflow-hidden">
                                </div>
                                <h2 className="text-xl font-bold text-slate-900 dark:text-white tracking-wide flex items-center justify-center gap-2">
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
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12">
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
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative">
                    <div className="text-center mb-16">
                        <motion.h2
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            className="text-3xl lg:text-5xl font-extrabold text-slate-900 dark:text-white tracking-tight"
                        >
                            Tools for{" "}
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                                structured extraction
                            </span>
                        </motion.h2>
                        <motion.p
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: 0.1 }}
                            className="text-lg text-slate-600 dark:text-gray-400 mt-4 max-w-2xl mx-auto"
                        >
                            The automatic extraction workflow is separate from the AHMN research policy router.
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
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
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
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── CTA Section ── */}
            <section className="relative z-10 py-24 lg:py-32">
                <div className="absolute inset-0 bg-gradient-to-b from-transparent via-brand-500/5 to-transparent dark:via-brand-500/5 pointer-events-none" />
                <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center relative">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        className="glass-panel rounded-3xl p-12 lg:p-16"
                    >
                        <h2 className="text-3xl lg:text-5xl font-extrabold text-slate-900 dark:text-white tracking-tight mb-6">
                            Experience intelligent{" "}
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                                document extraction
                            </span>
                        </h2>
                        <p className="text-lg text-slate-600 dark:text-gray-400 mb-8 max-w-2xl mx-auto">
                            Try automatic schema extraction and inspect proposed fields, source evidence,
                            and review status for each document.
                        </p>
                        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 flex-wrap">
                            <SignupLink className="w-full sm:w-auto px-8 py-4 glass-button rounded-xl text-lg flex items-center justify-center gap-2">
                                Try Extraction
                            </SignupLink>
                            <Link
                                href="/docs"
                                className="w-full sm:w-auto px-8 py-4 bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 text-slate-700 dark:text-gray-300 hover:bg-slate-50 dark:hover:bg-gray-800 rounded-xl text-lg font-medium transition-all shadow-sm text-center"
                            >
                                Read the Docs
                            </Link>
                        </div>
                    </motion.div>
                </div>
            </section>
        </div>
    );
}

"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useState } from "react";
import {
    BookOpen,
    Code2,
    Terminal,
    Layers,
    ArrowRight,
    Copy,
    Check,
    FileJson,
    Cpu,
    Shield,
    Zap,
    GitBranch,
} from "lucide-react";

const sections = [
    { id: "quickstart", label: "Getting Started", icon: <Zap className="w-4 h-4" /> },
    { id: "api", label: "Integration", icon: <Code2 className="w-4 h-4" /> },
    { id: "architecture", label: "How It Works", icon: <Layers className="w-4 h-4" /> },
    { id: "modules", label: "Capabilities", icon: <Cpu className="w-4 h-4" /> },
];

const apiEndpoints = [
    {
        method: "POST",
        path: "/api/v1/extract",
        desc: "Submit a document for extraction",
        color: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10",
    },
    {
        method: "GET",
        path: "/api/v1/results/{id}",
        desc: "Retrieve extraction results",
        color: "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10",
    },
    {
        method: "GET",
        path: "/api/v1/explain/{id}",
        desc: "Get AI explanation for an extraction",
        color: "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10",
    },
    {
        method: "POST",
        path: "/api/v1/validate",
        desc: "Validate extracted data against quality rules",
        color: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10",
    },
    {
        method: "POST",
        path: "/api/v1/review",
        desc: "Submit an expert review decision",
        color: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10",
    },
    {
        method: "GET",
        path: "/api/v1/health",
        desc: "Health check endpoint",
        color: "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10",
    },
];

const modules = [
    {
        icon: <Cpu className="w-6 h-6 text-brand-500" />,
        name: "Extraction Engine",
        desc: "Intelligent document processing with multi-level understanding and adaptive learning that improves over time.",
    },
    {
        icon: <GitBranch className="w-6 h-6 text-violet-500" />,
        name: "Transparency & Review",
        desc: "AI explanations and expert review workflows for transparent, auditable document processing.",
    },
    {
        icon: <Shield className="w-6 h-6 text-amber-500" />,
        name: "Quality Assurance",
        desc: "Multi-layered validation with format checking, consistency verification, and configurable business rules.",
    },
    {
        icon: <Layers className="w-6 h-6 text-emerald-500" />,
        name: "Secure Gateway",
        desc: "Unified entry point with authentication, rate limiting, and intelligent request routing.",
    },
];

function CodeBlock({ code, language }: { code: string; language: string }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
        navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="relative rounded-xl overflow-hidden bg-slate-950 dark:bg-gray-900/80 border border-slate-800 dark:border-gray-800">
            <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900/50 dark:bg-gray-900/50 border-b border-slate-800 dark:border-gray-800">
                <span className="text-xs text-slate-400 font-mono">{language}</span>
                <button
                    onClick={handleCopy}
                    className="text-xs text-slate-400 hover:text-white flex items-center gap-1.5 transition-colors"
                >
                    {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    {copied ? "Copied!" : "Copy"}
                </button>
            </div>
            <pre className="p-4 overflow-x-auto text-sm leading-relaxed">
                <code className="text-slate-300 font-mono">{code}</code>
            </pre>
        </div>
    );
}

export default function DocsPage() {
    const [activeSection, setActiveSection] = useState("quickstart");

    return (
        <div className="relative overflow-hidden">
            {/* Hero */}
            <section className="relative py-24 lg:py-28">
                <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-blue-500/15 dark:bg-blue-500/5 rounded-full blur-[150px] pointer-events-none" />
                <div className="max-w-7xl mx-auto px-6 lg:px-8 relative text-center">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5 }}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 text-blue-700 dark:text-blue-300 text-sm font-medium mb-6"
                    >
                        <BookOpen className="w-4 h-4" />
                        Documentation
                    </motion.div>
                    <motion.h1
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: 0.1 }}
                        className="text-4xl lg:text-6xl font-extrabold text-slate-900 dark:text-white tracking-tight leading-[1.1]"
                    >
                        Developer{" "}
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-blue-500">
                            guide
                        </span>
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: 0.2 }}
                        className="text-lg text-slate-600 dark:text-gray-400 mt-6 max-w-2xl mx-auto"
                    >
                        Everything you need to integrate Modular Doc AI into your workflow.
                    </motion.p>
                </div>
            </section>

            {/* Doc Nav */}
            <section className="sticky top-16 lg:top-20 z-30 border-y border-slate-200/60 dark:border-white/10 bg-white/80 dark:bg-gray-950/80 backdrop-blur-xl">
                <div className="max-w-7xl mx-auto px-6 lg:px-8">
                    <div className="flex items-center gap-1 overflow-x-auto py-3 scrollbar-none">
                        {sections.map((s) => (
                            <button
                                key={s.id}
                                onClick={() => {
                                    setActiveSection(s.id);
                                    document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth" });
                                }}
                                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all ${activeSection === s.id
                                    ? "text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-500/10"
                                    : "text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/5"
                                    }`}
                            >
                                {s.icon}
                                {s.label}
                            </button>
                        ))}
                    </div>
                </div>
            </section>

            {/* Content */}
            <div className="max-w-7xl mx-auto px-6 lg:px-8 py-16 space-y-24">
                {/* Quick Start */}
                <section id="quickstart" className="scroll-mt-40">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                    >
                        <h2 className="text-3xl font-extrabold text-slate-900 dark:text-white mb-4 flex items-center gap-3">
                            <Terminal className="w-8 h-8 text-brand-500" />
                            Getting Started
                        </h2>
                        <p className="text-slate-600 dark:text-gray-400 mb-8 text-lg leading-relaxed max-w-3xl">
                            Get up and running in minutes. Create your account, configure your document types,
                            and submit your first document for extraction.
                        </p>

                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">1. Create your account</h3>
                                <CodeBlock
                                    language="text"
                                    code={`Sign up at modular-doc-ai.com/signup
You'll receive an API key in your dashboard.`}
                                />
                            </div>
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">2. Configure document types</h3>
                                <CodeBlock
                                    language="text"
                                    code={`In the dashboard, go to Settings → Document Types
Choose from built-in types (invoice, receipt, contract...)
or create custom document schemas.`}
                                />
                            </div>
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">3. Submit a document</h3>
                                <CodeBlock
                                    language="bash"
                                    code={`curl -X POST https://api.modular-doc-ai.com/v1/extract \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -F "file=@invoice.pdf" \\
  -F "doc_type=invoice"`}
                                />
                            </div>
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">4. Get results with explanations</h3>
                                <CodeBlock
                                    language="json"
                                    code={`{
  "id": "ext_abc123",
  "status": "completed",
  "fields": {
    "vendor_name": { "value": "Acme Corp", "confidence": 0.97 },
    "total_amount": { "value": "$1,234.56", "confidence": 0.94 },
    "invoice_date": { "value": "2024-01-15", "confidence": 0.99 }
  },
  "explanation": {
    "summary": "High confidence extraction based on document layout analysis..."
  }
}`}
                                />
                            </div>
                        </div>
                    </motion.div>
                </section>

                {/* API Reference */}
                <section id="api" className="scroll-mt-40">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                    >
                        <h2 className="text-3xl font-extrabold text-slate-900 dark:text-white mb-4 flex items-center gap-3">
                            <FileJson className="w-8 h-8 text-blue-500" />
                            Integration Guide
                        </h2>
                        <p className="text-slate-600 dark:text-gray-400 mb-8 text-lg leading-relaxed max-w-3xl">
                            RESTful API with JSON request and response bodies. All endpoints require API key authentication.
                        </p>

                        <div className="space-y-4">
                            {apiEndpoints.map((ep, i) => (
                                <motion.div
                                    key={i}
                                    initial={{ opacity: 0, y: 10 }}
                                    whileInView={{ opacity: 1, y: 0 }}
                                    viewport={{ once: true }}
                                    transition={{ delay: i * 0.05 }}
                                    className="glass-card rounded-xl p-5 hover:translate-y-0 flex items-center gap-4"
                                >
                                    <span className={`text-xs font-bold px-3 py-1.5 rounded-lg ${ep.color} font-mono tracking-wider`}>
                                        {ep.method}
                                    </span>
                                    <code className="text-sm font-mono text-slate-900 dark:text-white font-medium flex-1">
                                        {ep.path}
                                    </code>
                                    <span className="text-sm text-slate-500 dark:text-gray-500 hidden md:block">{ep.desc}</span>
                                </motion.div>
                            ))}
                        </div>

                        <div className="mt-8">
                            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Authentication</h3>
                            <CodeBlock
                                language="bash"
                                code={`# Use your API key in all requests
curl https://api.modular-doc-ai.com/v1/results \\
  -H "Authorization: Bearer YOUR_API_KEY"`}
                            />
                        </div>
                    </motion.div>
                </section>

                {/* Architecture */}
                <section id="architecture" className="scroll-mt-40">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                    >
                        <h2 className="text-3xl font-extrabold text-slate-900 dark:text-white mb-4 flex items-center gap-3">
                            <Layers className="w-8 h-8 text-violet-500" />
                            How It Works
                        </h2>
                        <p className="text-slate-600 dark:text-gray-400 mb-8 text-lg leading-relaxed max-w-3xl">
                            Modular Doc AI processes your documents through multiple intelligent stages,
                            ensuring accuracy, quality, and full transparency at every step.
                        </p>

                        <div className="glass-panel rounded-2xl p-8">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div className="space-y-4">
                                    <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Processing Pipeline</h3>
                                    <div className="space-y-3">
                                        {[
                                            "Upload your document via dashboard or API",
                                            "AI identifies the document type and layout",
                                            "Intelligent extraction pulls key data fields",
                                            "Quality checks validate all extracted data",
                                            "AI generates explanations for each decision",
                                            "Uncertain items are sent for expert review",
                                            "Final validated results delivered to you",
                                        ].map((step, j) => (
                                            <div key={j} className="flex items-start gap-3 text-sm text-slate-600 dark:text-gray-400">
                                                <span className="text-xs font-bold text-brand-500 bg-brand-50 dark:bg-brand-500/10 px-2 py-0.5 rounded-md mt-0.5 shrink-0">
                                                    {j + 1}
                                                </span>
                                                {step}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                                <div className="space-y-4">
                                    <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Key Technologies</h3>
                                    <CodeBlock
                                        language="yaml"
                                        code={`platform:
  extraction:    # Adaptive AI engine
  transparency:  # Explainable results
  quality:       # Multi-layer validation
  gateway:       # Secure API access
  dashboard:     # Real-time monitoring
  storage:       # Secure data persistence
  caching:       # High-speed processing`}
                                    />
                                </div>
                            </div>
                        </div>
                    </motion.div>
                </section>

                {/* Modules */}
                <section id="modules" className="scroll-mt-40">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                    >
                        <h2 className="text-3xl font-extrabold text-slate-900 dark:text-white mb-4 flex items-center gap-3">
                            <Cpu className="w-8 h-8 text-emerald-500" />
                            Platform Capabilities
                        </h2>
                        <p className="text-slate-600 dark:text-gray-400 mb-8 text-lg leading-relaxed max-w-3xl">
                            Each capability is designed to work together seamlessly, giving you a complete document intelligence solution.
                        </p>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {modules.map((mod, i) => (
                                <motion.div
                                    key={i}
                                    initial={{ opacity: 0, y: 20 }}
                                    whileInView={{ opacity: 1, y: 0 }}
                                    viewport={{ once: true }}
                                    transition={{ delay: i * 0.08 }}
                                    className="glass-card rounded-2xl p-8 hover:translate-y-0"
                                >
                                    <div className="flex items-center justify-between mb-4">
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-xl bg-slate-50 dark:bg-gray-900 border border-slate-200 dark:border-gray-800 flex items-center justify-center">
                                                {mod.icon}
                                            </div>
                                            <h3 className="text-lg font-bold text-slate-900 dark:text-white">{mod.name}</h3>
                                        </div>
                                    </div>
                                    <p className="text-sm text-slate-600 dark:text-gray-400 leading-relaxed">{mod.desc}</p>
                                </motion.div>
                            ))}
                        </div>
                    </motion.div>
                </section>
            </div>

            {/* CTA */}
            <section className="relative z-10 py-24 border-t border-slate-200/60 dark:border-white/10 bg-white/40 dark:bg-gray-900/20">
                <div className="max-w-4xl mx-auto px-6 lg:px-8 text-center">
                    <h2 className="text-3xl lg:text-4xl font-extrabold text-slate-900 dark:text-white tracking-tight mb-4">
                        Need help getting started?
                    </h2>
                    <p className="text-lg text-slate-600 dark:text-gray-400 mb-8">
                        Our team is here to help you integrate Modular Doc AI into your workflow.
                    </p>
                    <div className="flex items-center justify-center gap-4 flex-wrap">
                        <Link href="/signup" className="px-8 py-4 glass-button rounded-xl text-lg flex items-center gap-2">
                            Start Building <ArrowRight className="w-5 h-5" />
                        </Link>
                        <Link href="/contact" className="px-8 py-4 bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 text-slate-700 dark:text-gray-300 hover:bg-slate-50 dark:hover:bg-gray-800 rounded-xl text-lg font-medium transition-all shadow-sm">
                            Contact Support
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}

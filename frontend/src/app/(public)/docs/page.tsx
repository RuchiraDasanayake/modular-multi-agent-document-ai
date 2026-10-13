"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { SignupLink } from "@/components/signup-link";

const sections = [
    { id: "quickstart", label: "Getting Started" },
    { id: "api", label: "Integration" },
    { id: "architecture", label: "How It Works" },
    { id: "modules", label: "Capabilities" },
];

const apiEndpoints = [
    {
        method: "POST",
        path: "/api/jobs",
        desc: "Create a job with the fields to extract",
        color: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10",
    },
    {
        method: "POST",
        path: "/api/jobs/{job_id}/documents",
        desc: "Upload documents to a job (multipart field files)",
        color: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10",
    },
    {
        method: "POST",
        path: "/api/jobs/{job_id}/auto",
        desc: "Start opt-in automatic extraction for selected file IDs",
        color: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10",
    },
    {
        method: "GET",
        path: "/api/jobs/{job_id}/auto",
        desc: "Read automatic run status and document IDs",
        color: "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10",
    },
    {
        method: "GET",
        path: "/api/jobs/{job_id}/auto/{run_id}/docs/{doc_id}",
        desc: "Read a document proposal, source text, and review",
        color: "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10",
    },
];

const modules = [
    {
        name: "Extraction Engine",
        desc: "Opt-in per-document schema and value proposals from local heuristics or a configured chat model.",
    },
    {
        name: "Transparency & Review",
        desc: "Source text, proposed fields, corrected results, and revisioned human review records.",
    },
    {
        name: "Source Evidence Checks",
        desc: "Exact source-text quote and typed-value checks for proposed values; human review remains necessary.",
    },
    {
        name: "Authenticated API",
        desc: "Authenticated, owner-scoped job and automatic extraction endpoints.",
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
                        Start the opt-in automatic extraction workflow and inspect its reviewable results.
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
                            Getting Started
                        </h2>
                        <p className="text-slate-600 dark:text-gray-400 mb-8 text-lg leading-relaxed max-w-3xl">
                            Create a job, upload a document, then start automatic schema extraction. A configured
                            chat model enables AI proposals; without one, the workflow uses local heuristics.
                        </p>

                        <div className="space-y-6">
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">1. Clone and start services</h3>
                                <CodeBlock
                                    language="bash"
                                    code={`git clone https://github.com/RuchiraDasanayake/modular-multi-agent-document-ai.git
cd modular-multi-agent-document-ai
cp .env.example .env
# Set JWT_SECRET_KEY and ADMIN_PASSWORD in .env before first start
docker compose up --build -d
# Gateway :8000 and frontend :3000 start with the default Compose profile`}
                                />
                            </div>
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">2. Log in to the dashboard</h3>
                                <CodeBlock
                                    language="text"
                                    code={`Open http://localhost:3000 in your browser.
Sign up for an account, or sign in with the admin account
created from ADMIN_PASSWORD in .env on first start.
Open Document Extraction, create a job, then choose Automatic schema extraction.
Model-backed runs currently require an admin account.`}
                                />
                            </div>
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">3. Upload and start automatic extraction</h3>
                                <CodeBlock
                                    language="bash"
                                    code={`# Sign in once; job endpoints need the token
TOKEN=$(curl -s -X POST http://localhost:3000/api/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"username":"admin","password":"your_password"}' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

# Create a job, upload a document, then start automatic extraction
JOB=$(curl -s -X POST http://localhost:3000/api/jobs -H "$AUTH" \\
  -H "Content-Type: application/json" \\
  -d '{"jobName":"sample documents"}' | jq -r .jobId)
FILE=$(curl -s -X POST http://localhost:3000/api/jobs/$JOB/documents -H "$AUTH" \\
  -F "files=@sample.pdf" | jq -r '.documents[-1].fileId')
RUN=$(curl -s -X POST http://localhost:3000/api/jobs/$JOB/auto -H "$AUTH" \\
  -H "Content-Type: application/json" \\
  -d "{\\"selectedFileIds\\":[\\"$FILE\\"]}" | jq -r .runId)`}
                                />
                            </div>
                            <div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">4. Poll the run and review the document</h3>
                                <CodeBlock
                                    language="bash"
                                    code={`# Repeat until the run status is success or failed
curl -s http://localhost:3000/api/jobs/$JOB/auto -H "$AUTH" | jq --arg run "$RUN" '.runs[] | select(.runId == $run)'

# After success, get a document ID and inspect its proposal
DOC=$(curl -s http://localhost:3000/api/jobs/$JOB/auto -H "$AUTH" |
  jq -r --arg run "$RUN" '.runs[] | select(.runId == $run) | .documents[0].docId')
curl -s http://localhost:3000/api/jobs/$JOB/auto/$RUN/docs/$DOC -H "$AUTH" | jq '.candidate, .correctedResult'
# Review fields in the dashboard at /dashboard/idpo/jobs/$JOB/auto/$RUN/docs/$DOC`}
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
                            Integration Guide
                        </h2>
                        <p className="text-slate-600 dark:text-gray-400 mb-8 text-lg leading-relaxed max-w-3xl">
                            Job endpoints require a signed-in session: send the token from <code>/api/auth/login</code>
                            as a Bearer header. The dashboard uses its session cookie. Automatic extraction requires a configured runner;
                            model-backed UI runs currently require admin access.
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
                                code={`# Login to get a JWT token
curl -X POST http://localhost:8000/api/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"username": "admin", "password": "your_password"}'

# Use the token in all requests
curl http://localhost:8000/api/dashboard/stats \\
  -H "Authorization: Bearer YOUR_TOKEN"`}
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
                            How It Works
                        </h2>
                        <p className="text-slate-600 dark:text-gray-400 mb-8 text-lg leading-relaxed max-w-3xl">
                            The automatic extraction path proposes reviewable fields and records source evidence.
                            It does not guarantee that the proposed schema or values are semantically correct.
                            The separate AHMN research runner supports Thompson Sampling policy routing and configurable OCR;
                            the <code>/auto</code> endpoints do not call it.
                        </p>

                        <div className="glass-panel rounded-2xl p-8">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div className="space-y-4">
                                    <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Processing Pipeline</h3>
                                    <div className="space-y-3">
                                        {[
                                            "Upload documents to a job via the dashboard or API",
                                            "Start opt-in automatic extraction for selected files",
                                            "Read native PDF text or use local OCR for image pages",
                                            "Local heuristics or a configured chat model propose fields and values",
                                            "Exact text quotes and typed values are checked for machine acceptance",
                                            "Operators review, correct, remove, or add fields",
                                            "Structured JSON and review history remain available per document",
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
                                    <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Current product path</h3>
                                    <CodeBlock
                                        language="text"
                                        code={`product_auto:
  ocr_default: Tesseract
  schema: local heuristics or configured chat model
  evidence: exact source-text quote and typed value
  review: document-level corrections and audit history
  output: structured JSON`}
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
                            Platform Capabilities
                        </h2>
                        <p className="text-slate-600 dark:text-gray-400 mb-8 text-lg leading-relaxed max-w-3xl">
                            These capabilities describe the current opt-in automatic extraction path.
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
                        <SignupLink className="px-8 py-4 glass-button rounded-xl text-lg flex items-center gap-2">
                            Start Building
                        </SignupLink>
                        <Link href="/contact" className="px-8 py-4 bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 text-slate-700 dark:text-gray-300 hover:bg-slate-50 dark:hover:bg-gray-800 rounded-xl text-lg font-medium transition-all shadow-sm">
                            Contact Support
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}

"use client";

export default function ArchitecturePage() {
    return (
        <div className="max-w-5xl mx-auto space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">System Architecture</h1>
                <p className="text-slate-500 dark:text-gray-500 mt-1">AHMN request lifecycle and component breakdown</p>
            </div>

            {/* Request Lifecycle */}
            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Request Lifecycle</h2>
                <div className="flex items-center gap-2 flex-wrap">
                    {[
                        { step: "1", label: "Document arrives", sub: "doc_type + vendor" },
                        { step: "2", label: "Embed context", sub: "MiniLM-L6 → 384d" },
                        { step: "3", label: "Query LTM", sub: "pgvector k-NN" },
                        { step: "4", label: "RABI init", sub: "Softmax-weighted prior" },
                        { step: "5", label: "Thompson Sample", sub: "Beta(α,β) → policy" },
                        { step: "6", label: "Return advice", sub: "Cache in STM" },
                        { step: "7", label: "Observe reward", sub: "F1 score" },
                        { step: "8", label: "DAAF check", sub: "Drift detection" },
                        { step: "9", label: "Bayesian update", sub: "α += r, β += (1-r)" },
                    ].map((s, i) => (
                        <div key={i} className="flex items-center gap-2">
                            <div className="bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-3 py-2 min-w-[130px]">
                                <div className="flex items-center gap-2">
                                    <span className="text-xs font-bold text-brand-400 bg-brand-500/10 px-1.5 py-0.5 rounded">
                                        {s.step}
                                    </span>
                                    <span className="text-sm text-slate-900 dark:text-white font-medium">{s.label}</span>
                                </div>
                                <p className="text-[11px] text-slate-500 dark:text-gray-500 mt-0.5">{s.sub}</p>
                            </div>
                            {i < 8 && <span className="text-slate-600 dark:text-gray-600">→</span>}
                        </div>
                    ))}
                </div>
            </div>

            {/* Algorithms Detail */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Thompson Sampling */}
                <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                    <h3 className="text-base font-semibold text-emerald-400 mb-3">Thompson Sampling</h3>
                    <div className="space-y-2 text-sm text-slate-600 dark:text-gray-300">
                        <p>Beta-Bernoulli conjugate model for each policy arm:</p>
                        <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3 font-mono text-xs text-slate-700 dark:text-gray-200">
                            <p>Prior: Beta(1, 1) = Uniform</p>
                            <p>Update: α += reward, β += (1 - reward)</p>
                            <p>Select: argmax sample(Beta(α, β))</p>
                        </div>
                        <p className="text-slate-500 dark:text-gray-500 text-xs">
                            References: Chapelle & Li (2011), Russo et al. (2018)
                        </p>
                    </div>
                </div>

                {/* RABI */}
                <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                    <h3 className="text-base font-semibold text-cyan-400 mb-3">RABI</h3>
                    <div className="space-y-2 text-sm text-slate-600 dark:text-gray-300">
                        <p>Cold-start solution via knowledge transfer:</p>
                        <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3 font-mono text-xs text-slate-700 dark:text-gray-200">
                            <p>wᵢ = softmax(simᵢ / τ)</p>
                            <p>α_init = 1 + Σ wᵢ·(αᵢ - 1)</p>
                            <p>β_init = 1 + Σ wᵢ·(βᵢ - 1)</p>
                        </div>
                        <p className="text-slate-500 dark:text-gray-500 text-xs">
                            Transfer (α-1, β-1) preserving pseudocount interpretation.
                        </p>
                    </div>
                </div>

                {/* DAAF */}
                <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                    <h3 className="text-base font-semibold text-violet-400 mb-3">DAAF</h3>
                    <div className="space-y-2 text-sm text-slate-600 dark:text-gray-300">
                        <p>Drift-aware forgetting separates noise from drift:</p>
                        <div className="bg-slate-100 dark:bg-gray-800 rounded-lg p-3 font-mono text-xs text-slate-700 dark:text-gray-200">
                            <p>Δ = |mean(recent) - mean(older)|</p>
                            <p>γ* = √(Δ² / ln(t))</p>
                            <p>α_new = 1 + (1-γ)(α - 1)</p>
                        </div>
                        <p className="text-slate-500 dark:text-gray-500 text-xs">
                            Key insight: use Δ (between-window), NOT σ² (within-window).
                        </p>
                    </div>
                </div>
            </div>

            {/* Tech Stack */}
            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Tech Stack</h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                        { label: "API", value: "FastAPI + Uvicorn" },
                        { label: "Database", value: "PostgreSQL + pgvector" },
                        { label: "Cache", value: "Redis (STM)" },
                        { label: "Embeddings", value: "all-MiniLM-L6-v2 (384d)" },
                        { label: "Frontend", value: "Next.js + Tailwind" },
                        { label: "Auth", value: "JWT + bcrypt" },
                        { label: "Experiments", value: "30 seeds × 7 methods × 4 scenarios" },
                        { label: "Container", value: "Docker Compose" },
                    ].map((t) => (
                        <div key={t.label} className="bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg px-4 py-3">
                            <p className="text-xs text-slate-500 dark:text-gray-500">{t.label}</p>
                            <p className="text-sm text-slate-900 dark:text-white font-medium mt-0.5">{t.value}</p>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

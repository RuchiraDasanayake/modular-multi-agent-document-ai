import { Icon } from "@/components/icons";

const CARD = "rounded-2xl border border-slate-200 bg-white/70 p-5 dark:border-gray-700 dark:bg-gray-800/40";

const REQUEST_STEPS = [
    { title: "Describe the document", detail: "The document type and vendor become a context string." },
    { title: "Embed it", detail: "A sentence-transformer turns the context into a vector." },
    { title: "Find similar contexts", detail: "A vector search over long-term memory returns the closest stored policies." },
    {
        title: "Build each policy's prior",
        detail: "A policy with close evidence keeps its own Beta counts; otherwise RABI borrows a prior from its neighbours.",
    },
    {
        title: "Draw a policy",
        detail: "Thompson sampling, seeded from the request, so the same request gets the same answer until the evidence changes.",
    },
    { title: "Return the advice", detail: "The advice waits in Redis (short-term memory) until its outcome arrives." },
];

const LEARNING_STEPS = [
    {
        title: "Record the outcome",
        detail: "The reward goes to mid-term memory and updates the policy's counts, which forget faster when DAAF sees that context's rewards drift.",
    },
    { title: "Apply expert feedback", detail: "A correct verdict adds success evidence to the policy; a wrong one adds failure evidence." },
    { title: "Promote", detail: "Every 30 minutes, policies that keep doing well move from mid-term to long-term memory." },
    { title: "Forget", detail: "Every 6 hours, DAAF decays stale policies and archives those that fall below the threshold." },
];

const ALGORITHMS = [
    {
        name: "Thompson sampling",
        lines: ["Prior: Beta(1, 1)", "Update: α += r, β += 1 − r", "Pick: argmax of one draw per policy"],
        note: "Chapelle and Li (2011); Russo et al. (2018).",
    },
    {
        name: "RABI cold start",
        lines: ["wᵢ = softmax(simᵢ / τ)", "α₀ = 1 + Σ wᵢ (αᵢ − 1)", "β₀ = 1 + Σ wᵢ (βᵢ − 1)"],
        note: "Transfers evidence counts from similar contexts instead of starting flat.",
    },
    {
        name: "DAAF forgetting",
        lines: ["Δ = |mean(recent) − mean(older)|", "γ* = √(Δ² / ln t)", "α′ = 1 + (1 − γ)(α − 1)"],
        note: "Reacts to a shift in the average reward, not to noise within a window.",
    },
];

const STACK = [
    { label: "API", value: "FastAPI" },
    { label: "Long-term memory", value: "PostgreSQL + pgvector" },
    { label: "Short-term memory", value: "Redis" },
    { label: "Embeddings", value: "Sentence Transformers" },
    { label: "Frontend", value: "Next.js + Tailwind" },
    { label: "Sign-in", value: "JWT, bcrypt password hashes" },
];

function StepList({ steps, start }: { steps: { title: string; detail: string }[]; start: number }) {
    return (
        <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {steps.map((step, index) => (
                <li key={step.title} className="flex gap-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900/60">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-xs font-bold text-brand-700 dark:bg-brand-500/10 dark:text-brand-300">
                        {start + index}
                    </span>
                    <div>
                        <p className="text-sm font-semibold text-slate-900 dark:text-white">{step.title}</p>
                        <p className="mt-1 text-sm text-slate-600 dark:text-gray-300">{step.detail}</p>
                    </div>
                </li>
            ))}
        </ol>
    );
}

export default function ArchitecturePage() {
    return (
        <div className="max-w-5xl 3xl:max-w-6xl mx-auto space-y-6">
            <div className="relative overflow-hidden glass-panel rounded-2xl p-6">
                <div className="absolute inset-0 bg-gradient-to-r from-brand-500/5 to-cyan-500/5 dark:from-brand-500/[0.03] dark:to-cyan-500/[0.03]" />
                <div className="relative">
                    <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white flex flex-wrap items-center gap-3">
                        <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-400 to-cyan-600 flex items-center justify-center shadow-lg shadow-brand-500/20 text-white">
                            <Icon name="layers" className="h-5 w-5" />
                        </span>
                        AHMN service architecture
                    </h1>
                    <p className="mt-1.5 max-w-3xl text-sm text-slate-600 dark:text-gray-300">
                        How the separate AHMN service answers a policy request and learns from what happens next.
                    </p>
                    <p className="mt-1 max-w-3xl text-xs text-slate-500 dark:text-gray-400">
                        The document pipeline and the benchmark do not call this service. They use an in-process advisor:
                        Thompson sampling over the stored policies, behind the safety gate, without RABI or DAAF.
                    </p>
                </div>
            </div>

            <section className={CARD}>
                <h2 className="text-base font-semibold text-slate-900 dark:text-white">When a policy is requested</h2>
                <p className="mt-1 mb-4 text-sm text-slate-600 dark:text-gray-300">POST /advice</p>
                <StepList steps={REQUEST_STEPS} start={1} />
            </section>

            <section className={CARD}>
                <h2 className="text-base font-semibold text-slate-900 dark:text-white">After the document is processed</h2>
                <p className="mt-1 mb-4 text-sm text-slate-600 dark:text-gray-300">
                    POST /advice/log and /advice/feedback, plus two background jobs
                </p>
                <StepList steps={LEARNING_STEPS} start={REQUEST_STEPS.length + 1} />
            </section>

            <section className="grid gap-4 lg:grid-cols-3">
                {ALGORITHMS.map((algorithm) => (
                    <div key={algorithm.name} className={CARD}>
                        <h2 className="text-base font-semibold text-slate-900 dark:text-white">{algorithm.name}</h2>
                        <div className="mt-3 space-y-1 rounded-lg bg-slate-100 p-3 font-mono text-xs text-slate-700 dark:bg-gray-900 dark:text-gray-200">
                            {algorithm.lines.map((line) => (
                                <p key={line}>{line}</p>
                            ))}
                        </div>
                        <p className="mt-3 text-xs text-slate-500 dark:text-gray-400">{algorithm.note}</p>
                    </div>
                ))}
            </section>

            <section className={CARD}>
                <h2 className="mb-4 text-base font-semibold text-slate-900 dark:text-white">Built with</h2>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                    {STACK.map((item) => (
                        <div key={item.label} className="rounded-lg border border-slate-200 bg-white px-4 py-3 dark:border-gray-700 dark:bg-gray-900/60">
                            <p className="text-xs text-slate-500 dark:text-gray-400">{item.label}</p>
                            <p className="mt-0.5 text-sm font-medium text-slate-900 dark:text-white">{item.value}</p>
                        </div>
                    ))}
                </div>
            </section>
        </div>
    );
}

"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { ArrowRight, Check, Sparkles, Building2, Zap } from "lucide-react";
import { useState } from "react";

const plans = [
    {
        name: "Community",
        icon: <Zap className="w-6 h-6" />,
        description: "Perfect for individuals and small projects getting started with document AI.",
        monthlyPrice: "Free",
        yearlyPrice: "Free",
        popular: false,
        cta: "Get Started",
        ctaHref: "/signup",
        features: [
            "100 documents / month",
            "5 document types",
            "Basic XAI explanations",
            "Standard guardrails",
            "Community support",
            "API access (rate-limited)",
            "Single user",
        ],
    },
    {
        name: "Pro",
        icon: <Sparkles className="w-6 h-6" />,
        description: "For growing teams that need advanced features and higher throughput.",
        monthlyPrice: "$49",
        yearlyPrice: "$39",
        popular: true,
        cta: "Start Free Trial",
        ctaHref: "/signup",
        features: [
            "10,000 documents / month",
            "All document types",
            "Full XAI with attention maps",
            "Advanced guardrails + custom rules",
            "Human-in-the-loop review",
            "AHMN + RABI selection",
            "Priority support",
            "Up to 10 team members",
            "Webhook integrations",
            "Custom export formats",
        ],
    },
    {
        name: "Enterprise",
        icon: <Building2 className="w-6 h-6" />,
        description: "Custom solutions for organizations with complex requirements at scale.",
        monthlyPrice: "Custom",
        yearlyPrice: "Custom",
        popular: false,
        cta: "Contact Sales",
        ctaHref: "/contact",
        features: [
            "Unlimited documents",
            "Custom document models",
            "Full XAI + audit logging",
            "Enterprise guardrails suite",
            "Dedicated HITL workforce",
            "All AI modules (AHMN, RABI, DAAF)",
            "24/7 premium support",
            "Unlimited team members",
            "SSO & RBAC",
            "On-premise deployment",
            "SLA guarantee (99.9%)",
            "Dedicated account manager",
        ],
    },
];

const faqs = [
    {
        q: "Can I switch plans later?",
        a: "Yes, you can upgrade or downgrade your plan at any time. Changes take effect immediately and we'll prorate the difference.",
    },
    {
        q: "What counts as a document?",
        a: "Each file uploaded for processing counts as one document, regardless of page count. Multi-page PDFs count as a single document.",
    },
    {
        q: "Do you offer academic or nonprofit discounts?",
        a: "Yes! We offer 50% off Pro plans for verified academic institutions and registered nonprofits. Contact us for details.",
    },
    {
        q: "Is there a free trial for Pro?",
        a: "Absolutely. Every Pro plan starts with a 14-day free trial with full access to all features. No credit card required.",
    },
    {
        q: "What about data security?",
        a: "All data is encrypted in transit (TLS 1.3) and at rest (AES-256). Enterprise plans offer additional options including on-premise deployment and custom data retention policies.",
    },
];

export default function PricingPage() {
    const [annual, setAnnual] = useState(true);

    return (
        <div className="relative overflow-hidden">
            {/* Hero */}
            <section className="relative py-24 lg:py-32">
                <div className="absolute top-0 right-1/3 w-[600px] h-[600px] bg-emerald-500/15 dark:bg-emerald-500/5 rounded-full blur-[150px] pointer-events-none" />
                <div className="max-w-7xl mx-auto px-6 lg:px-8 relative text-center">
                    <motion.h1
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5 }}
                        className="text-4xl lg:text-6xl font-extrabold text-slate-900 dark:text-white tracking-tight leading-[1.1]"
                    >
                        Simple, transparent{" "}
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-emerald-500">
                            pricing
                        </span>
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: 0.1 }}
                        className="text-lg text-slate-600 dark:text-gray-400 mt-6 max-w-2xl mx-auto"
                    >
                        Start free and scale as you grow. No hidden fees, no surprises.
                    </motion.p>

                    {/* Billing Toggle */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: 0.2 }}
                        className="mt-10 inline-flex items-center gap-3 bg-slate-100 dark:bg-gray-800/50 rounded-xl p-1.5"
                    >
                        <button
                            onClick={() => setAnnual(false)}
                            className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${!annual
                                    ? "bg-white dark:bg-gray-900 text-slate-900 dark:text-white shadow-sm"
                                    : "text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white"
                                }`}
                        >
                            Monthly
                        </button>
                        <button
                            onClick={() => setAnnual(true)}
                            className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${annual
                                    ? "bg-white dark:bg-gray-900 text-slate-900 dark:text-white shadow-sm"
                                    : "text-slate-600 dark:text-gray-400 hover:text-slate-900 dark:hover:text-white"
                                }`}
                        >
                            Annual
                            <span className="text-xs bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 px-2 py-0.5 rounded-full font-semibold">
                                Save 20%
                            </span>
                        </button>
                    </motion.div>
                </div>
            </section>

            {/* Plans */}
            <section className="relative z-10 pb-24">
                <div className="max-w-7xl mx-auto px-6 lg:px-8">
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                        {plans.map((plan, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.1 }}
                                className={`relative rounded-3xl p-8 lg:p-10 ${plan.popular
                                        ? "glass-panel ring-2 ring-brand-500/30 dark:ring-brand-500/20 scale-[1.02]"
                                        : "glass-card hover:translate-y-0"
                                    }`}
                            >
                                {plan.popular && (
                                    <div className="absolute -top-4 left-1/2 -translate-x-1/2 px-4 py-1.5 bg-gradient-to-r from-brand-500 to-violet-500 text-white text-xs font-bold rounded-full shadow-lg">
                                        Most Popular
                                    </div>
                                )}
                                <div className="flex items-center gap-3 mb-4">
                                    <div className={`w-10 h-10 rounded-xl ${plan.popular
                                            ? "bg-brand-50 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/20"
                                            : "bg-slate-100 dark:bg-gray-800 border-slate-200 dark:border-gray-700"
                                        } border flex items-center justify-center ${plan.popular ? "text-brand-500" : "text-slate-600 dark:text-gray-400"
                                        }`}>
                                        {plan.icon}
                                    </div>
                                    <h3 className="text-xl font-bold text-slate-900 dark:text-white">{plan.name}</h3>
                                </div>
                                <p className="text-sm text-slate-600 dark:text-gray-400 mb-6 leading-relaxed">
                                    {plan.description}
                                </p>
                                <div className="mb-8">
                                    <span className="text-4xl font-extrabold text-slate-900 dark:text-white">
                                        {annual ? plan.yearlyPrice : plan.monthlyPrice}
                                    </span>
                                    {plan.monthlyPrice !== "Free" && plan.monthlyPrice !== "Custom" && (
                                        <span className="text-slate-500 dark:text-gray-500 ml-2">/ month</span>
                                    )}
                                </div>
                                <Link
                                    href={plan.ctaHref}
                                    className={`w-full py-3 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all ${plan.popular
                                            ? "glass-button"
                                            : "bg-slate-100 dark:bg-gray-800 text-slate-700 dark:text-gray-300 hover:bg-slate-200 dark:hover:bg-gray-700 border border-slate-200 dark:border-gray-700"
                                        }`}
                                >
                                    {plan.cta} <ArrowRight className="w-4 h-4" />
                                </Link>
                                <div className="mt-8 pt-8 border-t border-slate-200/60 dark:border-white/10 space-y-3">
                                    {plan.features.map((feature, j) => (
                                        <div key={j} className="flex items-center gap-3 text-sm text-slate-700 dark:text-gray-300">
                                            <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                                            {feature}
                                        </div>
                                    ))}
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            {/* FAQ */}
            <section className="relative z-10 py-24 border-t border-slate-200/60 dark:border-white/10 bg-white/40 dark:bg-gray-900/20">
                <div className="max-w-3xl mx-auto px-6 lg:px-8">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl lg:text-4xl font-extrabold text-slate-900 dark:text-white tracking-tight">
                            Frequently asked questions
                        </h2>
                    </div>
                    <div className="space-y-6">
                        {faqs.map((faq, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 10 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.05 }}
                                className="glass-card rounded-2xl p-6 hover:translate-y-0"
                            >
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">{faq.q}</h3>
                                <p className="text-slate-600 dark:text-gray-400 leading-relaxed">{faq.a}</p>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>
        </div>
    );
}

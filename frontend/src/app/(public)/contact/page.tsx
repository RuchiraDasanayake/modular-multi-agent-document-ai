"use client";

import { useState } from "react";
import { motion } from "framer-motion";

const contactEmail = (process.env.NEXT_PUBLIC_CONTACT_EMAIL || "").trim();

export default function ContactPage() {
    const [submitted, setSubmitted] = useState(false);
    const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!contactEmail) return;
        const mailtoUrl = `mailto:${contactEmail}?subject=${encodeURIComponent(form.subject)}&body=${encodeURIComponent(`From: ${form.name} (${form.email})\n\n${form.message}`)}`;
        window.open(mailtoUrl, '_blank');
        setSubmitted(true);
        setTimeout(() => setSubmitted(false), 5000);
        setForm({ name: "", email: "", subject: "", message: "" });
    };

    return (
        <div className="relative overflow-hidden">
            {/* Hero */}
            <section className="relative py-24 lg:py-32">
                <div className="absolute top-0 right-1/4 w-[600px] h-[600px] bg-brand-500/15 dark:bg-brand-500/5 rounded-full blur-[150px] pointer-events-none" />
                <div className="max-w-7xl mx-auto px-6 lg:px-8 relative text-center">
                    <motion.h1
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5 }}
                        className="text-4xl lg:text-6xl font-extrabold text-slate-900 dark:text-white tracking-tight leading-[1.1]"
                    >
                        Get in{" "}
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-500 to-violet-500">
                            touch
                        </span>
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.5, delay: 0.1 }}
                        className="text-lg text-slate-600 dark:text-gray-400 mt-6 max-w-2xl mx-auto"
                    >
                        Questions about the research, the system design, or the evaluation?
                        We&apos;d love to hear from you.
                    </motion.p>
                </div>
            </section>

            {/* Contact Form + Social */}
            <section className="relative z-10 py-16 lg:py-24">
                <div className="max-w-3xl mx-auto px-6 lg:px-8">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                    >
                        <div className="glass-panel rounded-3xl p-8 lg:p-10">
                            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Send us a message</h2>
                            <p className="text-slate-600 dark:text-gray-400 mb-8">
                                {contactEmail
                                    ? "Submitting opens your email app with this message addressed to the research team."
                                    : "A contact address has not been configured for this deployment."}
                            </p>

                            {submitted && (
                                <motion.div
                                    initial={{ opacity: 0, y: -10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="mb-6 p-4 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 flex items-center gap-3"
                                >
                                    <p className="text-sm text-emerald-700 dark:text-emerald-300 font-medium">
                                        Your email app should now be open with this message. Send it from there.
                                    </p>
                                </motion.div>
                            )}

                            <form onSubmit={handleSubmit} className="space-y-6">
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">
                                            Name
                                        </label>
                                        <input
                                            type="text"
                                            required
                                            value={form.name}
                                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                                            className="w-full px-4 py-3 glass-input"
                                            placeholder="Your name"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">
                                            Email
                                        </label>
                                        <input
                                            type="email"
                                            required
                                            value={form.email}
                                            onChange={(e) => setForm({ ...form, email: e.target.value })}
                                            className="w-full px-4 py-3 glass-input"
                                            placeholder="you@example.com"
                                        />
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">
                                        Subject
                                    </label>
                                    <input
                                        type="text"
                                        required
                                        value={form.subject}
                                        onChange={(e) => setForm({ ...form, subject: e.target.value })}
                                        className="w-full px-4 py-3 glass-input"
                                        placeholder="How can we help?"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-gray-300 mb-2">
                                        Message
                                    </label>
                                    <textarea
                                        required
                                        rows={5}
                                        value={form.message}
                                        onChange={(e) => setForm({ ...form, message: e.target.value })}
                                        className="w-full px-4 py-3 glass-input resize-none"
                                        placeholder="Tell us more about your needs..."
                                    />
                                </div>
                                <button
                                    type="submit"
                                    disabled={!contactEmail}
                                    className="w-full py-3.5 glass-button rounded-xl text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    Compose Email
                                </button>
                            </form>
                        </div>
                    </motion.div>
                </div>
            </section>
        </div>
    );
}

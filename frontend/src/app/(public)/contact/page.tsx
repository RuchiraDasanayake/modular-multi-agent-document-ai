"use client";

import { useState } from "react";
import { motion } from "framer-motion";

const socialLinks = [
    { href: "https://github.com", label: "GitHub" },
    { href: "https://twitter.com", label: "Twitter" },
    { href: "https://linkedin.com", label: "LinkedIn" },
];

export default function ContactPage() {
    const [submitted, setSubmitted] = useState(false);
    const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        // Build mailto link with form data
        const mailtoUrl = `mailto:modulardocai@university.edu?subject=${encodeURIComponent(form.subject)}&body=${encodeURIComponent(`From: ${form.name} (${form.email})\n\n${form.message}`)}`;
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
                        Have a question about our platform? Want to discuss enterprise solutions?
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
                            <p className="text-slate-600 dark:text-gray-400 mb-8">Fill out the form and we&apos;ll get back to you within 24 hours.</p>

                            {submitted && (
                                <motion.div
                                    initial={{ opacity: 0, y: -10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="mb-6 p-4 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 flex items-center gap-3"
                                >
                                    <p className="text-sm text-emerald-700 dark:text-emerald-300 font-medium">
                                        Message sent successfully! We&apos;ll get back to you soon.
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
                                    className="w-full py-3.5 glass-button rounded-xl text-sm font-medium flex items-center justify-center gap-2"
                                >

                                    Send Message
                                </button>
                            </form>
                        </div>

                        {/* Social Links */}
                        <div className="flex items-center justify-center gap-4 mt-8">
                            <span className="text-sm text-slate-500 dark:text-gray-400">Follow us:</span>
                            {socialLinks.map((social, i) => (
                                <a
                                    key={i}
                                    href={social.href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="w-10 h-10 rounded-xl flex items-center justify-center bg-slate-100 dark:bg-gray-800 text-slate-500 dark:text-gray-400 hover:text-brand-600 dark:hover:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10 border border-slate-200 dark:border-gray-700 transition-all"
                                    aria-label={social.label}
                                >

                                </a>
                            ))}
                        </div>
                    </motion.div>
                </div>
            </section>
        </div>
    );
}

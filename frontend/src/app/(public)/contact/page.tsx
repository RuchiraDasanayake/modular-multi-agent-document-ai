"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import {
    Mail,
    MessageSquare,
    MapPin,
    Clock,
    Send,
    CheckCircle2,
    Github,
    Twitter,
    Linkedin,
} from "lucide-react";

const contactInfo = [
    {
        icon: <Mail className="w-6 h-6 text-brand-500" />,
        title: "Email Us",
        desc: "Our team will respond within 24 hours.",
        value: "hello@modulardocai.com",
        href: "mailto:hello@modulardocai.com",
    },
    {
        icon: <MessageSquare className="w-6 h-6 text-violet-500" />,
        title: "Live Chat",
        desc: "Available Monday to Friday, 9am-6pm EST.",
        value: "Start a conversation",
        href: "#",
    },
    {
        icon: <MapPin className="w-6 h-6 text-emerald-500" />,
        title: "Office",
        desc: "Visit us at our headquarters.",
        value: "San Francisco, CA",
        href: "#",
    },
    {
        icon: <Clock className="w-6 h-6 text-amber-500" />,
        title: "Working Hours",
        desc: "We're available during business hours.",
        value: "Mon-Fri, 9am-6pm EST",
        href: "#",
    },
];

const socialLinks = [
    { icon: <Github className="w-5 h-5" />, href: "https://github.com", label: "GitHub" },
    { icon: <Twitter className="w-5 h-5" />, href: "https://twitter.com", label: "Twitter" },
    { icon: <Linkedin className="w-5 h-5" />, href: "https://linkedin.com", label: "LinkedIn" },
];

export default function ContactPage() {
    const [submitted, setSubmitted] = useState(false);
    const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        // Simulate form submission
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

            {/* Contact Cards */}
            <section className="relative z-10 -mt-8">
                <div className="max-w-7xl mx-auto px-6 lg:px-8">
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                        {contactInfo.map((info, i) => (
                            <motion.a
                                key={i}
                                href={info.href}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.08 }}
                                className="glass-card rounded-2xl p-6 text-center block"
                            >
                                <div className="w-12 h-12 rounded-xl bg-slate-50 dark:bg-gray-900 border border-slate-200 dark:border-gray-800 flex items-center justify-center mb-4 mx-auto">
                                    {info.icon}
                                </div>
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1">{info.title}</h3>
                                <p className="text-xs text-slate-500 dark:text-gray-500 mb-3">{info.desc}</p>
                                <p className="text-sm font-medium text-brand-600 dark:text-brand-400">{info.value}</p>
                            </motion.a>
                        ))}
                    </div>
                </div>
            </section>

            {/* Contact Form + Info */}
            <section className="relative z-10 py-24 lg:py-32">
                <div className="max-w-7xl mx-auto px-6 lg:px-8">
                    <div className="grid grid-cols-1 lg:grid-cols-5 gap-12">
                        {/* Form */}
                        <motion.div
                            initial={{ opacity: 0, x: -20 }}
                            whileInView={{ opacity: 1, x: 0 }}
                            viewport={{ once: true }}
                            className="lg:col-span-3"
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
                                        <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
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
                                        <Send className="w-4 h-4" />
                                        Send Message
                                    </button>
                                </form>
                            </div>
                        </motion.div>

                        {/* Sidebar Info */}
                        <motion.div
                            initial={{ opacity: 0, x: 20 }}
                            whileInView={{ opacity: 1, x: 0 }}
                            viewport={{ once: true }}
                            className="lg:col-span-2 space-y-8"
                        >
                            <div className="glass-card rounded-2xl p-8 hover:translate-y-0">
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-4">
                                    Enterprise Solutions
                                </h3>
                                <p className="text-sm text-slate-600 dark:text-gray-400 leading-relaxed mb-4">
                                    Need a custom deployment, higher limits, or dedicated support?
                                    Our enterprise team can design a solution tailored to your organization.
                                </p>
                                <ul className="space-y-2.5 text-sm text-slate-600 dark:text-gray-400">
                                    <li className="flex items-center gap-2">
                                        <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                                        On-premise deployment
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                                        Custom AI model training
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                                        Dedicated account manager
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                                        SLA guarantee (99.9%)
                                    </li>
                                </ul>
                            </div>

                            <div className="glass-card rounded-2xl p-8 hover:translate-y-0">
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-4">
                                    Follow Us
                                </h3>
                                <p className="text-sm text-slate-600 dark:text-gray-400 leading-relaxed mb-4">
                                    Stay updated with the latest features, releases, and AI research.
                                </p>
                                <div className="flex items-center gap-3">
                                    {socialLinks.map((social, i) => (
                                        <a
                                            key={i}
                                            href={social.href}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="w-10 h-10 rounded-xl flex items-center justify-center bg-slate-100 dark:bg-gray-800 text-slate-500 dark:text-gray-400 hover:text-brand-600 dark:hover:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10 border border-slate-200 dark:border-gray-700 transition-all"
                                            aria-label={social.label}
                                        >
                                            {social.icon}
                                        </a>
                                    ))}
                                </div>
                            </div>

                            <div className="glass-card rounded-2xl p-8 hover:translate-y-0">
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-4">
                                    FAQ
                                </h3>
                                <p className="text-sm text-slate-600 dark:text-gray-400 leading-relaxed">
                                    Check our{" "}
                                    <a href="/pricing#faq" className="text-brand-600 dark:text-brand-400 hover:underline font-medium">
                                        frequently asked questions
                                    </a>{" "}
                                    for quick answers to common questions about pricing, features, and setup.
                                </p>
                            </div>
                        </motion.div>
                    </div>
                </div>
            </section>
        </div>
    );
}

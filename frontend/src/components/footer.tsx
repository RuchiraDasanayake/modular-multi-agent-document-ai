import Link from "next/link";

const footerLinks = {
    product: {
        title: "Product",
        links: [
            { label: "Features", href: "/features" },
            { label: "Pricing", href: "/pricing" },
            { label: "Documentation", href: "/docs" },
        ],
    },
    company: {
        title: "Company",
        links: [
            { label: "About", href: "/about" },
            { label: "Contact", href: "/contact" },
            { label: "Careers", href: "#" },
        ],
    },
    resources: {
        title: "Resources",
        links: [
            { label: "Getting Started", href: "/docs" },
            { label: "API Reference", href: "/docs" },
            { label: "GitHub", href: "#" },
        ],
    },
};

const socialLinks = [
    { href: "https://github.com", label: "GitHub" },
    { href: "https://twitter.com", label: "Twitter" },
    { href: "https://linkedin.com", label: "LinkedIn" },
    { href: "mailto:hello@modulardocai.com", label: "Email" },
];

export function Footer() {
    return (
        <footer className="relative border-t border-slate-200/60 dark:border-white/10 bg-white/50 dark:bg-gray-950/50 backdrop-blur-lg">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {/* Main Footer */}
                <div className="py-12 sm:py-16 grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-5 gap-8 sm:gap-12">
                    {/* Brand */}
                    <div className="col-span-2 lg:col-span-2 space-y-4">
                        <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center text-white text-sm font-bold shadow-md shadow-brand-500/25">
                                AI
                            </div>
                            <span className="text-lg font-bold text-slate-900 dark:text-white tracking-tight">
                                Modular Doc AI
                            </span>
                        </div>
                        <p className="text-sm text-slate-600 dark:text-gray-400 leading-relaxed max-w-sm">
                            Adaptive document extraction built on AHMN policy learning and IDPO runtime orchestration.
                        </p>
                        <div className="flex items-center gap-3 pt-2">
                            {socialLinks.map((social) => (
                                <a
                                    key={social.label}
                                    href={social.href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="px-3 h-9 rounded-lg flex items-center justify-center bg-slate-100 dark:bg-gray-800 text-xs font-semibold text-slate-500 dark:text-gray-400 hover:text-brand-600 dark:hover:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10 transition-all"
                                    aria-label={social.label}
                                >
                                    {social.label}
                                </a>
                            ))}
                        </div>
                    </div>

                    {/* Link Columns */}
                    {Object.values(footerLinks).map((section) => (
                        <div key={section.title}>
                            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4 uppercase tracking-wider">
                                {section.title}
                            </h3>
                            <ul className="space-y-3">
                                {section.links.map((link) => (
                                    <li key={link.label}>
                                        <Link
                                            href={link.href}
                                            className="text-sm text-slate-600 dark:text-gray-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
                                        >
                                            {link.label}
                                        </Link>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}
                </div>

                {/* Bottom Bar */}
                <div className="py-6 border-t border-slate-200/60 dark:border-white/10 flex flex-col sm:flex-row items-center justify-between gap-4">
                    <p className="text-sm text-slate-500 dark:text-gray-500">
                        &copy; {new Date().getFullYear()} Modular Doc AI. All rights reserved.
                    </p>
                </div>
            </div>
        </footer>
    );
}

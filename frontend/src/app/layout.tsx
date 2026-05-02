import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { ToastProvider } from "@/components/toast";

export const metadata: Metadata = {
    title: "Modular Document AI",
    description: "Adaptive document extraction with policy-driven pipelines, reviewer-in-the-loop feedback, and validation guardrails.",
    keywords: ["document AI", "NLP", "machine learning", "explainable AI", "guardrails", "multi-agent"],
    authors: [{ name: "Modular Doc AI Team" }],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en" suppressHydrationWarning>
            <body className="min-h-screen bg-slate-50 dark:bg-gray-950 text-slate-900 dark:text-gray-100 transition-colors duration-300">
                <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
                    <ToastProvider>
                        {children}
                    </ToastProvider>
                </ThemeProvider>
            </body>
        </html>
    );
}

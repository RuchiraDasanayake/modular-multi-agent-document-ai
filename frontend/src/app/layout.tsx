import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
    title: "AHMN Dashboard",
    description: "Adaptive Hierarchical Memory Network — Admin Dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en" className="dark">
            <body className="min-h-screen">{children}</body>
        </html>
    );
}

"use client";

import { motion, useMotionValue, useTransform, useSpring } from "framer-motion";
import { useEffect, useState } from "react";

export default function LoadingScreen() {
    const [mounted, setMounted] = useState(false);

    // Mouse position for 3D tilt
    const x = useMotionValue(0);
    const y = useMotionValue(0);

    // Smooth spring physics for the tilt - reduced damping for faster response
    const mouseXSpring = useSpring(x, { stiffness: 300, damping: 15 });
    const mouseYSpring = useSpring(y, { stiffness: 300, damping: 15 });

    // Transform mouse position to rotation degrees
    const rotateX = useTransform(mouseYSpring, [-0.5, 0.5], ["15deg", "-15deg"]);
    const rotateY = useTransform(mouseXSpring, [-0.5, 0.5], ["-15deg", "15deg"]);

    useEffect(() => {
        setMounted(true);
        const handleMouseMove = (e: MouseEvent) => {
            const rect = document.body.getBoundingClientRect();
            const width = rect.width;
            const height = rect.height;
            const mouseX = e.clientX;
            const mouseY = e.clientY;
            const xPct = mouseX / width - 0.5;
            const yPct = mouseY / height - 0.5;
            x.set(xPct);
            y.set(yPct);
        };

        window.addEventListener("mousemove", handleMouseMove);
        return () => window.removeEventListener("mousemove", handleMouseMove);
    }, [x, y]);

    if (!mounted) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-50/80 dark:bg-gray-950/80 backdrop-blur-xl overflow-hidden perspective-1000 transition-colors duration-300">
            {/* 3D Interactive Card */}
            <motion.div
                style={{
                    rotateX,
                    rotateY,
                    transformStyle: "preserve-3d",
                }}
                className="relative w-80 h-96 rounded-2xl border border-white/40 dark:border-white/10 bg-white/60 dark:bg-gray-900/40 backdrop-blur-md shadow-2xl shadow-slate-200/50 dark:shadow-black/20 flex flex-col items-center justify-center p-8"
            >
                <motion.div
                    style={{ transform: "translateZ(50px)" }}
                    className="relative w-32 h-40 bg-white dark:bg-gray-900/80 border border-brand-500/20 dark:border-brand-500/30 rounded-xl shadow-xl shadow-slate-200/50 dark:shadow-black/20 flex items-center justify-center overflow-hidden"
                >
                    <span className="text-2xl font-bold text-brand-500">AI</span>
                </motion.div>

                <motion.div
                    style={{ transform: "translateZ(30px)" }}
                    className="mt-8 text-center"
                >
                    <h2 className="text-xl font-bold text-slate-900 dark:text-white tracking-wide flex items-center justify-center gap-2">
                        Extracting Data
                    </h2>
                    <p className="text-sm text-slate-500 dark:text-gray-400 mt-2">
                        Initializing neural pathways...
                    </p>
                </motion.div>

            </motion.div>
        </div>
    );
}

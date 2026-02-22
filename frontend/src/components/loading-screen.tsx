"use client";

import { motion, useMotionValue, useTransform, useSpring } from "framer-motion";
import { useEffect, useState } from "react";
import { FileText, ScanLine, Sparkles } from "lucide-react";

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
            {/* Background ambient glow */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <motion.div
                    animate={{
                        scale: [1, 1.2, 1],
                        opacity: [0.3, 0.5, 0.3],
                    }}
                    transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                    className="w-[500px] h-[500px] bg-brand-500/20 rounded-full blur-[120px]"
                />
            </div>

            {/* 3D Interactive Card */}
            <motion.div
                style={{
                    rotateX,
                    rotateY,
                    transformStyle: "preserve-3d",
                }}
                className="relative w-80 h-96 rounded-2xl border border-white/40 dark:border-white/10 bg-white/60 dark:bg-gray-900/40 backdrop-blur-md shadow-2xl shadow-slate-200/50 dark:shadow-black/20 flex flex-col items-center justify-center p-8"
            >
                {/* Inner 3D elements */}
                <motion.div
                    style={{ transform: "translateZ(50px)" }}
                    className="relative w-32 h-40 bg-white dark:bg-gray-900/80 border border-brand-500/20 dark:border-brand-500/30 rounded-xl shadow-xl shadow-slate-200/50 dark:shadow-black/20 flex items-center justify-center overflow-hidden"
                >
                    {/* Document Icon */}
                    <FileText className="w-16 h-16 text-brand-500" strokeWidth={1.5} />

                    {/* Scanning Laser */}
                    <motion.div
                        animate={{ top: ["-10%", "110%"] }}
                        transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                        className="absolute left-0 right-0 h-0.5 bg-brand-400 shadow-[0_0_15px_3px_rgba(56,189,248,0.6)] z-10"
                    />

                    {/* Scanning overlay gradient */}
                    <motion.div
                        animate={{ top: ["-10%", "110%"] }}
                        transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                        className="absolute left-0 right-0 h-20 bg-gradient-to-b from-transparent to-brand-500/10 -translate-y-full"
                    />
                </motion.div>

                <motion.div
                    style={{ transform: "translateZ(30px)" }}
                    className="mt-8 text-center"
                >
                    <h2 className="text-xl font-bold text-slate-900 dark:text-white tracking-wide flex items-center justify-center gap-2">
                        <Sparkles className="w-5 h-5 text-brand-500" />
                        Extracting Data
                    </h2>
                    <p className="text-sm text-slate-500 dark:text-gray-400 mt-2">
                        Initializing neural pathways...
                    </p>
                </motion.div>

                {/* Floating particles */}
                {[...Array(5)].map((_, i) => (
                    <motion.div
                        key={i}
                        style={{ transform: `translateZ(${20 + i * 10}px)` }}
                        animate={{
                            y: [0, -20, 0],
                            opacity: [0, 1, 0],
                        }}
                        transition={{
                            duration: 2 + Math.random() * 2,
                            repeat: Infinity,
                            delay: Math.random() * 2,
                        }}
                        className="absolute w-1 h-1 bg-brand-400 rounded-full"
                        initial={{
                            left: `${20 + Math.random() * 60}%`,
                            top: `${20 + Math.random() * 60}%`,
                        }}
                    />
                ))}
            </motion.div>
        </div>
    );
}

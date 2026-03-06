"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ResultsPage() {
    const router = useRouter();
    useEffect(() => {
        router.replace("/dashboard/experiments");
    }, [router]);
    return null;
}

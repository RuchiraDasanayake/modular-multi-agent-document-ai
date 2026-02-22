"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/types";
import { isAuthenticated } from "@/lib/auth";

/**
 * Hook to fetch the current authenticated user.
 * Returns { user, loading, error }.
 */
export function useUser() {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!isAuthenticated()) {
            setLoading(false);
            return;
        }
        // Add a small artificial delay to show off the 3D loading screen
        Promise.all([
            api.me(),
            new Promise(resolve => setTimeout(resolve, 1500))
        ])
            .then(([userData]) => setUser(userData))
            .catch((err) => setError(err.message))
            .finally(() => setLoading(false));
    }, []);

    return { user, loading, error, isAdmin: user?.role === "admin" };
}

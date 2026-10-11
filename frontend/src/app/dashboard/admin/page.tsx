"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useUser } from "@/hooks/use-user";
import { Icon } from "@/components/icons";

interface User {
    id: string;
    email: string;
    username: string;
    role: string;
    is_active: boolean;
}

const EMPTY_FORM = { email: "", username: "", password: "", role: "viewer" };
const FIELD =
    "w-full px-3 py-2 bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/50";
const LABEL = "block text-xs font-semibold text-slate-700 dark:text-gray-200 mb-1";

export default function AdminPage() {
    const { user: currentUser, isAdmin, loading: userLoading } = useUser();
    const [users, setUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState(EMPTY_FORM);
    const [creating, setCreating] = useState(false);
    const [formError, setFormError] = useState("");
    const [error, setError] = useState("");

    const load = useCallback(() => {
        api.getUsers()
            .then((list) => {
                setUsers(list as User[]);
                setError("");
            })
            .catch((err) => setError(err instanceof Error ? err.message : "The user list could not be loaded."))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        if (!userLoading && isAdmin) {
            load();
        }
    }, [userLoading, isAdmin, load]);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError("");
        setCreating(true);
        try {
            await api.register(form);
            setShowForm(false);
            setForm(EMPTY_FORM);
            load();
        } catch (err: unknown) {
            setFormError(err instanceof Error ? err.message : "The account could not be created.");
        } finally {
            setCreating(false);
        }
    };

    const handleToggle = async (target: User) => {
        if (target.is_active && !window.confirm(`Disable ${target.username}? They will not be able to sign in until you enable the account again.`)) {
            return;
        }
        try {
            await api.toggleUser(target.id);
            load();
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : `${target.username} could not be updated.`);
        }
    };

    if (userLoading || (isAdmin && loading)) {
        return (
            <div className="flex items-center justify-center h-64" role="status">
                <span className="sr-only">Loading</span>
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    if (!isAdmin) {
        return (
            <div className="max-w-4xl 3xl:max-w-5xl mx-auto">
                <div className="glass-panel rounded-2xl p-12 text-center">
                    <div className="w-14 h-14 mx-auto rounded-2xl bg-slate-100 dark:bg-gray-800 border border-slate-200 dark:border-gray-700 flex items-center justify-center mb-4 text-slate-600 dark:text-gray-300">
                        <Icon name="lock" className="h-6 w-6" />
                    </div>
                    <h1 className="text-xl font-bold text-slate-900 dark:text-white mb-2">For administrators only</h1>
                    <p className="text-slate-600 dark:text-gray-300 text-sm">Sign in with an admin account to manage users.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-4xl 3xl:max-w-5xl mx-auto space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Users</h1>
                    <p className="text-slate-600 dark:text-gray-300 mt-1 text-sm">Create admin and viewer accounts, and turn sign-in on or off.</p>
                </div>
                <button
                    type="button"
                    onClick={() => {
                        setShowForm((value) => !value);
                        setFormError("");
                    }}
                    aria-expanded={showForm}
                    className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm font-semibold text-white transition-colors"
                >
                    {showForm ? "Cancel" : "New user"}
                </button>
            </div>

            {error && (
                <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300">
                    {error}
                </div>
            )}

            {showForm && (
                <form onSubmit={handleCreate} className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl p-6 space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                            <label htmlFor="new-user-email" className={LABEL}>Email</label>
                            <input
                                id="new-user-email"
                                type="email"
                                required
                                autoComplete="off"
                                value={form.email}
                                onChange={(e) => setForm({ ...form, email: e.target.value })}
                                className={FIELD}
                            />
                        </div>
                        <div>
                            <label htmlFor="new-user-username" className={LABEL}>Username</label>
                            <input
                                id="new-user-username"
                                type="text"
                                required
                                autoComplete="off"
                                value={form.username}
                                onChange={(e) => setForm({ ...form, username: e.target.value })}
                                className={FIELD}
                            />
                        </div>
                        <div>
                            <label htmlFor="new-user-password" className={LABEL}>Password</label>
                            <input
                                id="new-user-password"
                                type="password"
                                required
                                minLength={6}
                                autoComplete="new-password"
                                value={form.password}
                                onChange={(e) => setForm({ ...form, password: e.target.value })}
                                className={FIELD}
                            />
                            <p className="mt-1 text-xs text-slate-500 dark:text-gray-400">At least 6 characters.</p>
                        </div>
                        <div>
                            <label htmlFor="new-user-role" className={LABEL}>Role</label>
                            <select
                                id="new-user-role"
                                value={form.role}
                                onChange={(e) => setForm({ ...form, role: e.target.value })}
                                className={FIELD}
                            >
                                <option value="viewer">Viewer</option>
                                <option value="admin">Admin</option>
                            </select>
                        </div>
                    </div>
                    {formError && (
                        <div role="alert" className="text-sm text-red-800 dark:text-red-300 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg px-4 py-2">
                            {formError}
                        </div>
                    )}
                    <button
                        type="submit"
                        disabled={creating}
                        className="px-4 py-2 bg-brand-600 hover:bg-brand-700 rounded-lg text-sm font-semibold text-white transition-colors disabled:opacity-50"
                    >
                        {creating ? "Creating…" : "Create user"}
                    </button>
                </form>
            )}

            <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-xl overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                    <thead>
                        <tr className="border-b border-slate-200 dark:border-gray-800 bg-slate-100/80 dark:bg-gray-800/40">
                            <th className="text-left py-3 px-4 text-slate-600 dark:text-gray-300 font-medium">Username</th>
                            <th className="text-left py-3 px-4 text-slate-600 dark:text-gray-300 font-medium">Email</th>
                            <th className="text-left py-3 px-4 text-slate-600 dark:text-gray-300 font-medium">Role</th>
                            <th className="text-left py-3 px-4 text-slate-600 dark:text-gray-300 font-medium">Sign-in</th>
                            <th className="py-3 px-4">
                                <span className="sr-only">Actions</span>
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {users.length === 0 && (
                            <tr>
                                <td colSpan={5} className="py-10 text-center text-sm text-slate-500 dark:text-gray-400">
                                    No users yet.
                                </td>
                            </tr>
                        )}
                        {users.map((u) => {
                            const isSelf = currentUser?.id === u.id;
                            return (
                                <tr key={u.id} className="border-b border-slate-200 dark:border-gray-800/50 hover:bg-slate-50 dark:hover:bg-gray-800/30">
                                    <td className="py-3 px-4 text-slate-900 dark:text-white font-medium">
                                        {u.username}
                                        {isSelf && <span className="ml-2 text-xs font-normal text-slate-500 dark:text-gray-400">(you)</span>}
                                    </td>
                                    <td className="py-3 px-4 text-slate-600 dark:text-gray-300">{u.email}</td>
                                    <td className="py-3 px-4">
                                        <span
                                            className={`text-xs font-medium px-2 py-0.5 rounded ${
                                                u.role === "admin"
                                                    ? "bg-brand-50 text-brand-800 dark:bg-brand-500/10 dark:text-brand-300"
                                                    : "bg-slate-100 text-slate-700 dark:bg-gray-700 dark:text-gray-300"
                                            }`}
                                        >
                                            {u.role === "admin" ? "Admin" : "Viewer"}
                                        </span>
                                    </td>
                                    <td className="py-3 px-4">
                                        <span className={`text-xs font-medium ${u.is_active ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}>
                                            {u.is_active ? "Allowed" : "Disabled"}
                                        </span>
                                    </td>
                                    <td className="py-3 px-4 text-right">
                                        {!isSelf && (
                                            <button
                                                type="button"
                                                onClick={() => void handleToggle(u)}
                                                className="rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white"
                                            >
                                                {u.is_active ? "Disable" : "Enable"}
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

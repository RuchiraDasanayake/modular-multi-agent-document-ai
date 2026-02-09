"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface User {
    id: string;
    email: string;
    username: string;
    role: string;
    is_active: boolean;
}

export default function AdminPage() {
    const [users, setUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ email: "", username: "", password: "", role: "viewer" });
    const [error, setError] = useState("");

    const load = () => {
        api.getUsers()
            .then(setUsers)
            .catch(() => { })
            .finally(() => setLoading(false));
    };

    useEffect(load, []);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        try {
            await api.register(form);
            setShowForm(false);
            setForm({ email: "", username: "", password: "", role: "viewer" });
            load();
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Failed");
        }
    };

    const handleToggle = async (userId: string) => {
        await api.toggleUser(userId);
        load();
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    return (
        <div className="max-w-4xl mx-auto space-y-8">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-white">User Management</h1>
                    <p className="text-gray-500 mt-1">Manage admin and viewer accounts</p>
                </div>
                <button
                    onClick={() => setShowForm(!showForm)}
                    className="px-4 py-2 bg-brand-600 hover:bg-brand-500 rounded-lg text-sm text-white transition-colors"
                >
                    {showForm ? "Cancel" : "+ New User"}
                </button>
            </div>

            {/* Create User Form */}
            {showForm && (
                <form onSubmit={handleCreate} className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs text-gray-500 mb-1">Email</label>
                            <input
                                type="email" required value={form.email}
                                onChange={(e) => setForm({ ...form, email: e.target.value })}
                                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm
                           focus:outline-none focus:ring-2 focus:ring-brand-500/50"
                            />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-500 mb-1">Username</label>
                            <input
                                type="text" required value={form.username}
                                onChange={(e) => setForm({ ...form, username: e.target.value })}
                                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm
                           focus:outline-none focus:ring-2 focus:ring-brand-500/50"
                            />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-500 mb-1">Password</label>
                            <input
                                type="password" required minLength={6} value={form.password}
                                onChange={(e) => setForm({ ...form, password: e.target.value })}
                                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm
                           focus:outline-none focus:ring-2 focus:ring-brand-500/50"
                            />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-500 mb-1">Role</label>
                            <select
                                value={form.role}
                                onChange={(e) => setForm({ ...form, role: e.target.value })}
                                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm
                           focus:outline-none focus:ring-2 focus:ring-brand-500/50"
                            >
                                <option value="viewer">Viewer</option>
                                <option value="admin">Admin</option>
                            </select>
                        </div>
                    </div>
                    {error && (
                        <div className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2">
                            {error}
                        </div>
                    )}
                    <button
                        type="submit"
                        className="px-4 py-2 bg-brand-600 hover:bg-brand-500 rounded-lg text-sm text-white transition-colors"
                    >
                        Create User
                    </button>
                </form>
            )}

            {/* Users Table */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-gray-800 bg-gray-800/40">
                            <th className="text-left py-3 px-4 text-gray-400 font-medium">Username</th>
                            <th className="text-left py-3 px-4 text-gray-400 font-medium">Email</th>
                            <th className="text-left py-3 px-4 text-gray-400 font-medium">Role</th>
                            <th className="text-left py-3 px-4 text-gray-400 font-medium">Status</th>
                            <th className="text-right py-3 px-4 text-gray-400 font-medium">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {users.map((u) => (
                            <tr key={u.id} className="border-b border-gray-800/50 hover:bg-gray-800/20">
                                <td className="py-3 px-4 text-white font-medium">{u.username}</td>
                                <td className="py-3 px-4 text-gray-400">{u.email}</td>
                                <td className="py-3 px-4">
                                    <span
                                        className={`text-xs font-medium px-2 py-0.5 rounded ${u.role === "admin"
                                                ? "bg-brand-500/10 text-brand-400"
                                                : "bg-gray-700 text-gray-400"
                                            }`}
                                    >
                                        {u.role}
                                    </span>
                                </td>
                                <td className="py-3 px-4">
                                    <span
                                        className={`text-xs font-medium ${u.is_active ? "text-emerald-400" : "text-red-400"}`}
                                    >
                                        {u.is_active ? "Active" : "Disabled"}
                                    </span>
                                </td>
                                <td className="py-3 px-4 text-right">
                                    <button
                                        onClick={() => handleToggle(u.id)}
                                        className="text-xs text-gray-500 hover:text-white transition-colors"
                                    >
                                        {u.is_active ? "Disable" : "Enable"}
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

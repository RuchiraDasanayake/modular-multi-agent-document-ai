interface StatCardProps {
    label: string;
    value: string | number;
    icon: string;
    delta?: string;
    deltaType?: "positive" | "negative" | "neutral";
}

export default function StatCard({ label, value, icon, delta, deltaType = "neutral" }: StatCardProps) {
    const deltaColor =
        deltaType === "positive"
            ? "text-emerald-600 dark:text-emerald-400"
            : deltaType === "negative"
                ? "text-red-600 dark:text-red-400"
                : "text-slate-500 dark:text-gray-400";

    return (
        <div className="group glass-stat p-5">
            <div className="relative z-10">
                <div className="flex items-center justify-between mb-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-50 to-cyan-50 dark:from-brand-500/10 dark:to-cyan-500/10 border border-brand-100/60 dark:border-brand-500/15 flex items-center justify-center shadow-sm group-hover:shadow-md group-hover:shadow-brand-500/10 transition-all duration-300">
                        <span className="text-lg group-hover:scale-110 transition-transform duration-200">{icon}</span>
                    </div>
                    {delta && <span className={`text-xs font-medium ${deltaColor}`}>{delta}</span>}
                </div>
                <p className="text-2xl font-extrabold text-slate-900 dark:text-white tracking-tight">{value}</p>
                <p className="text-xs text-slate-500 dark:text-gray-400 mt-1 font-medium">{label}</p>
            </div>
        </div>
    );
}

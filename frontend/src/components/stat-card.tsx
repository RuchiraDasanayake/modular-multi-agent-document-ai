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
        <div className="glass-card rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
                <span className="text-2xl drop-shadow-sm">{icon}</span>
                {delta && <span className={`text-xs font-medium ${deltaColor}`}>{delta}</span>}
            </div>
            <p className="text-2xl font-bold text-slate-900 dark:text-white">{value}</p>
            <p className="text-sm text-slate-500 dark:text-gray-400 mt-1">{label}</p>
        </div>
    );
}

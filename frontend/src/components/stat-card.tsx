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
            ? "text-emerald-400"
            : deltaType === "negative"
                ? "text-red-400"
                : "text-gray-500";

    return (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 card-hover">
            <div className="flex items-center justify-between mb-3">
                <span className="text-2xl">{icon}</span>
                {delta && <span className={`text-xs font-medium ${deltaColor}`}>{delta}</span>}
            </div>
            <p className="text-2xl font-bold text-white">{value}</p>
            <p className="text-sm text-gray-500 mt-1">{label}</p>
        </div>
    );
}

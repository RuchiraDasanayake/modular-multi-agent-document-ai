export default function DashboardLoading() {
    return (
        <div className="flex min-h-[60vh] items-center justify-center" role="status" aria-label="Loading dashboard content">
            <div className="flex flex-col items-center gap-4">
                {/* Spinner */}
                <div className="relative h-12 w-12">
                    <div className="absolute inset-0 rounded-full border-4 border-gray-200 dark:border-gray-700" />
                    <div className="absolute inset-0 animate-spin rounded-full border-4 border-transparent border-t-indigo-600 dark:border-t-indigo-400" />
                </div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                    Loading…
                </p>
            </div>
        </div>
    );
}

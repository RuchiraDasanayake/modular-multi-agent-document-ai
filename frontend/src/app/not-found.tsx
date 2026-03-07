import Link from "next/link";

export default function NotFound() {
    return (
        <div className="flex min-h-screen items-center justify-center bg-gray-50 p-6 dark:bg-gray-950">
            <div className="w-full max-w-md text-center">
                <p className="text-7xl font-bold text-indigo-600 dark:text-indigo-400">404</p>
                <h1 className="mt-4 text-2xl font-bold text-gray-900 dark:text-white">
                    Page not found
                </h1>
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                    The page you&apos;re looking for doesn&apos;t exist or has been moved.
                </p>
                <div className="mt-8 flex items-center justify-center gap-3">
                    <Link
                        href="/dashboard"
                        className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
                    >
                        Go to Dashboard
                    </Link>
                    <Link
                        href="/"
                        className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    >
                        Go home
                    </Link>
                </div>
            </div>
        </div>
    );
}

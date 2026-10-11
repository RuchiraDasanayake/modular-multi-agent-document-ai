import type { ReactNode } from "react";

const PATHS = {
    home: (
        <>
            <path d="M3 11l9-7 9 7" />
            <path d="M5 10v10h14V10" />
        </>
    ),
    document: (
        <>
            <path d="M6 3h8l4 4v14H6z" />
            <path d="M14 3v4h4" />
            <path d="M9 12h6M9 16h6" />
        </>
    ),
    chart: (
        <>
            <path d="M4 20h16" />
            <path d="M7 16v-5M12 16V7M17 16v-8" />
        </>
    ),
    play: (
        <>
            <circle cx="12" cy="12" r="9" />
            <path d="M10 8.5l5 3.5-5 3.5z" />
        </>
    ),
    chat: <path d="M4 5h16v11H9l-5 4z" />,
    shield: (
        <>
            <path d="M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z" />
            <path d="M9 12l2 2 4-4" />
        </>
    ),
    userCheck: (
        <>
            <circle cx="9" cy="8" r="4" />
            <path d="M2 21c0-3.9 3.1-7 7-7s7 3.1 7 7" />
            <path d="M16 11l2 2 4-4" />
        </>
    ),
    flask: (
        <>
            <path d="M9 3h6" />
            <path d="M10 3v6l-5 10a1.5 1.5 0 001.3 2h11.4a1.5 1.5 0 001.3-2L14 9V3" />
            <path d="M7.5 15h9" />
        </>
    ),
    clipboard: (
        <>
            <rect x="6" y="4" width="12" height="17" rx="2" />
            <path d="M9 4h6v3H9z" />
            <path d="M9 13l2 2 4-4" />
        </>
    ),
    seedling: (
        <>
            <path d="M12 21V11" />
            <path d="M12 11c0-4 3-6 7-6 0 4-3 6-7 6z" />
            <path d="M12 13c0-3-2.5-5-6-5 0 3 2.5 5 6 5z" />
        </>
    ),
    activity: <path d="M3 12h4l3-8 4 16 3-8h4" />,
    bolt: <path d="M13 10V3L4 14h7v7l9-11h-7z" />,
    users: (
        <>
            <circle cx="9" cy="8" r="4" />
            <path d="M2 21c0-3.9 3.1-7 7-7s7 3.1 7 7" />
            <path d="M16 4a4 4 0 010 8" />
            <path d="M18 14c2.4.9 4 3.2 4 7" />
        </>
    ),
    database: (
        <>
            <ellipse cx="12" cy="5" rx="8" ry="3" />
            <path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
            <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
        </>
    ),
    sun: (
        <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </>
    ),
    moon: <path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z" />,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="M6 6l12 12M18 6L6 18" />,
    logout: (
        <>
            <path d="M9 4H5v16h4" />
            <path d="M16 8l4 4-4 4" />
            <path d="M20 12H10" />
        </>
    ),
    upload: (
        <>
            <path d="M12 16V4" />
            <path d="M7 9l5-5 5 5" />
            <path d="M4 16v4h16v-4" />
        </>
    ),
    arrowRight: <path d="M5 12h14M13 6l6 6-6 6" />,
    check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
    minus: <path d="M6 12h12" />,
    chevronDown: <path d="M6 9l6 6 6-6" />,
    send: (
        <>
            <path d="M21 3L3 10.5l7 2.5 2.5 7z" />
            <path d="M21 3L10 13" />
        </>
    ),
    search: (
        <>
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-4-4" />
        </>
    ),
    lock: (
        <>
            <rect x="5" y="11" width="14" height="10" rx="2" />
            <path d="M8 11V7a4 4 0 018 0v4" />
        </>
    ),
    refresh: (
        <>
            <path d="M20 11a8 8 0 10-2.3 5.7" />
            <path d="M20 4v7h-7" />
        </>
    ),
    inbox: (
        <>
            <path d="M3 13l3-8h12l3 8v6H3z" />
            <path d="M3 13h5l1 3h6l1-3h5" />
        </>
    ),
    alert: (
        <>
            <path d="M12 4l9 16H3z" />
            <path d="M12 10v4M12 17h.01" />
        </>
    ),
    sliders: <path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6" />,
    window: (
        <>
            <rect x="3" y="5" width="18" height="14" rx="2" />
            <path d="M3 9h18" />
        </>
    ),
    trendDown: <path d="M3 7l6 6 4-4 8 8M21 11v6h-6" />,
    clock: (
        <>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5l3 2" />
        </>
    ),
    info: (
        <>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 11v5M12 8h.01" />
        </>
    ),
    layers: (
        <>
            <path d="M12 3l9 5-9 5-9-5z" />
            <path d="M3 13l9 5 9-5" />
        </>
    ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

export function Icon({ name, className = "h-4 w-4" }: { name: IconName; className?: string }) {
    return (
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            className={className}
        >
            {PATHS[name]}
        </svg>
    );
}

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Public routes that don't require authentication
const publicPaths = [
  "/",
  "/features",
  "/about",
  "/docs",
  "/contact",
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
];

// Local API routes that read or change job data. They run on this server, so the gateway never sees them.
const sessionApiPrefixes = ["/api/jobs", "/api/runs", "/api/benchmarks"];

const SESSION_CACHE_MS = 60_000;
const verifiedSessions = new Map<string, number>();

function gatewayUrl(): string {
  return process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

function requestToken(request: NextRequest): string | undefined {
  const header = request.headers.get("authorization");
  if (header && header.toLowerCase().startsWith("bearer ")) {
    return header.slice(7).trim() || undefined;
  }
  return request.cookies.get("ahmn_token")?.value;
}

async function verifySession(token: string): Promise<"ok" | "invalid" | "unavailable"> {
  const now = Date.now();
  if ((verifiedSessions.get(token) ?? 0) > now) {
    return "ok";
  }
  try {
    const res = await fetch(`${gatewayUrl()}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (res.ok) {
      if (verifiedSessions.size > 1000) {
        for (const [key, expiresAt] of verifiedSessions) {
          if (expiresAt <= now) verifiedSessions.delete(key);
        }
      }
      verifiedSessions.set(token, now + SESSION_CACHE_MS);
      return "ok";
    }
    verifiedSessions.delete(token);
    return res.status === 401 || res.status === 403 ? "invalid" : "unavailable";
  } catch {
    return "unavailable";
  }
}

function isUnexpiredJwt(token: string): boolean {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return false;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    return !(payload.exp && payload.exp * 1000 < Date.now());
  } catch {
    return false;
  }
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isSessionApi = sessionApiPrefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));

  // Allow public paths, gateway-proxied API routes, and static assets
  if (!isSessionApi && (publicPaths.includes(pathname) || pathname.startsWith("/api") || pathname.startsWith("/_next"))) {
    return NextResponse.next();
  }

  // Dashboard pages render job data on this server too, so a well-formed cookie is not enough: the gateway must accept it
  const token = requestToken(request);
  const session = token && isUnexpiredJwt(token) ? await verifySession(token) : "invalid";
  if (session === "ok") {
    return NextResponse.next();
  }

  if (isSessionApi) {
    return NextResponse.json(
      { error: session === "invalid" ? "Sign in to use the job API." : "The sign-in service is unavailable." },
      { status: session === "invalid" ? 401 : 503 },
    );
  }
  if (session === "unavailable") {
    return new NextResponse("The sign-in service is unavailable. Try again shortly.", { status: 503 });
  }
  const res = NextResponse.redirect(new URL("/login", request.url));
  if (token) {
    res.cookies.delete("ahmn_token");
  }
  return res;
}

export const config = {
  // Upload POST authenticates and checks ownership in its route before reading
  // the body. Avoid Next's proxy clone, which buffers and truncates at 10 MiB;
  // the route instead streams the original bytes through its explicit limits.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|api/jobs/[^/]+/documents/?$).*)"],
};

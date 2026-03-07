import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Public routes that don't require authentication
const publicPaths = [
  "/",
  "/features",
  "/about",
  "/pricing",
  "/docs",
  "/contact",
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
];

export function middleware(request: NextRequest) {
  const token = request.cookies.get("ahmn_token")?.value;
  const { pathname } = request.nextUrl;

  // Allow public paths, API routes, and static assets
  if (publicPaths.includes(pathname) || pathname.startsWith("/api") || pathname.startsWith("/_next")) {
    return NextResponse.next();
  }

  // Redirect to login if not authenticated
  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Basic JWT structure & expiry validation
  try {
    const parts = token.split(".");
    if (parts.length !== 3) throw new Error("malformed");
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      // Token expired — clear and redirect
      const res = NextResponse.redirect(new URL("/login", request.url));
      res.cookies.delete("ahmn_token");
      return res;
    }
  } catch {
    // Malformed token — clear and redirect
    const res = NextResponse.redirect(new URL("/login", request.url));
    res.cookies.delete("ahmn_token");
    return res;
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

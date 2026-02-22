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
];

export function middleware(request: NextRequest) {
  const token = request.cookies.get("ahmn_token")?.value;
  const { pathname } = request.nextUrl;

  // Allow public paths and API routes
  if (publicPaths.includes(pathname) || pathname.startsWith("/api")) {
    return NextResponse.next();
  }

  // Development mode: allow access without authentication
  // Remove this block in production
  const isDev = process.env.NODE_ENV === "development";
  if (isDev) {
    return NextResponse.next();
  }

  // Redirect to login if not authenticated
  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

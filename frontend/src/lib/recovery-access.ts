import { NextResponse } from "next/server";

/** Passive recovery permits only the authenticated artifact readback protocol. */
export function recoveryReadOnlyResponse(request: Request): NextResponse | null {
  if (process.env.IDPO_RECOVERY_READ_ONLY !== "1") return null;
  const { pathname, search } = new URL(request.url);
  const identifier = "[A-Za-z0-9_-]{1,128}";
  const artifact = new RegExp(`^/api/jobs/${identifier}/(?:docs/${identifier}/content|auto/${identifier}/export)$`);
  const allowed = !search && (
    (request.method === "POST" && pathname === "/api/auth/login") ||
    (request.method === "GET" && (["/api/health", "/api/auth/me"].includes(pathname) || artifact.test(pathname)))
  );
  if (allowed) return null;
  return NextResponse.json({ error: "This recovery copy is read-only." }, {
    status: 423,
    headers: { "X-DocAI-Recovery": "read-only", "Cache-Control": "no-store" },
  });
}

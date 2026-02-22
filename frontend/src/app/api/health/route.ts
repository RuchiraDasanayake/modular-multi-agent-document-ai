import { NextResponse } from "next/server";

/**
 * Internal health-check for the Docker HEALTHCHECK directive.
 * This avoids hitting the /api rewrites which proxy to the backend.
 */
export async function GET() {
  return NextResponse.json({ status: "ok", service: "ahmn-frontend" });
}

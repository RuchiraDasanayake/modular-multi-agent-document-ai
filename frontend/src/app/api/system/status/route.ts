import { NextResponse } from "next/server";
import { getSystemStatus } from "@/server/status";
import { requireAdmin, requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    requireAdmin(await requireUser(request.headers));
    const status = await getSystemStatus();
    return NextResponse.json(status);
  } catch (error) {
    return apiError(error, 500);
  }
}

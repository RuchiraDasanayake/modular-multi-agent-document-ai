import { NextResponse } from "next/server";
import { getSystemStatus } from "@/server/status";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const status = await getSystemStatus();
    return NextResponse.json(status);
  } catch (error) {
    return apiError(error, 500);
  }
}

import { NextResponse } from "next/server";
import { AccessError } from "@/server/auth";

export function apiError(error: unknown, status = 400) {
  const message = error instanceof Error ? error.message : "Unknown error";
  return NextResponse.json({ error: message }, { status: error instanceof AccessError ? error.statusCode : status });
}

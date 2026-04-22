import { NextResponse } from "next/server";
import { apiError } from "@/server/api/response";
import { createJobCustomPolicy, listJobPolicies } from "@/server/policies";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
};

interface Params {
  params: Promise<{ jobId: string }>;
}

function parseStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
    .filter((entry) => entry.length > 0);
}

export async function GET(_: Request, { params }: Params) {
  try {
    const { jobId } = await params;
    return NextResponse.json(listJobPolicies(jobId), { headers: NO_STORE_HEADERS });
  } catch (error) {
    return apiError(error, 400);
  }
}

export async function POST(request: Request, { params }: Params) {
  try {
    const { jobId } = await params;
    const payload = (await request.json()) as Record<string, unknown>;
    const policyId = typeof payload.policyId === "string" ? payload.policyId : "";
    const name = typeof payload.name === "string" ? payload.name : "";
    const executionProfile =
      payload.executionProfile === "fast_local" || payload.executionProfile === "balanced" || payload.executionProfile === "heavy_cloud"
        ? payload.executionProfile
        : "balanced";

    if (!policyId.trim()) {
      throw new Error("policyId is required");
    }
    if (!name.trim()) {
      throw new Error("name is required");
    }

    const created = createJobCustomPolicy(jobId, {
      policyId,
      name,
      executionProfile,
      instructions: typeof payload.instructions === "string" ? payload.instructions : null,
      routeBins: parseStringArray(payload.routeBins),
      contentProfiles: parseStringArray(payload.contentProfiles),
      vendorClusters: parseStringArray(payload.vendorClusters),
      docTypes: parseStringArray(payload.docTypes),
      explicitEntities: parseStringArray(payload.explicitEntities),
    });

    return NextResponse.json(
      {
        created,
        workspace: listJobPolicies(jobId),
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error) {
    return apiError(error, 400);
  }
}

export interface AuthenticatedUser {
  id: string;
  role: string;
}

export class AccessError extends Error {
  constructor(message: string, readonly statusCode: number) {
    super(message);
  }
}

function accessToken(headers: Headers): string | null {
  const authorization = headers.get("authorization");
  if (authorization?.toLowerCase().startsWith("bearer ")) {
    return authorization.slice(7).trim() || null;
  }
  const cookie = headers.get("cookie")?.split(";").map((part) => part.trim())
    .find((part) => part.startsWith("ahmn_token="));
  if (!cookie) return null;
  try {
    return decodeURIComponent(cookie.slice("ahmn_token=".length)) || null;
  } catch {
    return null;
  }
}

export async function requireUser(headers: Headers): Promise<AuthenticatedUser> {
  const token = accessToken(headers);
  if (!token) throw new AccessError("Sign in to access this resource.", 401);

  const gateway = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  let response: Response;
  try {
    response = await fetch(`${gateway}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    throw new AccessError("The sign-in service is unavailable.", 503);
  }
  if (response.status === 401 || response.status === 403) {
    throw new AccessError("Sign in to access this resource.", 401);
  }
  if (!response.ok) throw new AccessError("The sign-in service is unavailable.", 503);

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new AccessError("The sign-in service returned an invalid response.", 503);
  }
  if (!payload || typeof payload !== "object" || !("id" in payload) || !("role" in payload)
    || typeof payload.id !== "string" || !payload.id || typeof payload.role !== "string") {
    throw new AccessError("The sign-in service returned an invalid response.", 503);
  }
  return { id: payload.id, role: payload.role };
}

export function requireAdmin(user: AuthenticatedUser): void {
  if (user.role !== "admin") throw new AccessError("Admin access required.", 403);
}

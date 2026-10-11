import assert from "node:assert/strict";
import http from "node:http";
import type { AddressInfo } from "node:net";
import test from "node:test";
import { NextRequest } from "next/server";
import { middleware } from "../middleware";

interface FakeGateway {
  baseUrl: string;
  meCalls: () => number;
  close: () => Promise<void>;
}

async function startFakeGateway(acceptedTokens: string[]): Promise<FakeGateway> {
  let calls = 0;
  const server = http.createServer((request, response) => {
    if (request.url === "/api/auth/me") {
      calls += 1;
      const token = (request.headers.authorization ?? "").replace(/^Bearer /, "");
      response.statusCode = acceptedTokens.includes(token) ? 200 : 401;
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify(response.statusCode === 200 ? { id: "u1", username: "admin" } : { detail: "Invalid token" }));
      return;
    }
    response.statusCode = 404;
    response.end();
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return {
    baseUrl: `http://127.0.0.1:${port}`,
    meCalls: () => calls,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

function jwtShapedToken(subject: string): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode({ sub: subject, exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

function passedThrough(response: Response): boolean {
  return response.headers.get("x-middleware-next") === "1";
}

test("job API requires a session the gateway accepts", async () => {
  const valid = jwtShapedToken("valid-user");
  const forged = jwtShapedToken("forged-user");
  const gateway = await startFakeGateway([valid]);
  process.env.INTERNAL_API_URL = gateway.baseUrl;
  try {
    const anonymous = await middleware(new NextRequest("http://localhost:3000/api/jobs"));
    assert.equal(anonymous.status, 401);

    const withBearer = await middleware(
      new NextRequest("http://localhost:3000/api/jobs/job-1/documents", { headers: { authorization: `Bearer ${valid}` } }),
    );
    assert.ok(passedThrough(withBearer));

    const withForgedCookie = await middleware(
      new NextRequest("http://localhost:3000/api/runs/run-1/summary", { headers: { cookie: `ahmn_token=${forged}` } }),
    );
    assert.equal(withForgedCookie.status, 401);

    const callsBefore = gateway.meCalls();
    const cached = await middleware(
      new NextRequest("http://localhost:3000/api/benchmarks", { headers: { cookie: `ahmn_token=${valid}` } }),
    );
    assert.ok(passedThrough(cached));
    assert.equal(gateway.meCalls(), callsBefore);
  } finally {
    await gateway.close();
  }
});

test("dashboard pages redirect a forged cookie to login and clear it", async () => {
  const valid = jwtShapedToken("page-user");
  const forged = jwtShapedToken("page-forger");
  const gateway = await startFakeGateway([valid]);
  process.env.INTERNAL_API_URL = gateway.baseUrl;
  try {
    const forgedPage = await middleware(
      new NextRequest("http://localhost:3000/dashboard/idpo/runs/run-1", { headers: { cookie: `ahmn_token=${forged}` } }),
    );
    assert.equal(forgedPage.status, 307);
    assert.equal(new URL(forgedPage.headers.get("location") ?? "").pathname, "/login");
    assert.match(forgedPage.headers.get("set-cookie") ?? "", /ahmn_token=;/);

    const validPage = await middleware(
      new NextRequest("http://localhost:3000/dashboard/idpo", { headers: { cookie: `ahmn_token=${valid}` } }),
    );
    assert.ok(passedThrough(validPage));
  } finally {
    await gateway.close();
  }
});

test("public routes need no session and an unreachable gateway fails closed", async () => {
  const gateway = await startFakeGateway([]);
  await gateway.close();
  process.env.INTERNAL_API_URL = gateway.baseUrl;

  assert.ok(passedThrough(await middleware(new NextRequest("http://localhost:3000/api/health"))));
  assert.ok(passedThrough(await middleware(new NextRequest("http://localhost:3000/login"))));

  const token = jwtShapedToken("offline-user");
  const jobs = await middleware(new NextRequest("http://localhost:3000/api/jobs", { headers: { authorization: `Bearer ${token}` } }));
  assert.equal(jobs.status, 503);
  const page = await middleware(new NextRequest("http://localhost:3000/dashboard", { headers: { cookie: `ahmn_token=${token}` } }));
  assert.equal(page.status, 503);
});

import type { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const origin = process.env.ASSISTANT_API_URL;
  if (!origin)
    return Response.json(
      {
        detail:
          "The assistant service has not been connected to this deployment.",
      },
      { status: 503 },
    );
  const { path } = await context.params;
  if (
    path[0] === "dev-session" &&
    !(
      process.env.NODE_ENV === "development" &&
      process.env.LOCAL_DEMO_AUTH === "true"
    )
  )
    return Response.json({ detail: "Not found." }, { status: 404 });
  if (path.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part)))
    return Response.json({ detail: "Invalid request path." }, { status: 400 });
  const headers = new Headers();
  for (const name of [
    "authorization",
    "content-type",
    "x-workspace-id",
    "x-demo-role",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("accept", request.headers.get("accept") || "application/json");
  try {
    const upstream = await fetch(
      `${origin.replace(/\/$/, "")}/api/${path.join("/")}${request.nextUrl.search}`,
      {
        method: request.method,
        headers,
        cache: "no-store",
        body: ["GET", "HEAD"].includes(request.method)
          ? undefined
          : await request.arrayBuffer(),
        signal: AbortSignal.timeout(55000),
      },
    );
    const responseHeaders = new Headers({ "Cache-Control": "no-store" });
    responseHeaders.set(
      "Content-Type",
      upstream.headers.get("content-type") || "application/json",
    );
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    const timedOut =
      error instanceof Error &&
      ["TimeoutError", "AbortError"].includes(error.name);
    return Response.json(
      {
        detail: timedOut
          ? "The service is taking longer than expected. Your saved work is safe; try reconnecting."
          : "The assistant service could not be reached. Please try again.",
      },
      { status: timedOut ? 504 : 502 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as DELETE, proxy as PATCH };

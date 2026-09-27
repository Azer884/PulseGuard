import { callBackend, isAllowedBackendPath, type BackendMethod } from "@/lib/backend";

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, { params }: Context, method: BackendMethod) {
  const { path } = await params;
  if (!isAllowedBackendPath(path)) {
    return Response.json({ detail: "Not found" }, { status: 404 });
  }
  const body = method === "POST" || method === "PUT" ? await request.text() : undefined;
  const { status, text } = await callBackend(path, method, body, new URL(request.url).search);
  if (status === 204) return new Response(null, { status });
  return new Response(text, { status, headers: { "Content-Type": "application/json" } });
}

export const GET = (req: Request, ctx: Context) => proxy(req, ctx, "GET");
export const POST = (req: Request, ctx: Context) => proxy(req, ctx, "POST");
export const PUT = (req: Request, ctx: Context) => proxy(req, ctx, "PUT");
export const DELETE = (req: Request, ctx: Context) => proxy(req, ctx, "DELETE");

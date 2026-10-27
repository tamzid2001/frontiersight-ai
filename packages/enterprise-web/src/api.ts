/** One authenticated service for both website and programmatic adapters. */
import type { Firestore } from "@google-cloud/firestore";
import { FirestoreWorkspace, type StoragePolicy } from "./firestore.ts";
import { AccessError, requireFeature, requireWorkspaceAdmin, requireExpectedVersion, type Principal } from "./policy.ts";
import { enforceOrigin, errorResponse, jsonResponse, pageSize, readJson, strictFields } from "./http.ts";

export type WorkspaceConfiguration = Readonly<{
  siteId: string; name: string; stages: readonly string[]; origins: readonly string[];
}>;
export type WorkspaceDependencies = {
  database: () => Firestore;
  authenticate: (request: Request) => Promise<Principal>;
  auditSecret: string;
};

export function storagePolicy(principal: Principal, stages: number): StoragePolicy {
  const limits = {
    free: [25, 100], starter: [500, 2000], pro: [5000, 20_000], enterprise: [20_000, 100_000],
  } as const;
  const [maximumRecords, monthlyMutations] = limits[principal.plan ?? "free"];
  return { maximumRecords, monthlyMutations, stages };
}

export function createWorkspaceApi(config: WorkspaceConfiguration, dependencies: WorkspaceDependencies) {
  return async (request: Request): Promise<Response> => {
    try {
      enforceOrigin(request, config.origins);
      const principal = await dependencies.authenticate(request);
      const constrainedOrg = request.headers.get("x-workspace-organization");
      if (constrainedOrg !== null && constrainedOrg !== (principal.orgId ?? "personal")) {
        throw new AccessError(409, "session_workspace_changed");
      }
      const path = new URL(request.url).pathname;
      const programmatic = path.startsWith("/api/v1/");
      if (programmatic) requireFeature(principal, "api_access");
      const prefix = programmatic ? "/api/v1/workflows" : "/api/workspace";
      if (path !== prefix && !path.startsWith(prefix + "/")) throw new AccessError(404, "endpoint_not_found");
      const store = new FirestoreWorkspace(dependencies.database(), config.siteId, principal,
        storagePolicy(principal, config.stages.length), dependencies.auditSecret);
      await store.consumeRequest(principal.plan === "free" || !principal.plan ? 60 : 300);
      const suffix = path.slice(prefix.length), method = request.method;
      const url = new URL(request.url);
      const limit = () => pageSize(url.searchParams.get("limit"));
      const key = () => request.headers.get("idempotency-key") ?? "";
      if (method === "GET" && suffix === "/context") {
        return jsonResponse({ product: config.name, principal, stages: config.stages, usage: await store.usage() });
      }
      if (method === "GET" && suffix === "/audit") {
        requireFeature(principal, "audit_logs");
        return jsonResponse(await store.verifiedAuditPage(limit()));
      }
      if (method === "GET" && suffix === "/export") {
        requireFeature(principal, "export");
        const size = Math.min(limit(), 20);
        const rows = await store.list(size, url.searchParams.get("after") ?? undefined);
        const items = await Promise.all(rows.map(row => store.get(row.id)));
        return jsonResponse({ product: config.siteId, exportedAt: new Date().toISOString(), items,
          next: rows.length === size ? rows.at(-1)!.id : null }, 200,
          { "content-disposition": `attachment; filename="${config.siteId}-workflows.json"` });
      }
      if (method === "GET" && suffix === "") {
        const size = limit(), rows = await store.list(size, url.searchParams.get("after") ?? undefined);
        return jsonResponse({ items: rows, next: rows.length === size ? rows.at(-1)!.id : null });
      }
      if (method === "POST" && suffix === "") {
        const body = await readJson(request);
        strictFields(body, ["title", "payload"]);
        if (typeof body.title !== "string") throw new AccessError(400, "title_required");
        const row = await store.create({ title: body.title, payload: (body.payload === undefined ? {} : body.payload) as Record<string, unknown> }, key());
        return jsonResponse(row, row.replayed ? 200 : 201);
      }
      const match = /^\/([a-f0-9-]{36})$/.exec(suffix);
      if (match) {
        const id = match[1];
        if (method === "GET") return jsonResponse(await store.get(id));
        if (method === "PATCH" || method === "DELETE") {
          if (method === "DELETE") requireWorkspaceAdmin(principal);
          const body = await readJson(request);
          strictFields(body, method === "PATCH" ? ["expectedVersion", "stage"] : ["expectedVersion"]);
          const version = requireExpectedVersion(body.expectedVersion);
          return jsonResponse(method === "PATCH"
            ? await store.transition(id, version, body.stage as number, key())
            : await store.remove(id, version, key()));
        }
      }
      throw new AccessError(405, "method_or_endpoint_not_supported");
    } catch (error) { return errorResponse(error); }
  };
}

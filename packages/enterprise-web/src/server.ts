/** Lazy server adapter: configuration is evaluated at request time, not build.
 * The database connection may be reused. Identity is ALWAYS per request. */
import { clerkConfiguration, createBearerAuthenticator } from "./auth.ts";
import { createWorkspaceApi, type WorkspaceConfiguration } from "./api.ts";
import { createWorkspaceMcp } from "./mcp.ts";
import { firestoreClient } from "./firestore.ts";
import { errorResponse } from "./http.ts";
import { createSupportHandler } from "./support.ts";

export function workspaceServer(config: WorkspaceConfiguration, env: NodeJS.ProcessEnv = process.env) {
  let database: ReturnType<typeof firestoreClient> | undefined;
  let authenticate: ReturnType<typeof createBearerAuthenticator> | undefined;
  const dependencies = () => ({
    database: () => database ??= firestoreClient(env),
    authenticate: authenticate ??= createBearerAuthenticator(clerkConfiguration(env)),
    auditSecret: env.WORKSPACE_AUDIT_SECRET ?? "",
  });
  return {
    async close() { if (database) { await database.terminate(); database = undefined; } },
    async support(request: Request) {
      try { return await createSupportHandler(config, dependencies(), env)(request); }
      catch (error) { return errorResponse(error); }
    },
    async api(request: Request) {
      try { return await createWorkspaceApi(config, dependencies())(request); }
      catch (error) { return errorResponse(error); }
    },
    async mcp(request: Request) {
      try { return await createWorkspaceMcp(config, dependencies())(request); }
      catch (error) { return errorResponse(error); }
    },
  };
}

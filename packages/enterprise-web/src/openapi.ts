import type { WorkspaceConfiguration } from "./api.ts";

/** The implemented HTTP surface only. Planned Python APIs are not advertised
 * as deployed web endpoints. Clerk session tokens expire; API keys and OAuth
 * discovery require a separate, explicitly configured integration. */
export function workspaceOpenApi(config: WorkspaceConfiguration, origin: string) {
  if (new URL(origin).origin !== origin) throw new Error("canonical_origin_required");
  const ref = (name: string) => ({ $ref: "#/components/schemas/" + name });
  const response = (schema: unknown) => ({ description: "Success", content: { "application/json": { schema } } });
  const body = (schema: unknown) => ({ required: true, content: { "application/json": { schema } } });
  const paging = [{ name: "limit", in: "query", schema: { type: "integer", minimum: 1, maximum: 100, default: 50 } },
    { name: "after", in: "query", schema: { type: "string", format: "uuid" } }];
  const key = { name: "Idempotency-Key", in: "header", required: true, schema: { type: "string", pattern: "^[A-Za-z0-9_-]{16,128}$" } };
  const errors = Object.fromEntries([400, 401, 403, 404, 409, 413, 415, 429, 503].map(status => [status,
    { description: "Validation, authorization, conflict, quota or availability error", content: { "application/json": { schema: ref("Error") } } }]));
  const recordFields = { id: { type: "string", format: "uuid" }, title: { type: "string", maxLength: 160 },
    stage: { type: "integer", minimum: 0, maximum: config.stages.length - 1 }, version: { type: "integer", minimum: 1 },
    createdBy: { type: "string" }, createdAt: { type: "string", format: "date-time" }, updatedAt: { type: "string", format: "date-time" } };
  return {
    openapi: "3.1.0", info: { title: config.name + " workspace API", version: "1.0.0",
      description: "Clerk-authenticated, Firestore-backed records. Paid programmatic access is checked on every request in the active personal or organization workspace. Stage changes only record status; they do not execute domain actions." },
    servers: [{ url: origin }], security: [{ ClerkSession: [] }],
    paths: {
      "/api/v1/models": { get: { operationId: "listApplicableModels", description: "Reviewed model capabilities applicable to this product. Free development endpoints have provider trial terms and rate limits; no model is invoked.", responses: { 200: response({ type: "object" }), ...errors } } },
      "/api/v1/models/prepare": { post: { operationId: "prepareModelRequest", description: "Validate a bounded reasoning or tabular regression payload and return a provider request with a placeholder key. This operation never invokes NVIDIA or uploads workspace data. Protein jobs require a dedicated scientific adapter and are rejected here.",
        requestBody: body({ type: "object", required: ["model"], additionalProperties: false, properties: { model: {type:"string"}, prompt:{type:"string",minLength:1,maxLength:4000}, table:{type:"object",description:"columns [{name,dtype: float64|string}], target name, context rows including numeric target last (2–200), predict rows excluding target (1–32). 1–24 feature columns, finite numbers, strings <=256 characters or missing null features."}} }),
        responses: { 200: response({ type:"object",properties:{status:{const:"prepared_not_executed"},url:{type:"string"},body:{type:"object"}} }), ...errors } } },
      "/api/v1/workflows": {
        get: { operationId: "listWorkflows", parameters: paging, responses: { 200: response(ref("Page")), ...errors } },
        post: { operationId: "createWorkflow", parameters: [key], requestBody: body(ref("CreateRecord")),
          responses: { 201: response(ref("Record")), 200: response(ref("Record")), ...errors } },
      },
      "/api/v1/workflows/{id}": { parameters: [{ name: "id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        get: { operationId: "getWorkflow", responses: { 200: response(ref("Record")), ...errors } },
        patch: { operationId: "transitionWorkflow", parameters: [key], requestBody: body({ type: "object", additionalProperties: false,
          required: ["expectedVersion", "stage"], properties: { expectedVersion: { type: "integer", minimum: 1 }, stage: recordFields.stage } }), responses: { 200: response(ref("Record")), ...errors } },
        delete: { operationId: "deleteWorkflow", description: "Personal owner or organization administrator only. Deletes content, retaining content-free audit metadata.", parameters: [key],
          requestBody: body({ type: "object", additionalProperties: false, required: ["expectedVersion"], properties: { expectedVersion: { type: "integer", minimum: 1 } } }),
          responses: { 200: response({ type: "object", properties: { id: recordFields.id, deleted: { const: true }, version: recordFields.version } }), ...errors } },
      },
      "/api/v1/workflows/context": { get: { operationId: "workspaceContext", responses: { 200: response({ type: "object" }), ...errors } } },
      "/api/v1/workflows/export": { get: { operationId: "exportWorkflows", description: "Requires export feature. Paginated full records; maximum 10 per page. Follow next cursor.", parameters: paging,
        responses: { 200: response({ type: "object", properties: { items: { type: "array", items: ref("Record") }, next: { type: ["string", "null"] } } }), ...errors } } },
      "/api/v1/workflows/audit": { get: { operationId: "verifyAudit", description: "Requires audit_logs. Verifies event signatures and links in the most recent bounded window; not a privileged rollback proof.", parameters: [paging[0]],
        responses: { 200: response({ type: "object" }), ...errors } } },
    },
    components: { securitySchemes: { ClerkSession: { type: "http", scheme: "bearer", bearerFormat: "Clerk session JWT" } }, schemas: {
      Summary: { type: "object", required: Object.keys(recordFields), properties: recordFields },
      Record: { type: "object", required: [...Object.keys(recordFields), "payload"], properties: { ...recordFields, payload: { type: "object" }, replayed: { type: "boolean" } } },
      CreateRecord: { type: "object", additionalProperties: false, required: ["title"], properties: { title: { type: "string", minLength: 1, maxLength: 160 }, payload: { type: "object", default: {} } } },
      Page: { type: "object", properties: { items: { type: "array", items: ref("Summary"), maxItems: 100 }, next: { type: ["string", "null"] } } },
      Error: { type: "object", properties: { error: { type: "object", required: ["code", "requestId"], properties: { code: { type: "string" }, requestId: { type: "string", format: "uuid" } } } } },
    } },
  };
}

"use client";
import { useAuth, SignInButton, OrganizationProfile, OrganizationSwitcher, UserProfile } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";
import type { WorkspaceSummary } from "./firestore.ts";

type Context = { product: string; stages: string[]; principal: {
  orgId: string | null; orgRole: string | null; plan: string; features: string[];
}; usage: { mutations: number; records: number; maximumRecords: number; monthlyMutations: number; period: string } };

const MESSAGES: Record<string, string> = {
  feature_not_in_plan: "This capability needs a paid plan for the active workspace.",
  organization_admin_required: "An organization administrator must perform this action.",
  record_version_conflict: "Someone changed this record. Refresh and review it before retrying.",
  session_workspace_changed: "Your active workspace changed. Refresh this page before continuing.",
  monthly_mutation_limit: "This workspace has reached its monthly change allowance.",
  workspace_record_limit: "This workspace has reached its saved-record allowance.",
  request_rate_limit: "Too many requests. Wait a minute before retrying.",
  authentication_required: "Sign in again to continue.",
  firestore_project_not_configured: "Saved workspaces are awaiting server configuration. No record was saved.",
  firestore_credentials_not_configured: "Saved workspaces are awaiting server configuration. No record was saved.",
  authentication_not_configured: "Authentication is awaiting server configuration.",
};

export function WorkspacePanel({ name, stages }: { name: string; stages: readonly string[] }) {
  const { isLoaded, isSignedIn, orgId, userId } = useAuth();
  if (!isLoaded) return <p role="status">Loading your session…</p>;
  if (!isSignedIn) return <section className="card"><h2>Your saved workspace</h2><p>Sign in to save and share records securely.</p><SignInButton><button className="btn primary">Sign in</button></SignInButton></section>;
  // Changing this key discards all previous tenant data, forms and in-flight UI.
  return <WorkspaceSession key={userId + ":" + (orgId ?? "personal")} name={name} stages={stages} />;
}

function WorkspaceSession({ name, stages }: { name: string; stages: readonly string[] }) {
  const { getToken, orgId } = useAuth();
  const [rows, setRows] = useState<WorkspaceSummary[]>([]), [context, setContext] = useState<Context | null>(null);
  const [title, setTitle] = useState(""), [payload, setPayload] = useState("{}");
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [next, setNext] = useState<string | null>(null);
  const [detail, setDetail] = useState<string>(""), [audit, setAudit] = useState<string>("");
  const controllers = useRef(new Set<AbortController>());
  const mutationKeys = useRef(new Map<string, string>());
  const api = useCallback(async (path: string, method = "GET", body?: unknown) => {
    const token = await getToken();
    if (!token) throw new Error("Sign in again to continue.");
    const controller = new AbortController(); controllers.current.add(controller);
    const timeout = setTimeout(() => controller.abort(), 20_000);
    const signature = method + path + JSON.stringify(body);
    let key = mutationKeys.current.get(signature);
    if (method !== "GET" && !key) { key = crypto.randomUUID(); mutationKeys.current.set(signature, key); }
    try {
      const response = await fetch("/api/workspace" + path, { method, signal: controller.signal, cache: "no-store",
        headers: { authorization: "Bearer " + token, "x-workspace-organization": orgId ?? "personal",
          ...(body === undefined ? {} : { "content-type": "application/json", "idempotency-key": key! }) },
        body: body === undefined ? undefined : JSON.stringify(body) });
      const value = await response.json();
      if (!response.ok) throw new Error(MESSAGES[value.error?.code] ?? "The request could not be completed. Try again; if it persists, contact support with request " + (value.error?.requestId ?? "unavailable") + ".");
      return value;
    } finally { clearTimeout(timeout); controllers.current.delete(controller); }
  }, [getToken, orgId]);

  const refresh = useCallback(async () => {
    const [data, info] = await Promise.all([api("?limit=25"), api("/context")]);
    setRows(data.items); setNext(data.next); setContext(info);
  }, [api]);
  useEffect(() => {
    let active = true;
    refresh().catch(e => { if (active) setError(e instanceof Error ? e.message : "Workspace unavailable."); });
    const current = controllers.current;
    return () => { active = false; current.forEach(controller => controller.abort()); };
  }, [refresh]);

  async function action(run: () => Promise<void>) {
    setBusy(true); setError("");
    try { await run(); } catch (e) { setError(e instanceof Error ? e.message : "Request failed."); }
    finally { setBusy(false); }
  }
  async function create(event: React.FormEvent) {
    event.preventDefault();
    await action(async () => {
      if (new TextEncoder().encode(payload).length > 32 * 1024) throw new Error("Keep record data below 32 KB in this form.");
      let data; try { data = JSON.parse(payload); } catch { throw new Error("Record data must be valid JSON."); }
      await api("", "POST", { title, payload: data });
      setTitle(""); setPayload("{}"); mutationKeys.current.clear(); await refresh();
    });
  }
  const can = (feature: string) => context?.principal.features.includes(feature);
  const admin = !context?.principal.orgId || context.principal.orgRole === "org:admin";
  return <section aria-label={name}>
    <div className="workspace-toolbar"><OrganizationSwitcher hidePersonal={false} />
      <button className="btn" disabled={busy} onClick={() => action(refresh)}>Refresh</button>
      <a href="/settings">Workspace settings</a></div>
    <p>{context?.principal.orgId ? "Organization" : "Personal"} workspace · {context?.principal.plan ?? "Loading plan"}</p>
    {context && <p className="usage">{context.usage.records} / {context.usage.maximumRecords} saved records · {context.usage.mutations} / {context.usage.monthlyMutations} changes in {context.usage.period}</p>}
    <p role="alert" className="bad">{error}</p>
    <form onSubmit={create} className="card workspace-form">
      <label htmlFor="record-title">Record title</label>
      <input id="record-title" value={title} onChange={event => setTitle(event.target.value)} required maxLength={160} />
      <label htmlFor="record-payload">Record data (JSON object)</label>
      <textarea id="record-payload" value={payload} onChange={event => setPayload(event.target.value)} rows={4} spellCheck={false} />
      <p>Do not include credentials, access tokens or personal data you do not have permission to store.</p>
      <button className="btn primary" disabled={busy} type="submit">{busy ? "Working…" : "Save record"}</button>
    </form>
    <div className="workspace-toolbar">
      {can("export") ? <button className="btn" disabled={busy} onClick={() => action(async () => {
        const page = await api("/export?limit=10");
        const url = URL.createObjectURL(new Blob([JSON.stringify(page, null, 2)], { type: "application/json" }));
        const link = document.createElement("a"); link.href = url; link.download = "workspace-export-page.json";
        document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        if (page.next) setDetail("Export contains the first 10 records. Use the documented export cursor to retrieve subsequent pages.");
      })}>Export first page</button> : <a href="/pricing">Plans with export</a>}
      {can("audit_logs") && <button className="btn" disabled={busy} onClick={() => action(async () => setAudit(JSON.stringify(await api("/audit?limit=50"), null, 2)))}>Verify recent audit</button>}
    </div>
    {rows.length === 0 && context && <p>No saved records in this workspace. Create your first one above.</p>}
    {rows.map(row => <article className="card" key={row.id}>
      <h3>{row.title}</h3><p>{stages[row.stage]} · version {row.version} · updated <time dateTime={row.updatedAt}>{new Date(row.updatedAt).toLocaleString()}</time></p>
      <div className="workspace-toolbar">
        <button className="btn" disabled={busy} onClick={() => action(async () => setDetail(JSON.stringify(await api("/" + row.id), null, 2)))}>View data</button>
        <label>Stage <select value={row.stage} disabled={busy} onChange={event => {
          const stage = Number(event.target.value);
          action(async () => { await api("/" + row.id, "PATCH", { expectedVersion: row.version, stage }); await refresh(); });
        }}>{stages.map((stage, index) => <option key={stage} value={index}>{stage}</option>)}</select></label>
        {admin && <button className="btn" disabled={busy} onClick={() => {
          if (confirm("Delete this record? Its content will be removed; the content-free audit event remains.")) {
            action(async () => { await api("/" + row.id, "DELETE", { expectedVersion: row.version }); setDetail(""); await refresh(); });
          }
        }}>Delete</button>}
      </div>
    </article>)}
    {next && <button className="btn" disabled={busy} onClick={() => action(async () => {
      const page = await api("?limit=25&after=" + next);
      setRows(current => [...current, ...page.items.filter((row: WorkspaceSummary) => !current.some(old => old.id === row.id))]); setNext(page.next);
    })}>Show more records</button>}
    {detail && <section><h2>Record data</h2><button className="btn" onClick={() => setDetail("")}>Close data</button><pre>{detail}</pre></section>}
    {audit && <section><h2>Recent audit verification</h2><p>Signatures and links are checked for this window. This does not prove protection against a privileged database rollback.</p><button className="btn" onClick={() => setAudit("")}>Close audit</button><pre>{audit}</pre></section>}
  </section>;
}

export function OrganizationSettings() {
  const { isLoaded, isSignedIn, orgId } = useAuth();
  if (!isLoaded) return <p role="status">Loading settings…</p>;
  if (!isSignedIn) return <SignInButton><button className="btn primary">Sign in to manage settings</button></SignInButton>;
  return <section><OrganizationSwitcher hidePersonal={false} />
    <p>Select your personal account or an organization. Organization membership and roles are managed by Clerk; saved records follow your active workspace.</p>
    {orgId ? <OrganizationProfile routing="hash" /> : <UserProfile routing="hash" />}
  </section>;
}

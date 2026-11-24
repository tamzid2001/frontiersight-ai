/** File selection validation for local, deterministic workbench analysis. */
export function uploadName(name: string, allowed: ReadonlySet<string>): string {
  const basename = name.split(/[\\/]/).at(-1) ?? "";
  const dot = basename.lastIndexOf(".");
  const extension = basename.slice(dot).toLowerCase();
  if (dot < 1 || !allowed.has(extension)) throw new Error("Choose an approved file type.");
  const stem = basename.slice(0, dot).replace(/[^A-Za-z0-9._-]/g, "_").replace(/^[._-]+/, "").slice(0, 95);
  return (stem || "dataset") + extension;
}

export async function readJsonUpload(file: File, maxBytes: number): Promise<{ name: string; text: string }> {
  const name = uploadName(file.name, new Set([".json"]));
  if (file.size < 1 || file.size > maxBytes) {
    throw new Error(`Choose a nonempty JSON file up to ${Math.floor(maxBytes / 1024)} KiB.`);
  }
  return { name, text: new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()) };
}

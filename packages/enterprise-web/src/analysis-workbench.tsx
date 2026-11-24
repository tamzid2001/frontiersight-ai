"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { comparePixels, MAX_INPUT_BYTES, parseInput, runAnalysis, type AnalysisReport } from "./analysis.ts";

import { readJsonUpload, uploadName } from "./upload.ts";

const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);

type Guide = { title: string; description: string; example: Record<string, unknown>; schema: unknown };
type SourceGuide = { label: string; placeholder: string; button: string };

async function compareFiles(baseline: File, candidate: File, tolerance: number) {
  const bitmaps: ImageBitmap[] = [];
  try {
    for (const file of [baseline, candidate]) {
      uploadName(file.name, IMAGE_EXTENSIONS);
      if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 15 * 1024 * 1024) {
        throw new Error("Choose a PNG, JPEG or WebP file up to 15 MiB for each image.");
      }
      const bitmap = await createImageBitmap(file);
      bitmaps.push(bitmap);
      if (bitmap.width * bitmap.height > 16_000_000 || Math.max(bitmap.width, bitmap.height) > 8192) {
        throw new Error("Use images up to 16 megapixels and 8192 pixels per side.");
      }
    }
    const { width, height } = bitmaps[0];
    if (bitmaps[1].width !== width || bitmaps[1].height !== height) {
      throw new Error(`Image sizes differ (${width}×${height} and ${bitmaps[1].width}×${bitmaps[1].height}). Use matching dimensions.`);
    }
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("This browser could not initialize image processing.");
    const pixels = bitmaps.map(bitmap => {
      context.clearRect(0, 0, width, height);
      context.drawImage(bitmap, 0, 0);
      return new Uint8Array(context.getImageData(0, 0, width, height).data.buffer);
    });
    return comparePixels(pixels[0], pixels[1], width, height, tolerance);
  } finally {
    for (const bitmap of bitmaps) bitmap.close();
  }
}

const printable = (value: string | number | null) => value ?? "—";
const message = (error: unknown) => error instanceof Error ? error.message : "The operation failed.";

export function AnalysisWorkbench({ siteId, guide, sourceGuide }: { siteId: string; guide: Guide; sourceGuide?: SourceGuide }) {
  const prefix = useId();
  const results = useRef<HTMLHeadingElement>(null);
  const errorBox = useRef<HTMLParagraphElement>(null);
  const [text, setText] = useState("");
  const [inputSource, setInputSource] = useState<AnalysisReport["inputSource"]>("user_supplied");
  const [source, setSource] = useState<string>();
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<AnalysisReport>();
  const [images, setImages] = useState(siteId === "visual-regression-evaluator");

  function changeText(value: string, nextSource: AnalysisReport["inputSource"], url?: string) {
    setText(value); setInputSource(nextSource); setSource(url);
    setReport(undefined); setError(""); setStatus("");
  }
  function showError(cause: unknown) {
    setError(message(cause));
    requestAnimationFrame(() => errorBox.current?.focus());
  }

  async function importSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(""); setStatus("Retrieving public data…");
    try {
      let existing = {};
      if (siteId === "atmospheric-calibrated-forecast-platform" && text.trim()) {
        const parsed = parseInput(text);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Enter a forecast JSON object first.");
        if ("unit" in parsed && parsed.unit !== "°C") throw new Error("Enter forecasts in °C before importing station observations.");
        existing = parsed;
      }
      const identifier = String(new FormData(event.currentTarget).get("source") ?? "").trim();
      const response = await fetch(`/api/analysis/source?id=${encodeURIComponent(identifier)}`, { signal: AbortSignal.timeout(12000) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "The source could not be loaded.");
      changeText(JSON.stringify({ ...existing, ...result.data }, null, 2), "public_api", result.source);
      setStatus("Public records imported. Review the input and run the analysis.");
    } catch (cause) { setStatus(""); showError(cause); }
    finally { setBusy(false); }
  }

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(""); setStatus(""); setReport(undefined); setBusy(true);
    try {
      let next: AnalysisReport;
      if (images) {
        const form = new FormData(event.currentTarget);
        const before = form.get("baseline"), after = form.get("candidate");
        const tolerance = Number(form.get("tolerance"));
        if (!(before instanceof File) || !(after instanceof File) || !before.size || !after.size) {
          throw new Error("Choose both screenshot files.");
        }
        const findings = await compareFiles(before, after, tolerance);
        next = { schemaVersion: "1.0", product: siteId, analysis: guide.title, inputSource: "user_supplied", ...findings };
      } else {
        next = runAnalysis(siteId, parseInput(text), inputSource, source);
      }
      setReport(next);
      setStatus("Analysis complete.");
      requestAnimationFrame(() => results.current?.focus());
    } catch (cause) { showError(cause); }
    finally { setBusy(false); }
  }

  function download() {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2) + "\n"], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url; link.download = `${siteId}-report.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const rows = report?.rows ?? [];
  const columns = rows.length ? Object.keys(rows[0]) : [];
  const sourceLabel = report?.inputSource === "example" ? "Illustrative example" :
    report?.inputSource === "public_api" ? "Includes public API data" : "Your input";

  return (
    <section className="analysis-workbench" aria-label="Data analysis workbench">
      {sourceGuide && <form className="analysis-source card" onSubmit={importSource} aria-labelledby={prefix + "-sources"}>
        <h2 id={prefix + "-sources"}>Import public data</h2>
        <label htmlFor={prefix + "-source"}>{sourceGuide.label}</label>
        <div className="analysis-buttons">
          <input id={prefix + "-source"} name="source" autoCapitalize="off" spellCheck={false}
            placeholder={sourceGuide.placeholder} maxLength={140} required />
          <button type="submit" className="btn" disabled={busy}>{sourceGuide.button}</button>
        </div>
        <p className="widget-note">{siteId === "atmospheric-calibrated-forecast-platform"
          ? "Enter your forecasts in °C first. Importing replaces the observations with the station’s recent temperature readings."
          : "Uses the latest 50 completed public workflow runs. Groups share a workflow ID, commit, event and branch."}</p>
      </form>}
      <form className="card analysis-form" onSubmit={analyze} aria-labelledby={prefix + "-input-title"}>
        <h2 id={prefix + "-input-title"}>Analysis input</h2>
        <p className="widget-note">Files and pasted data are processed in this browser.</p>
        {siteId === "visual-regression-evaluator" &&
          <button type="button" className="btn" disabled={busy} onClick={() => {
            setImages(!images); setReport(undefined); setError(""); setStatus("");
          }}>{images ? "Switch to JSON input" : "Switch to image files"}</button>}
        {images ? (
          <fieldset className="analysis-image-inputs">
            <legend>Screenshot files</legend>
            <label htmlFor={prefix + "-before"}>Baseline screenshot</label>
            <input id={prefix + "-before"} name="baseline" type="file" accept="image/png,image/jpeg,image/webp" required
              onChange={() => { setReport(undefined); setStatus(""); setError(""); }} />
            <label htmlFor={prefix + "-after"}>Candidate screenshot</label>
            <input id={prefix + "-after"} name="candidate" type="file" accept="image/png,image/jpeg,image/webp" required
              onChange={() => { setReport(undefined); setStatus(""); setError(""); }} />
            <label htmlFor={prefix + "-tolerance"}>Channel tolerance (0–255)</label>
            <input id={prefix + "-tolerance"} name="tolerance" type="number" min={0} max={255} step={1} defaultValue={0} required
              onChange={() => { setReport(undefined); setStatus(""); setError(""); }} />
          </fieldset>
        ) : (
          <>
            <div className="analysis-file">
              <label htmlFor={prefix + "-file"}>Import a JSON file (optional)</label>
              <input id={prefix + "-file"} name="file" type="file" accept=".json,application/json" disabled={busy}
                onChange={async event => {
                  const file = event.currentTarget.files?.[0];
                  event.currentTarget.value = "";
                  if (!file) return;
                  setBusy(true);
                  try {
                    const uploaded = await readJsonUpload(file, MAX_INPUT_BYTES);
                    changeText(uploaded.text, "user_supplied");
                    setStatus(uploaded.name + " loaded. Run the analysis to see the results.");
                  } catch (cause) { showError(cause); }
                  finally { setBusy(false); }
                }} />
            </div>
            <label htmlFor={prefix + "-json"}>JSON data (required)</label>
            <textarea id={prefix + "-json"} name="analysis" value={text} rows={12} required spellCheck={false}
              aria-describedby={prefix + "-json-hint"} disabled={busy} maxLength={MAX_INPUT_BYTES}
              onChange={event => changeText(event.target.value, "user_supplied")} />
            <span id={prefix + "-json-hint"} className="widget-note">Paste data or load the example to see the format. Limit 512 KiB.</span>
            <details><summary>Input schema</summary><pre>{JSON.stringify(guide.schema, null, 2)}</pre></details>
          </>
        )}
        <div className="analysis-buttons">
          <button type="submit" className="cta" disabled={busy}>Run analysis</button>
          {!images && <button type="button" className="btn" disabled={busy}
            onClick={() => changeText(JSON.stringify(guide.example, null, 2), "example")}>Load example</button>}
        </div>
        <p className="analysis-status" role="status">{status}</p>
        <p className={error ? "analysis-error" : undefined} role="alert" aria-live="assertive" tabIndex={-1} ref={errorBox}>{error}</p>
      </form>
      {report && <section className="card analysis-results" aria-labelledby={prefix + "-results"}>
        <div className="analysis-result-heading">
          <div><h2 id={prefix + "-results"} tabIndex={-1} ref={results}>Results</h2>
            <p>{sourceLabel}{report.source && <> · <a href={report.source} target="_blank" rel="noreferrer">View source</a></>}</p></div>
          <button type="button" className="btn" onClick={download}>Download report</button>
        </div>
        <dl className="analysis-metrics">{Object.entries(report.metrics).map(([label, value]) =>
          <div key={label}><dt>{label}</dt><dd>{printable(value)}</dd></div>)}</dl>
        {rows.length > 0 && <div className="analysis-table" tabIndex={0} role="region" aria-label="Detailed results">
          <table aria-label="Detailed results data"><thead><tr>{columns.map(column => <th key={column} scope="col">{column}</th>)}</tr></thead>
            <tbody>{rows.slice(0, 200).map((row, index) => <tr key={index}>
              {columns.map(column => <td key={column}>{printable(row[column])}</td>)}
            </tr>)}</tbody></table>
        </div>}
        {rows.length > 200 && <p>Showing 200 of {rows.length} rows. Download the report for all rows.</p>}
      </section>}
    </section>
  );
}

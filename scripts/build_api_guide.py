"""Build the served HTML integration guide from the checked-in Markdown source."""
from pathlib import Path
import markdown
root=Path(__file__).resolve().parents[1]
body=markdown.markdown((root/'docs/WORKBENCH_API.md').read_text(),extensions=['tables','fenced_code'])
page='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scene, Object, Media API &amp; MCP | FrontierSight AI</title>
<meta name="description" content="Connect agents to FrontierSight AI: authenticated scene and object libraries, path planning, predictions, media, frames and MCP tools.">
<link rel="canonical" href="https://frontiersight-ai.vercel.app/api-guide.html"><link rel="icon" href="/favicon-32.png"><link rel="stylesheet" href="/app.css">
<style>body{display:block;margin:0;padding:24px}main{max-width:1080px;margin:auto}header{max-width:1080px;margin:0 auto 24px;display:flex;gap:20px;align-items:center;flex-wrap:wrap}pre{overflow:auto;padding:16px;border:1px solid #526174;border-radius:12px}code{overflow-wrap:anywhere}table{display:block;max-width:100%;overflow:auto;border-collapse:collapse}th,td{padding:12px;border:1px solid #526174;text-align:left;vertical-align:top}p,li{line-height:1.7}h1{font-size:clamp(2rem,5vw,3rem)}a{color:#56bace}h2{margin-top:2.2rem}header a{font-weight:600}</style>
</head><body><header><a href="/">FrontierSight AI</a><a href="/create">Create Lab</a><a href="/pricing">Pricing</a><a href="/settings">Agent keys</a><a href="/openapi.json">OpenAPI JSON</a></header><main>'''+body+'''</main><footer><a href="mailto:hello@quantura.studio">Contact support</a> · <a href="https://quantura.studio">Quantura</a></footer></body></html>'''
(root/'apps/web/api-guide.html').write_text(page)

# FrontierSight MCP server

FrontierSight exposes its **deterministic** capabilities as an MCP
(Model Context Protocol) server, so agents (Claude Code, Cursor, VS Code,
your own) can analyse scenes and run counterfactuals with reproducible
numbers instead of vibes. Model-backed tools are deliberately excluded:
an MCP call can never spend the host's Meta API credits, and evidence
export still requires the human approval gate in the UI.

## Connect (under two minutes)

**Hosted (HTTP)** — Claude Code:

```bash
claude mcp add --transport http frontiersight https://frontiersight-ai.vercel.app/api/mcp
```

**Cursor / VS Code** (`mcp.json`):

```json
{"mcpServers": {"frontiersight": {"url": "https://frontiersight-ai.vercel.app/api/mcp"}}}
```

**Offline / local (stdio)** — from a clone of this repo:

```bash
claude mcp add frontiersight -- python3 scripts/mcp_stdio.py
```

## Tools

| Tool | What it does |
|---|---|
| `resize_scene` / `reposition_scene` | Resize metre-space floors/paths or move an object and its path; pure transforms with explicit bounds and no persistence. [Contract and examples](SCENE_EDITING_API.md) |
| `server_info` | Identity, protocol, honesty labels |
| `list_scenarios` / `get_scenario` | Built-in scenarios; observations + separately-held ground truth |
| `analyse_scenario` | Per-pair measured (along-trajectory) + predicted (CPA/TTC) proximity — no LLM |
| `analyse_tracks` | Same analysis for your tracks; pixel space never fakes metres |
| `simulate_counterfactual` | Path-following braking simulation (agent slows along its own curved path); anonymous Monte-Carlo cap 200; accepts a complete edited `scene`, agent and optional target |
| `sample_paths` | Complete `scene` → floor, object definitions, digest and timestamped tracks. Legacy objects-only input remains supported. |
| `validate_scene` | Create Lab scene schema validation — rejects, never repairs |

## Protocol notes

`POST /api/mcp` speaks JSON-RPC 2.0 (`initialize`, `ping`, `tools/list`,
`tools/call`); notifications are acknowledged with `202`. Engine errors
return as MCP tool errors (`isError`) carrying the engine's message.
`GET /api/mcp` returns the human-readable catalog. Rate limits and the
12 MB ingest bound from the REST API apply unchanged.

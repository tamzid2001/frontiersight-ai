"""FrontierSight MCP server over stdio — same handlers as POST /api/mcp,
fully offline against a local clone (no API key, no network).

Usage (Claude Code):  claude mcp add frontiersight -- python3 scripts/mcp_stdio.py
Protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.api.mcp import handle_jsonrpc

def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: body = json.loads(line)
        except Exception: continue
        resp = handle_jsonrpc(body)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n"); sys.stdout.flush()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

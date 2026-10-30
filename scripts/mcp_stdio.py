"""FrontierSight MCP server over stdio — same handlers as POST /api/mcp,
offline against a local clone by default (no API key, no network).
Use --url with a private FRONTIERSIGHT_API_KEY for the full hosted workbench.

Usage (Claude Code):  claude mcp add frontiersight -- python3 scripts/mcp_stdio.py
Protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout.
"""
import json, sys, argparse, os, urllib.request, urllib.error
from urllib.parse import urlparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.api.mcp import handle_jsonrpc

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',help='Optional authenticated HTTPS MCP endpoint; omit for offline analysis')
    parser.add_argument('--token-env',default='FRONTIERSIGHT_API_KEY')
    args=parser.parse_args()
    token=os.environ.get(args.token_env,'')
    if args.url:
        parsed=urlparse(args.url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or not token:
            parser.error('remote mode requires a clean HTTPS endpoint and a token in the named environment variable')
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: body = json.loads(line)
        except Exception: continue
        if args.url:
            request=urllib.request.Request(args.url,data=json.dumps(body).encode(),headers={
                'Content-Type':'application/json','Accept':'application/json, text/event-stream',
                'Authorization':'Bearer '+token,'MCP-Protocol-Version':'2025-11-25'})
            try:
                with urllib.request.urlopen(request,timeout=40) as response:
                    data=response.read(4_500_000)
                    resp=json.loads(data) if data else None
            except (urllib.error.URLError,ValueError):
                resp={'jsonrpc':'2.0','id':body.get('id') if isinstance(body,dict) else None,
                      'error':{'code':-32000,'message':'Remote MCP request failed; no automatic retry was made.'}}
        else:
            resp = handle_jsonrpc(body)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n"); sys.stdout.flush()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

# Security

- `MODEL_API_KEY` is server-side only, never serialised to clients, never logged.
- Uploads: media is processed as data URLs in-memory in this demo; size/type
  validation belongs at the ingest boundary before any model call (concept
  prompts are single-noun-phrase validated). No shell execution from prompts.
- Evidence manifests are SHA-256 hash-bound; reports state assumptions and
  label model-derived vs deterministic content.
- Report vulnerabilities privately to the repo owner via GitHub.

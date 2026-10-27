# Contributing

Run `python3 -m pytest -q` and `PYTHONPATH=. python3 -m services.api.server --smoke` before opening a PR.
Keep deterministic code in `engine/` free of model calls; keep model code behind
`integrations/meta/` with schema validation; never relabel fixture output as live.

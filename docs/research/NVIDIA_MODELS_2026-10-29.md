# NVIDIA model catalog review — October 29, 2026

All five pages of https://build.nvidia.com/models were retrieved: 105 model cards,
45 marked Free Endpoint. The adjacent JSONL records names, URLs, page, review date
and availability labels; it does not reproduce model-card descriptions or weights.
Availability labels describe the catalog snapshot, not an uptime or pricing SLA.
NVIDIA's free APIs are for development, with trial terms and shared rate limits.
Model licenses and hosted-service terms are separate. Recheck both before use.

## Implemented web contracts

`@quantura/enterprise-web` 0.1.2 adds product-scoped capability discovery and
bounded request preparation through the authenticated API and MCP. Preparation
never calls NVIDIA, uploads saved records, runs a GPU or inserts real credentials.
The output explicitly says `prepared_not_executed`. A trusted client must review
and submit the request independently under its own provider authorization.

- Nemotron Bolt: https://build.nvidia.com/nvidia/nemotron-3.5-bolt-e4b — documented
  chat endpoint, model ID, token bound and thinking flag. Advisory analysis only.
- Kumo Tabular: https://docs.api.nvidia.com/nim/reference/nvidia-kumo-tabular-statuspolling
  — a separate structured-data API, not chat completions. Numeric labels are
  excluded from query rows; row IDs are disjoint, shapes/dtypes are validated.
  Preparation supports a bounded arrays-format regression subset, not Arrow,
  relational tables, sessions or a claim of calibrated forecasting performance.
- GLM fallback: https://build.nvidia.com/z-ai/glm-5-3-flash — the API model ID is
  `z-ai/glm-5.3-flash`, which differs from the catalog URL. Support may use it only
  after explicit operator verification of current free endpoint access.

## Scientific workflows kept separate

RFD4-Proteina: https://docs.api.nvidia.com/nim/reference/ipd-rfd4-proteina-infer
requires structured design conditions and a scientific job adapter. The chemistry
website links to the provider interface and marks that adapter unimplemented.
Protein design does not demonstrate DNA computation, chemical kinetics or wet-lab
validity. The catalog and API documentation display differing model-license
labels; consult the governing terms rather than treating the label as legal advice.

Ising Calibration: https://docs.api.nvidia.com/nim/reference/nvidia-ising-calibration-1-5-31b
is a calibration-plot VLM. None of the 18 current web workspaces has a quantum
calibration data path, so the model is recorded but not injected into those apps.
It does not execute quantum circuits or control a QPU.

OpenFold3, Evo2 and TRELLIS were listed as downloadable, without a free-endpoint
badge in this catalog. No free hosted API or local hardware execution is claimed.
Cosmos3 Nano Reasoner is relevant to a future FrontierSight physical-scene adapter,
but no replacement of the existing Meta scene-generation pipeline is made here.

## Validation boundaries

Software tests exercise exact local serialization, limits, authorization and MCP
transport with a real Firestore emulator. They do not measure prediction quality,
protein validity, provider acceptance, GPU kernels or production availability.

# Architecture

```
apps/web (workbench UI) ──► services/api (stdlib HTTP, Vercel serverless)
                               ├─► agents/workflow   9 bounded stages, idempotency, approval gate
                               ├─► engine/           geometry · kinematics/TTC · tracking · uncertainty
                               │                     counterfactual sim · analytical validation · scenarios
                               └─► integrations/meta Muse Spark · SAM 3.1 (+ wire parser) · Muse Image
fixtures/  synthetic scenarios, ground truth held separate from observations
```

Trust boundaries: the browser never sees `MODEL_API_KEY`; model output is
schema-validated and labelled MODEL_DERIVED; physical claims come only from
`engine/`; export requires the human_review stage. Data flow and provenance
labels are described in README.md and docs/HACKATHON_SUBMISSION.md.

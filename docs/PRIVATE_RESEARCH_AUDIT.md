# Private research audit — concepts only, no private code

Method: API-level inventory of the author's private repositories (capabilities,
stated limitations, test counts) on 2026-10-27. **No private source, fixtures,
or documentation were copied into this repository.** FrontierSight re-implements
selected *concepts* from scratch; this document discloses capabilities at a
high level only, which is also why licence status matters below.

| Private reference (author's own) | Capability actually implemented (repo-stated) | Concept independently rebuilt here | Stated limitations |
|---|---|---|---|
| simulated-warehouse-near-miss | TTC classification (separation ÷ closing speed), constant-velocity closest approach over finite-radius objects, checkpointed analysis | CPA + TTC engine (`engine/geometry.py`, `engine/kinematics.py`) with exact quadratic TTC | Simulated only; supplied calibrated annotations; not a safety certification |
| video-world-state-transition-tester | Kinematic transition consistency, teleport/discontinuity diagnostics | Track continuity diagnostics (jumps, gaps, implausible acceleration) in `engine/tracking.py` | Synthetic trajectories only |
| dynamic-scene-constraint-solver | Pre-synthesis collision/kinematic constraint solving, CPU reference | Constraint/plausibility rejection (invalid inputs raise, never fabricate) | GPU/QPU mocked; robot unavailable |
| robot-occlusion-recovery-bench | Track continuity through injected occlusions; occlusion ≠ disappearance | Occlusion windows as *missing evidence*, identity-switch diagnostics | Synthetic fixtures only |
| cosmos-prompt-physics-checker | Structured motion-constraint contradiction checks with required-speed diagnostics | Schema-validated model output (reject, don't repair) in `integrations/meta/spark.py` | Synthetic prompt linting only |
| embodied-action-sequence-evaluator | Action-sequence scoring vs state invariants; CPU physics evidence | Analytical reference-case gate (`engine/validation.py`) | CPU-evidence only; no real robot |
| agent-human-approval-ledger | Human authorisation gates, risk tiering, append-style ledger | Human-review stage gating evidence export (`agents/workflow.py`) | Demo local; production credential-gated |
| agent-evaluation-orchestrator | Reproducible evaluations with independent validators | Independent Verification Controller stage + hash-bound artifacts | Test doubles labelled; no live cloud runs |
| quantura-fleet-core | Durable workbench, request ledger, bounded workers, MCP tooling | Bounded retries, idempotency keys, checkpoint store in the workflow | Hardware paths not run |

## IP / licensing findings (load-bearing)
- GitHub's API reports the licence of every audited private repo as
  `NOASSERTION` ("Other"), even where a README claims MIT. **Therefore no
  private repo is treated as licensed for redistribution**, and nothing was
  copied. Ideas and mathematical methods (CPA, TTC, finite differences) are
  re-derived here from first principles and standard references.
- Repo-stated test/coverage figures in the private portfolio are *not*
  independently re-run claims; several repos share templated scaffolding and
  identical stated figures, which is itself recorded as a maturity caveat:
  the defensible summary is "deterministic CPU reference implementations with
  audit scaffolding", not hardware or production validation.
- FrontierSight runtime dependencies: Python standard library only, so no
  third-party licence obligations are introduced. Demo fixtures are generated
  by code in this repo (`engine/scenarios.py`) and are MIT-licensed with it.

"""Uncertainty helpers. Missing evidence is reported as missing evidence —
never folded into a numerical interval to make it look quantified."""
from __future__ import annotations
import math

def interval(values: list, lo_q: float = 0.05, hi_q: float = 0.95) -> dict:
    if not values: raise ValueError("no values")
    s = sorted(values)
    def q(p): return s[min(len(s) - 1, max(0, int(p * len(s))))]
    return {"p_lo": q(lo_q), "median": q(0.5), "p_hi": q(hi_q), "n": len(s)}

def evidence_report(track) -> dict:
    """Per-track evidence quality: coverage, gaps, occlusion windows."""
    ts = [t for t, _ in track.points]
    gaps = [(round(a, 3), round(b, 3)) for (a, _), (b, _) in zip(track.points, track.points[1:]) if b - a > 0.21]
    return {"object_id": track.object_id, "observations": len(ts),
            "window": [ts[0], ts[-1]] if ts else None,
            "declared_occlusions": track.occluded, "observation_gaps": gaps,
            "source": track.source,
            "note": "gaps and occlusions are missing evidence, reported separately from numerical uncertainty"}

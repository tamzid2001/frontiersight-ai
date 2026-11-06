"""Validate three raw runs without selecting the most favorable result.

Performance uses the declared median of three. Accessibility, SEO, best
practices and any additional categories must pass in every run. Hidden editor
dependency requests and invalid/missing reports fail regardless of scores.
"""
import argparse
import json
import math
from pathlib import Path
from statistics import median

REQUIRED = {"performance", "accessibility", "best-practices", "seo"}
DEFERRED = ("/assets/sam-gallery/", "/image-scene.mjs", "/physical-intelligence.mjs",
            "/physical-intelligence.css", "/edge-studio.mjs", "/vendor/three", "/api/mcp")


def validate_reports(reports):
    if len(reports) != 3:
        raise ValueError("Exactly three Lighthouse runs are required")
    scores = []
    identities = set()
    for report in reports:
        if report.get("runtimeError"):
            raise ValueError("Lighthouse runtime failure")
        identities.add((report["finalDisplayedUrl"], report["lighthouseVersion"]))
        categories = report["categories"]
        if not REQUIRED.issubset(categories):
            raise ValueError("Missing required Lighthouse categories")
        row = {name: category["score"] for name, category in categories.items()}
        for name, score in row.items():
            if isinstance(score, bool) or not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Invalid Lighthouse category score")
            if name != "performance" and score < .95:
                raise ValueError(f"{name} below 95 in an individual run")
        requests = report["audits"]["network-requests"]["details"]["items"]
        if not requests:
            raise ValueError("Missing network-request evidence")
        if any(asset in request["url"] for request in requests for asset in DEFERRED):
            raise ValueError("Hidden editor dependencies loaded on the homepage")
        scores.append(row)
    if len(identities) != 1 or not next(iter(identities))[0] or not next(iter(identities))[1]:
        raise ValueError("Runs must measure the same URL and Lighthouse version")
    performance = median(row["performance"] for row in scores)
    if performance < .90:
        raise ValueError(f"Median performance {performance:.3f} below 90")
    return {"run_count": 3, "performance_aggregation": "median", "performance_minimum": .90,
            "median_performance": performance, "per_run_scores": scores,
            "other_categories": "Every run must meet 95; hidden dependencies always fail"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs=3, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args(argv)
    result = validate_reports([json.loads(path.read_text()) for path in args.reports])
    args.summary.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

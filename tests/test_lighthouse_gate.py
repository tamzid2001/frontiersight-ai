"""Gate logic fixtures are not actual Lighthouse measurements."""
import json

import pytest

from scripts.check_lighthouse import main, validate_reports


def report(performance=.95):
    return {"finalDisplayedUrl": "http://127.0.0.1:8799/", "lighthouseVersion": "13.6.0",
            "categories": {name: {"score": score} for name, score in {
                "performance": performance, "accessibility": 1, "best-practices": 1, "seo": 1,
                "agentic-browsing": 1}.items()},
            "audits": {"network-requests": {"details": {"items": [
                {"url": "http://127.0.0.1:8799/"}]}}}}


def test_median_has_a_fixed_sample_and_does_not_select_the_best_run():
    result = validate_reports([report(.81), report(1), report(.93)])
    assert result["median_performance"] == .93
    assert [r["performance"] for r in result["per_run_scores"]] == [.81, 1, .93]
    with pytest.raises(ValueError, match="below 90"):
        validate_reports([report(.81), report(1), report(.89)])
    assert validate_reports([report(.90)] * 3)["median_performance"] == .90
    with pytest.raises(ValueError, match="below 90"):
        validate_reports([report(.899)] * 3)  # No rounding a failure up to 90.


@pytest.mark.parametrize("count", [0, 1, 2, 4])
def test_requires_all_three_runs(count):
    with pytest.raises(ValueError, match="Exactly three"):
        validate_reports([report()] * count)


@pytest.mark.parametrize("score", [None, True, "1", float("nan"), float("inf"), -1, 1.01])
def test_rejects_invalid_scores(score):
    with pytest.raises(ValueError, match="Invalid"):
        validate_reports([report(score), report(), report()])


@pytest.mark.parametrize("category", ["accessibility", "best-practices", "seo", "agentic-browsing"])
def test_a_bad_nontiming_score_fails_even_if_other_runs_pass(category):
    bad = report()
    bad["categories"][category]["score"] = .94
    with pytest.raises(ValueError, match="individual run"):
        validate_reports([report(), bad, report()])


@pytest.mark.parametrize("asset", ["/api/mcp", "/physical-intelligence.mjs", "/assets/sam-gallery/example.jpg"])
def test_hidden_dependency_is_a_failure_in_any_run(asset):
    bad = report()
    bad["audits"]["network-requests"]["details"]["items"].append({"url": "http://127.0.0.1:8799" + asset})
    with pytest.raises(ValueError, match="Hidden editor"):
        validate_reports([bad, report(), report()])


@pytest.mark.parametrize("field", ["finalDisplayedUrl", "lighthouseVersion"])
def test_all_runs_must_measure_the_same_target_and_version(field):
    bad = report()
    bad[field] = "different"
    with pytest.raises(ValueError, match="same URL"):
        validate_reports([report(), bad, report()])
    empty = report()
    empty[field] = ""
    with pytest.raises(ValueError, match="same URL"):
        validate_reports([empty] * 3)


def test_missing_runtime_or_network_evidence_cannot_pass():
    bad = report()
    bad["runtimeError"] = {"code": "FAILED_DOCUMENT_REQUEST"}
    with pytest.raises(ValueError, match="runtime failure"):
        validate_reports([bad, report(), report()])
    bad = report()
    del bad["categories"]["seo"]
    with pytest.raises(ValueError, match="Missing required"):
        validate_reports([bad, report(), report()])
    bad = report()
    bad["audits"]["network-requests"]["details"]["items"] = []
    with pytest.raises(ValueError, match="Missing network"):
        validate_reports([bad, report(), report()])


def test_cli_requires_real_parseable_files_and_writes_all_scores(tmp_path, capsys):
    files = [tmp_path / f"run-{i}.json" for i in range(3)]
    summary = tmp_path / "summary.json"
    for path in files:
        path.write_text(json.dumps(report()))
    main([*(str(path) for path in files), "--summary", str(summary)])
    assert json.loads(summary.read_text())["run_count"] == 3
    assert '"median_performance": 0.95' in capsys.readouterr().out
    summary.unlink()
    files[0].write_text("not JSON")
    with pytest.raises(json.JSONDecodeError):
        main([*(str(path) for path in files), "--summary", str(summary)])
    assert not summary.exists()

import pytest
from integrations.meta.sam import parse_output_text
from integrations.meta import spark
from agents.workflow import run_analysis
from engine import scenarios as scen

SAMPLE = ("<0f>1<|box;x1=10;y1=20;x2=60;y2=90;w=640;h=480;c=0.91|>"
          "<|mask;x=0;y=0;c=0.91;data=30,40,~abcXYZ|>,2<|box;x1=100;y1=100;x2=140;y2=180;w=640;h=480|>\n"
          "<3f>1<|box;x1=14;y1=20;x2=64;y2=90;w=640;h=480;c=0.88|>\n"
          "garbage line")

def test_sam_parser_documented_grammar():
    out = parse_output_text(SAMPLE)
    assert out["objects"] == [1, 2]
    f0 = out["frames"][0]
    assert f0["frame"] == 0 and f0["records"][0]["box"]["x2"] == 60
    assert f0["records"][0]["confidence"] == pytest.approx(0.91)
    assert f0["records"][0]["mask"]["raster"] == ["30", "40"] and f0["records"][0]["mask"]["decoded"] is False
    assert out["frames"][1]["records"][0]["object_id"] == 1  # stable track id across frames
    assert any(d["code"] == "unparsed_line" for d in out["diagnostics"])

def test_sam_parser_zero_matches_is_valid():
    out = parse_output_text("")
    assert out["frames"] == [] and out["objects"] == []

def test_spark_blocks_without_key(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert spark.configured() is False
    with pytest.raises(spark.BlockedCredentials):
        spark.narrate({})

def test_workflow_fixture_replay_end_to_end():
    run = run_analysis(scen.build("warehouse-near-miss"))
    names = [s.name for s in run.stages]
    assert names == ["scene_analyst", "research_planner", "segmentation", "scene_extraction",
                     "hypothesis", "simulation", "independent_verification", "human_review", "export"]
    assert run.mode == "FIXTURE_REPLAY"
    seg = run.stages[2]
    assert seg.detail["status"] == "unavailable_offline"  # never claims segmentation happened
    assert run.stages[-1].status == "skipped"  # export gated on human review
    run2 = run_analysis(scen.build("warehouse-near-miss"), human_approved=True)
    assert run2.stages[-1].status == "completed"

def test_workflow_idempotent(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    a = run_analysis(scen.build("safe-passing"), idempotency_key="test-key-1")
    b = run_analysis(scen.build("safe-passing"), idempotency_key="test-key-1")
    assert a.run_id == b.run_id

def test_api_smoke():
    from services.api.server import main
    assert main(["--smoke", "--port", "8795"]) == 0

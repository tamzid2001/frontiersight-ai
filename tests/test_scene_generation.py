"""Bounded multi-candidate generation without paid network requests."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from integrations.meta import spark


def scene(y=3):
    return {"name": "Warehouse", "explanation": "A candidate.", "objects": [
        {"category": "pedestrian", "waypoints": [[2, y], [5, y]], "speed": 1, "radius": .45},
        {"category": "forklift", "waypoints": [[8, 8], [12, 8]], "speed": 1.2, "radius": .9},
    ]}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "unit-test-placeholder-not-a-secret")


@pytest.mark.parametrize("count", [0, 9, True, 2.5, "3", None])
def test_candidate_budget_rejects_invalid_input(count):
    with pytest.raises(ValueError, match="candidates"):
        spark.generate_scene("A warehouse scene", candidates=count)


def test_candidates_are_finite_parallel_and_select_one(monkeypatch):
    barrier = threading.Barrier(3)
    calls = []
    def provider(prompt, **kwargs):
        calls.append(kwargs)
        barrier.wait(timeout=2)  # Would deadlock if candidates ran sequentially.
        return json.dumps(scene()), {"model": kwargs["model"]}
    monkeypatch.setattr(spark, "_call", provider)
    chosen, meta = spark.generate_scene("A warehouse scene", "muse-spark-1.1", candidates=3)
    assert len(calls) == 3
    assert all(call == {"timeout": 20, "retries": 0, "model": "muse-spark-1.1"} for call in calls)
    assert chosen["name"] == "Warehouse"
    assert meta["candidates_valid"] == meta["candidates_completed"] == 3
    assert meta["automatic_retries"] == 0


def test_invalid_candidates_do_not_trigger_repair_calls(monkeypatch):
    calls = []
    def provider(*args, **kwargs):
        calls.append(1)
        return "not JSON", {}
    monkeypatch.setattr(spark, "_call", provider)
    with pytest.raises(spark.ModelError, match="No candidate"):
        spark.generate_scene("A warehouse scene", candidates=2)
    assert len(calls) == 2


def test_valid_candidate_survives_an_invalid_peer(monkeypatch):
    lock, index = threading.Lock(), [0]
    def provider(*args, **kwargs):
        with lock:
            index[0] += 1
            invalid = index[0] == 1
        return ("[]" if invalid else json.dumps(scene())), {}
    monkeypatch.setattr(spark, "_call", provider)
    _, meta = spark.generate_scene("A warehouse scene", candidates=2)
    assert meta["candidates_valid"] == 1


def test_timeout_retains_capacity_until_provider_finishes(monkeypatch):
    release, started = threading.Event(), threading.Event()
    def provider(*args, **kwargs):
        started.set()
        release.wait(timeout=2)
        return json.dumps(scene()), {}
    monkeypatch.setattr(spark, "_call", provider)
    monkeypatch.setattr(spark, "SCENE_DEADLINE_SECONDS", .02)
    before = time.monotonic()
    try:
        with pytest.raises(spark.SceneTimeout):
            spark.generate_scene("A warehouse scene", candidates=1)
        assert started.is_set() and time.monotonic() - before < .5
        with pytest.raises(spark.SceneBusy):
            spark.generate_scene("A second scene", candidates=1)
    finally:
        release.set()
        # Wait for the callback, rather than racing subsequent tests.
        acquired = spark._SCENE_CAPACITY.acquire(timeout=2)
        assert acquired
        spark._SCENE_CAPACITY.release()


def test_completed_candidate_can_be_returned_at_deadline(monkeypatch):
    release, index, lock = threading.Event(), [0], threading.Lock()
    def provider(*args, **kwargs):
        with lock:
            index[0] += 1
            slow = index[0] == 2
        if slow:
            release.wait(timeout=2)
        return json.dumps(scene()), {}
    monkeypatch.setattr(spark, "_call", provider)
    monkeypatch.setattr(spark, "SCENE_DEADLINE_SECONDS", .02)
    try:
        _, meta = spark.generate_scene("A warehouse scene", candidates=2)
        assert meta["candidates_completed"] == meta["candidates_valid"] == 1
    finally:
        release.set()
        assert spark._SCENE_CAPACITY.acquire(timeout=2)
        spark._SCENE_CAPACITY.release()


def test_response_body_is_bounded(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            assert size == spark.MAX_MODEL_RESPONSE_BYTES + 1
            return b"x" * size
    monkeypatch.setattr(spark.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(spark.ModelError, match="size limit"):
        spark._call("prompt", retries=0)


@pytest.mark.parametrize("value", [[], None, "text", {"objects": [None, None]}])
def test_non_object_scene_is_rejected(value):
    with pytest.raises(spark.ModelError):
        spark.validate_scene(value)

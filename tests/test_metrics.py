"""成本/QoS 对账单测(design.md §14/§15/§22)。用内存库,断言节省率与分桶。"""
from __future__ import annotations

import pytest

from metrics import MetricsStore, BASELINE_IMAGE_TOKENS, _percentile


@pytest.fixture
def store():
    return MetricsStore(":memory:")


def test_empty_summary(store):
    s = store.summary()
    assert s["turns"] == 0
    assert s["savings_rate"] == 0.0
    assert s["cache_hit_rate"] == 0.0


def test_savings_rate_against_baseline(store):
    # 两轮带图,实际各 300 input token;Baseline 假设各 1300
    store.record_turn(turn_type="image", input_tokens=300, output_tokens=20)
    store.record_turn(turn_type="image", input_tokens=300, output_tokens=20)
    s = store.summary()
    assert s["actual_input_tokens"] == 600
    assert s["baseline_input_tokens"] == 2 * BASELINE_IMAGE_TOKENS
    # 节省率 = 1 - 600/2600
    assert s["savings_rate"] == round(1 - 600 / 2600, 3)


def test_cache_hit_counts_and_zero_tokens(store):
    store.record_turn(turn_type="image", cache_hit=True, input_tokens=0, output_tokens=0)
    store.record_turn(turn_type="image", cache_hit=False, input_tokens=400, output_tokens=10)
    s = store.summary()
    assert s["turns"] == 2
    assert s["cache_hits"] == 1
    assert s["cache_hit_rate"] == 0.5


def test_latency_buckets_by_turn_type(store):
    for ms in (100, 200, 300):
        store.record_turn(turn_type="text", input_tokens=10, latency_ms=ms)
    store.record_turn(turn_type="image", input_tokens=1000, latency_ms=2500)
    s = store.summary()
    assert s["latency_ms"]["text"]["n"] == 3
    assert s["latency_ms"]["text"]["p50"] == 200
    assert s["latency_ms"]["image"]["n"] == 1


def test_track_events_counted(store):
    store.track("camera_open")
    store.track("vision_success", {"route": "image"})
    assert store.summary()["events"] == 2


def test_cost_estimate_nonnegative(store):
    store.record_turn(input_tokens=1000, output_tokens=500)
    assert store.summary()["cost_estimate_cny"] >= 0


def test_reset(store):
    store.record_turn(input_tokens=100)
    store.track("x")
    store.reset()
    s = store.summary()
    assert s["turns"] == 0 and s["events"] == 0


def test_percentile_helper():
    assert _percentile([], 50) == 0.0
    assert _percentile([10], 95) == 10
    assert _percentile([1, 2, 3, 4], 50) in (2, 3)


def test_ab_breakdown_by_variant(store):
    # on 组省 token(OCR 只发文本),off 组发整图
    store.record_turn(turn_type="image", input_tokens=200, latency_ms=100, variant="on")
    store.record_turn(turn_type="image", input_tokens=1300, latency_ms=200, variant="off")
    ab = store.summary()["ab"]["ocr_first"]
    assert ab["on"]["turns"] == 1 and ab["off"]["turns"] == 1
    assert ab["on"]["savings_rate"] > ab["off"]["savings_rate"]
    assert ab["off"]["avg_latency_ms"] == 200


def test_ab_ignores_unbucketed(store):
    store.record_turn(turn_type="image", input_tokens=100, variant="")
    assert store.summary()["ab"]["ocr_first"] == {}

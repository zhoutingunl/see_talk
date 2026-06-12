"""A/B 实验框架单测(design.md §18/§22)。"""
from __future__ import annotations

from experiments import EXPERIMENTS, all_assignments, assign


def test_assignment_is_deterministic():
    a = assign("user-1", "ocr_first")
    b = assign("user-1", "ocr_first")
    assert a == b and a in ("on", "off")


def test_distribution_covers_both_variants():
    variants = {assign(f"u{i}", "ocr_first") for i in range(300)}
    assert variants == {"on", "off"}


def test_roughly_balanced_split():
    on = sum(assign(f"u{i}", "ocr_first") == "on" for i in range(1000))
    assert 350 < on < 650          # 50/50 大致均衡


def test_unknown_experiment_returns_empty():
    assert assign("u", "does-not-exist") == ""


def test_all_assignments_contains_defined():
    a = all_assignments("u1")
    assert set(a) == set(EXPERIMENTS)
    assert a["ocr_first"] in ("on", "off")

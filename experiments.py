"""A/B 实验框架(design.md §18)。

按 session_id 确定性分桶(同一用户始终同一变体),记录到 metrics,
Dashboard / /api/experiments 按变体对比成本与延迟,量化策略效果。

当前实验:
- ocr_first:OCR 优先路由 on / off —— 量化"只发文本省 token vs 误判风险"。
"""
from __future__ import annotations

import hashlib

EXPERIMENTS: dict[str, dict] = {
    "ocr_first": {"variants": ["on", "off"], "split": [50, 50], "default": "on"},
}


def assign(session_id: str, experiment: str) -> str:
    """确定性分桶:同一 (session_id, experiment) 永远同一变体。"""
    spec = EXPERIMENTS.get(experiment)
    if not spec:
        return ""
    variants, split = spec["variants"], spec["split"]
    digest = hashlib.md5(f"{experiment}:{session_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % sum(split)
    cum = 0
    for v, w in zip(variants, split):
        cum += w
        if bucket < cum:
            return v
    return spec["default"]


def all_assignments(session_id: str) -> dict[str, str]:
    return {exp: assign(session_id, exp) for exp in EXPERIMENTS}

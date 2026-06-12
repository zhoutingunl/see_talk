"""评估框架(design.md §17)——避免伪指标,用可复现的样例集实测能力。

三类打分(均确定性、不依赖人工):
- OCR Accuracy:已知文字图 → OCR → 字符级相似度。
- Conversation Success:渲染场景图 → 走 vision 管线 → 关键词命中率。
- (延迟/成本由 metrics 实测,见 §15,本模块不重复。)

render_fn / svc / ocr 均可注入,便于单测用 Mock;直接运行则跑真实服务出报告。
"""
from __future__ import annotations

import base64
import io
from difflib import SequenceMatcher


# ---------- 打分函数(纯逻辑)----------
def char_accuracy(expected: str, actual: str) -> float:
    """字符级相似度(忽略空白),0~1。"""
    e = "".join(expected.split())
    a = "".join(actual.split())
    if not e:
        return 1.0 if not a else 0.0
    return round(SequenceMatcher(None, e, a).ratio(), 3)


def keyword_score(answer: str, keywords: list[str]) -> float:
    """关键词命中率,0~1。"""
    if not keywords:
        return 1.0
    hit = sum(1 for k in keywords if k.lower() in answer.lower())
    return round(hit / len(keywords), 3)


# ---------- 样例集 ----------
OCR_CASES = ["ERROR 404", "Segmentation fault", "Connection timeout"]

QA_CASES = [
    {"image_text": "ERROR 404 not found",
     "question": "What HTTP status is shown?", "keywords": ["404"]},
    {"image_text": "TypeError None",
     "question": "What error type is this?", "keywords": ["TypeError", "type"]},
]


# ---------- 默认渲染 ----------
def default_render(text: str) -> str:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (520, 140), "white")
    d = ImageDraw.Draw(img)
    font = None
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        try:
            font = ImageFont.truetype(p, 40)
            break
        except Exception:
            continue
    d.text((20, 40), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


# ---------- 评估流程 ----------
def evaluate_ocr(ocr, render=default_render) -> dict:
    scores = []
    for text in OCR_CASES:
        got, _, _ = ocr.extract(render(text))
        scores.append(char_accuracy(text, got))
    avg = round(sum(scores) / len(scores), 3) if scores else 0.0
    return {"metric": "ocr_accuracy", "avg": avg, "n": len(scores), "scores": scores}


def evaluate_qa(svc, render=default_render) -> dict:
    scores = []
    for case in QA_CASES:
        reply = svc.vision_chat(case["question"], image_b64=render(case["image_text"]))
        scores.append(keyword_score(reply.text, case["keywords"]))
    avg = round(sum(scores) / len(scores), 3) if scores else 0.0
    return {"metric": "conversation_success", "avg": avg, "n": len(scores),
            "scores": scores}


def run_all(svc, ocr, render=default_render) -> dict:
    return {"ocr": evaluate_ocr(ocr, render), "qa": evaluate_qa(svc, render)}


if __name__ == "__main__":  # pragma: no cover - 手动跑真实服务
    import json

    from ai import get_service
    from ocr_service import get_ocr

    report = run_all(get_service(), get_ocr())
    print(json.dumps(report, ensure_ascii=False, indent=2))

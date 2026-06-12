"""SeeTalk Flask 应用入口(PR1:最小「抓帧 → 提问 → 回答」闭环)。

PR1 范围:摄像头抓帧 + 文字提问 → M3 多模态回答(无 key 时 Mock 降级)。
语音 ASR / TTS / 成本 Dashboard 见后续 PR(design.md §26)。
"""
from __future__ import annotations

import base64
import logging
import re

from flask import Flask, jsonify, render_template, request

import config
from ai import get_service

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("seetalk")

app = Flask(__name__)

# data URL 前缀:data:image/jpeg;base64,xxxx
_DATA_URL = re.compile(r"^data:(?P<mt>image/[\w.+-]+);base64,(?P<data>.+)$", re.S)


def _parse_image(raw: str | None) -> tuple[str | None, str]:
    """解析前端传来的图片:支持 data URL 或裸 base64。返回 (base64, media_type)。"""
    if not raw:
        return None, "image/jpeg"
    m = _DATA_URL.match(raw.strip())
    if m:
        return m.group("data"), m.group("mt")
    return raw.strip(), "image/jpeg"


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    svc = get_service()
    return jsonify(status=config.status(), vision_live=svc.vision_live)


@app.post("/api/ask")
def ask():
    """{question, image?} → {answer, source, degraded, tokens}。"""
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify(error="question 不能为空"), 400

    image_b64, media_type = _parse_image(payload.get("image"))
    # 轻量校验 base64,避免把脏数据发去云端
    if image_b64:
        try:
            base64.b64decode(image_b64, validate=True)
        except Exception:
            return jsonify(error="image 不是合法的 base64"), 400

    reply = get_service().vision_chat(
        question, image_b64=image_b64, media_type=media_type)
    return jsonify(
        answer=reply.text,
        source=reply.source,
        degraded=reply.degraded,
        tokens={"input": reply.input_tokens, "output": reply.output_tokens},
    )


def main() -> None:
    host, port = "0.0.0.0", 8000
    try:  # 生产用 gevent(design.md 技术栈);未装则退回 Flask 开发服务器
        from gevent.pywsgi import WSGIServer

        log.info("SeeTalk on http://%s:%d (gevent)", host, port)
        WSGIServer((host, port), app).serve_forever()
    except ImportError:  # pragma: no cover
        log.info("SeeTalk on http://%s:%d (flask dev)", host, port)
        app.run(host=host, port=port)


if __name__ == "__main__":
    main()

"""SeeTalk Flask 应用入口(PR1:最小「抓帧 → 提问 → 回答」闭环)。

PR1 范围:摄像头抓帧 + 文字提问 → M3 多模态回答(无 key 时 Mock 降级)。
语音 ASR / TTS / 成本 Dashboard 见后续 PR(design.md §26)。
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time

from flask import Flask, Response, jsonify, render_template, request

import config
import metrics
import ocr_service
import vision_cache
from ai import get_service
from ai.service import ASRUnavailable
from ai.types import VisionReply

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("seetalk")

app = Flask(__name__)

# 进程级视觉缓存(变化检测 + 同画面复用,design.md §14)
_cache = vision_cache.VisionCache()

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


def _frame_hash(image_b64: str | None) -> int:
    return vision_cache.average_hash(image_b64) if image_b64 else 0


def _route_vision(question: str, image_b64: str | None) -> tuple[str, str | None, str]:
    """OCR 优先路由(design.md §14)。返回 (发送用问题, 发送用图, route)。

    文本场景:本地 OCR 出文本 → 只发文本省掉整图 token;否则发图。
    """
    if not image_b64:
        return question, None, "text"
    ocr = ocr_service.get_ocr()
    if not ocr.enabled:
        return question, image_b64, "image"
    text, conf, nchars = ocr.extract(image_b64)
    if ocr.is_text_scene(text, conf, nchars):
        metrics.get_store().track("ocr_route", {"chars": nchars, "conf": conf})
        aug = f"{question}\n\n[画面识别到的文字]:\n{text}"
        return aug, None, "ocr"
    return question, image_b64, "image"


def _record(turn_type: str, route: str, reply: VisionReply,
            cache_hit: bool, t0: float) -> None:
    store = metrics.get_store()
    store.record_turn(
        turn_type=turn_type, route=route, source=reply.source, cache_hit=cache_hit,
        input_tokens=0 if cache_hit else reply.input_tokens,
        output_tokens=0 if cache_hit else reply.output_tokens,
        latency_ms=(time.monotonic() - t0) * 1000)
    store.track("cache_hit" if cache_hit else
                ("vision_success" if reply.source == "minimax" else "vision_mock"),
                {"route": route})


def _sse(ev: dict) -> str:
    return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.get("/api/metrics")
def api_metrics():
    return jsonify(metrics.get_store().summary())


@app.get("/api/health")
def health():
    svc = get_service()
    return jsonify(status=config.status(), vision_live=svc.vision_live,
                   asr_live=svc.asr_live)


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

    t0 = time.monotonic()
    h = _frame_hash(image_b64)
    turn_type = "image" if image_b64 else "text"
    cached = _cache.get(h, question) if image_b64 else None
    if cached is not None:
        reply, cache_hit, route = cached, True, "cache"
    else:
        q_send, img_send, route = _route_vision(question, image_b64)
        reply = get_service().vision_chat(
            q_send, image_b64=img_send, media_type=media_type)
        cache_hit = False
        if image_b64 and reply.source == "minimax":
            _cache.put(h, question, reply)
    _cache.mark(h)
    _record(turn_type, route, reply, cache_hit, t0)
    return jsonify(
        answer=reply.text,
        source=reply.source,
        degraded=reply.degraded,
        cache_hit=cache_hit,
        route=route,
        tokens={"input": 0 if cache_hit else reply.input_tokens,
                "output": 0 if cache_hit else reply.output_tokens},
    )


@app.post("/api/ask_stream")
def ask_stream():
    """流式多模态(SSE):逐段 data:{type:delta|done}。供前端首句优先 TTS。"""
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify(error="question 不能为空"), 400
    image_b64, media_type = _parse_image(payload.get("image"))
    if image_b64:
        try:
            base64.b64decode(image_b64, validate=True)
        except Exception:
            return jsonify(error="image 不是合法的 base64"), 400

    t0 = time.monotonic()
    h = _frame_hash(image_b64)
    turn_type = "image" if image_b64 else "text"

    def gen():
        cached = _cache.get(h, question) if image_b64 else None
        if cached is not None:                       # 命中缓存:复用文本,零云调用
            for i in range(0, len(cached.text), 12):
                yield _sse({"type": "delta", "text": cached.text[i:i + 12]})
            yield _sse({"type": "done", "source": cached.source, "cache_hit": True,
                        "input_tokens": 0, "output_tokens": 0})
            _cache.mark(h)
            _record(turn_type, "cache", cached, True, t0)
            return

        q_send, img_send, route = _route_vision(question, image_b64)
        acc, src, in_tok, out_tok = "", "mock", 0, 0
        try:
            for ev in get_service().vision_chat_stream(
                    q_send, image_b64=img_send, media_type=media_type):
                if ev["type"] == "delta":
                    acc += ev["text"]
                elif ev["type"] == "done":
                    src = ev.get("source", "mock")
                    in_tok = ev.get("input_tokens", 0)
                    out_tok = ev.get("output_tokens", 0)
                yield _sse(ev)
        except Exception as e:  # 流中异常以事件收尾,前端不挂死
            log.warning("ask_stream 异常:%s", e)
            yield _sse({"type": "error", "message": str(e)})
            return

        reply = VisionReply(text=acc, source=src, input_tokens=in_tok,
                            output_tokens=out_tok, degraded=(src == "mock"))
        if image_b64 and src == "minimax":
            _cache.put(h, question, reply)
        _cache.mark(h)
        _record(turn_type, route, reply, False, t0)

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/asr")
def asr():
    """移动端 ASR:body 为单声道 16k PCM(application/octet-stream)→ {text}。"""
    pcm = request.get_data() or b""
    if len(pcm) < 320:  # 不足 ~10ms,视为空
        return jsonify(error="音频为空"), 400
    try:
        text = get_service().transcribe(pcm)
    except ASRUnavailable:
        return jsonify(error="服务端 ASR 未配置,请用浏览器 Web Speech"), 503
    except Exception as e:
        log.warning("ASR 失败:%s", e)
        metrics.get_store().track("asr_fail", {"bytes": len(pcm)})
        return jsonify(error="识别失败"), 502
    metrics.get_store().track("asr_success", {"bytes": len(pcm)})
    return jsonify(text=text)


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

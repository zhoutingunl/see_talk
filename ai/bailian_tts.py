"""阿里百炼 CosyVoice 实时 TTS(DashScope WebSocket run-task 协议)。

与 ASR 同一端点 / 同一把 Key,任务为 tts:
  run-task(voice/format 参数)→ task-started
  → continue-task(input.text)→ finish-task
  → 服务端回二进制音频帧 + result-generated,直到 task-finished

按"一句话"为单位合成,返回完整音频字节(供前端逐句播放,首句优先)。
"""
from __future__ import annotations

import json
import uuid

from config import BailianConfig


class BailianTTSError(RuntimeError):
    pass


class BailianTTSClient:
    def __init__(self, cfg: BailianConfig, *, timeout: float = 30.0) -> None:
        if not cfg.ready:
            raise BailianTTSError("百炼 API key 未配置")
        self.cfg = cfg
        self.timeout = timeout

    def _connect(self):
        from websocket import create_connection

        return create_connection(
            self.cfg.ws_url,
            header=[f"Authorization: bearer {self.cfg.api_key}"],
            timeout=self.timeout,
        )

    def _run_task_msg(self, task_id: str) -> str:
        return json.dumps({
            "header": {"action": "run-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {
                "task_group": "audio", "task": "tts", "function": "SpeechSynthesizer",
                "model": self.cfg.tts_model,
                "parameters": {
                    "text_type": "PlainText", "voice": self.cfg.tts_voice,
                    "format": self.cfg.tts_format, "sample_rate": self.cfg.tts_sample_rate,
                },
                "input": {},
            },
        })

    @staticmethod
    def _continue_msg(task_id: str, text: str) -> str:
        return json.dumps({
            "header": {"action": "continue-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {"input": {"text": text}},
        })

    @staticmethod
    def _finish_msg(task_id: str) -> str:
        return json.dumps({
            "header": {"action": "finish-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {"input": {}},
        })

    @staticmethod
    def _event(msg) -> str | None:
        if isinstance(msg, (bytes, bytearray)):
            return None
        return json.loads(msg).get("header", {}).get("event")

    def synthesize(self, text: str) -> bytes:
        """合成单段文本,返回完整音频字节(mp3)。失败抛 BailianTTSError。"""
        task_id = uuid.uuid4().hex
        ws = self._connect()
        try:
            ws.send(self._run_task_msg(task_id))
            self._await_started(ws)
            ws.send(self._continue_msg(task_id, text))
            ws.send(self._finish_msg(task_id))
            return self._collect_audio(ws)
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _await_started(self, ws) -> None:
        while True:
            msg = ws.recv()
            ev = self._event(msg)
            if ev == "task-started":
                return
            if ev == "task-failed":
                raise BailianTTSError(
                    f"task-failed: {json.loads(msg).get('header', {}).get('error_message')}")

    def _collect_audio(self, ws) -> bytes:
        chunks: list[bytes] = []
        while True:
            msg = ws.recv()
            if isinstance(msg, (bytes, bytearray)):   # 二进制音频帧
                chunks.append(bytes(msg))
                continue
            ev = json.loads(msg).get("header", {}).get("event")
            if ev == "task-finished":
                return b"".join(chunks)
            if ev == "task-failed":
                raise BailianTTSError(
                    f"task-failed: {json.loads(msg).get('header', {}).get('error_message')}")

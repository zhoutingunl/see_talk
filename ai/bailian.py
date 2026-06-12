"""阿里百炼 Paraformer 实时 ASR(DashScope WebSocket run-task 协议)。

协议(DashScope 实时系列通用):
  连接 wss://dashscope.aliyuncs.com/api-ws/v1/inference,头 Authorization: bearer <key>
  → 发 run-task(JSON 文本)→ 收 task-started
  → 发二进制音频帧(单声道 PCM,16k)→ 收 result-generated(句子增量)
  → 发 finish-task → 收 task-finished

移动端按"VAD 切出的一句话"为单位一次性转写:喂完整 PCM,收最终文本。
"""
from __future__ import annotations

import json
import uuid

from config import BailianConfig


class BailianError(RuntimeError):
    pass


class BailianASRClient:
    def __init__(self, cfg: BailianConfig, *, timeout: float = 20.0,
                 chunk_bytes: int = 3200) -> None:  # ~100ms @16k/16bit/mono
        if not cfg.ready:
            raise BailianError("百炼 API key 未配置")
        self.cfg = cfg
        self.timeout = timeout
        self.chunk_bytes = chunk_bytes

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
                "task_group": "audio", "task": "asr", "function": "recognition",
                "model": self.cfg.asr_model,
                "parameters": {"format": self.cfg.audio_format,
                               "sample_rate": self.cfg.sample_rate},
                "input": {},
            },
        })

    @staticmethod
    def _finish_msg(task_id: str) -> str:
        return json.dumps({
            "header": {"action": "finish-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {"input": {}},
        })

    def transcribe(self, pcm: bytes) -> str:
        """一次性转写单声道 16k PCM,返回最终文本。失败抛 BailianError。"""
        task_id = uuid.uuid4().hex
        ws = self._connect()
        try:
            ws.send(self._run_task_msg(task_id))
            self._await_event(ws, "task-started")

            for i in range(0, len(pcm), self.chunk_bytes):
                ws.send_binary(pcm[i:i + self.chunk_bytes])

            ws.send(self._finish_msg(task_id))
            return self._collect_until_finished(ws)
        finally:
            try:
                ws.close()
            except Exception:
                pass

    @staticmethod
    def _event(msg) -> tuple[str | None, dict]:
        if isinstance(msg, (bytes, bytearray)):
            return None, {}
        data = json.loads(msg)
        return data.get("header", {}).get("event"), data

    def _await_event(self, ws, target: str) -> None:
        while True:
            ev, data = self._event(ws.recv())
            if ev == target:
                return
            if ev == "task-failed":
                raise BailianError(
                    f"task-failed: {data.get('header', {}).get('error_message')}")

    def _collect_until_finished(self, ws) -> str:
        finalized: list[str] = []
        current = ""
        while True:
            ev, data = self._event(ws.recv())
            if ev == "result-generated":
                sent = (data.get("payload", {}).get("output", {}) or {}).get("sentence") or {}
                current = sent.get("text", current) or current
                if sent.get("sentence_end"):
                    if current:
                        finalized.append(current)
                    current = ""
            elif ev == "task-finished":
                if current:
                    finalized.append(current)
                return "".join(finalized).strip()
            elif ev == "task-failed":
                raise BailianError(
                    f"task-failed: {data.get('header', {}).get('error_message')}")

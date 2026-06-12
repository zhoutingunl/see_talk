"""MiniMax-M3 多模态接入:Anthropic 兼容 /v1/messages,图片以 base64 block 传入。

实测约定(参考姊妹项目 speak_mate/ai/minimax.py):
- 鉴权:x-api-key + anthropic-version 头。
- 多模态:user 消息 content 用 block 列表,image block 在前、text 在后。
- 返回:content[].text 拼接;usage.input_tokens / output_tokens 用于成本对账。
"""
from __future__ import annotations

import json
from collections.abc import Iterator

import requests

from config import MiniMaxConfig
from .types import ChatMessage, VisionReply


class MiniMaxError(RuntimeError):
    pass


class MiniMaxClient:
    def __init__(self, cfg: MiniMaxConfig) -> None:
        if not cfg.ready:
            raise MiniMaxError("MiniMax API key 未配置")
        self.cfg = cfg

    def _headers(self) -> dict:
        return {
            "x-api-key": self.cfg.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _build_messages(self, question: str, image_b64: str | None,
                        media_type: str, history: list[ChatMessage] | None) -> list[dict]:
        """历史只含文本(design.md §11);只有当前轮 content 携带 image block。"""
        content: list[dict] = []
        if image_b64:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type,
                           "data": image_b64},
            })
        content.append({"type": "text", "text": question})
        messages = [m.to_api() for m in (history or [])]
        messages.append({"role": "user", "content": content})
        return messages

    def vision_chat(self, question: str, *, image_b64: str | None = None,
                    media_type: str = "image/jpeg",
                    history: list[ChatMessage] | None = None,
                    system: str | None = None,
                    max_tokens: int = 1024) -> VisionReply:
        """当前轮带图(可选)+ 文本历史 → 一次多模态调用(非流式)。"""
        messages = self._build_messages(question, image_b64, media_type, history)
        body: dict = {
            "model": self.cfg.llm_model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            body["system"] = system

        resp = requests.post(
            f"{self.cfg.base_url}/v1/messages",
            headers=self._headers(), json=body, timeout=self.cfg.timeout,
        )
        if resp.status_code != 200:
            raise MiniMaxError(f"vision_chat HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text").strip()
        usage = data.get("usage", {}) or {}
        return VisionReply(
            text=text,
            source="minimax",
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
        )

    def vision_chat_stream(self, question: str, *, image_b64: str | None = None,
                           media_type: str = "image/jpeg",
                           history: list[ChatMessage] | None = None,
                           system: str | None = None,
                           max_tokens: int = 1024) -> Iterator[dict]:
        """流式多模态(首句优先,design.md §16)。

        逐段 yield {"type":"delta","text":...},末尾 yield
        {"type":"done","source":"minimax","input_tokens":..,"output_tokens":..}。
        """
        messages = self._build_messages(question, image_b64, media_type, history)
        body: dict = {
            "model": self.cfg.llm_model,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": messages,
        }
        if system:
            body["system"] = system

        in_tok = out_tok = 0
        with requests.post(
                f"{self.cfg.base_url}/v1/messages",
                headers=self._headers(), json=body, timeout=self.cfg.timeout,
                stream=True) as resp:
            if resp.status_code != 200:
                raise MiniMaxError(
                    f"vision_chat_stream HTTP {resp.status_code}: {resp.text[:300]}")
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    evt = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type")
                if etype == "message_start":
                    in_tok = int((evt.get("message", {}).get("usage", {})
                                  or {}).get("input_tokens", 0) or 0)
                elif etype == "content_block_delta":
                    delta = evt.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield {"type": "delta", "text": delta["text"]}
                elif etype == "message_delta":
                    out_tok = int((evt.get("usage", {}) or {}).get(
                        "output_tokens", out_tok) or out_tok)

        yield {"type": "done", "source": "minimax",
               "input_tokens": in_tok, "output_tokens": out_tok}

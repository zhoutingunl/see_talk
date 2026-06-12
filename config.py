"""集中配置:环境变量 / .env 为底,绝不硬编码密钥(design.md §25)。

- MiniMax-M3:Anthropic 兼容直连,承担视觉 + 对话(design.md §9)。
- 百炼 Paraformer:移动端 ASR(PR2 接入,这里先占位)。
- PlanConfig:档位(上下文轮数 / 视觉记忆帧数 …)映射付费等级(design.md §11/§24)。

各 provider 是否就绪在这里统一给出;未配置 Key 时 AIService 自动降级 Mock。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# 轻量加载 .env(无 python-dotenv 时静默跳过,环境变量仍可生效)
try:  # pragma: no cover - 取决于运行环境
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except Exception:  # pragma: no cover
    pass


_PLACEHOLDER = {"", "replace-me", "your-key", "changeme"}


def _clean(value: str | None) -> str:
    """把占位值视作未配置,避免拿假 key 去打真实接口。"""
    v = (value or "").strip()
    return "" if v in _PLACEHOLDER else v


@dataclass(frozen=True)
class MiniMaxConfig:
    """MiniMax-M3 多模态(Anthropic 兼容 /v1/messages)。"""

    base_url: str = "https://api.minimaxi.com/anthropic"
    api_key: str = ""
    llm_model: str = "MiniMax-M3"
    timeout: float = 60.0

    @property
    def ready(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class BailianConfig:
    """阿里百炼:Paraformer 实时 ASR + CosyVoice 实时 TTS。国内站 DashScope WS。"""

    api_key: str = ""
    asr_model: str = "paraformer-realtime-v2"
    ws_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
    sample_rate: int = 16000
    audio_format: str = "pcm"
    # CosyVoice TTS(高音质,付费档)
    tts_model: str = "cosyvoice-v2"
    tts_voice: str = "longxiaochun_v2"
    tts_format: str = "mp3"
    tts_sample_rate: int = 22050

    @property
    def ready(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class PlanConfig:
    """档位配置 → 付费等级(design.md §11/§24)。免费档为默认地板。"""

    text_history_turns: int = 10   # 文本历史轮数(可配 1/3/5/10…)
    image_history_frames: int = 1  # 视觉记忆帧数(付费档 5/10)
    continuous_analysis: bool = False  # 连续分析模式(会议辅助)


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default) or default


def build() -> tuple[MiniMaxConfig, BailianConfig, PlanConfig]:
    mm = MiniMaxConfig(
        base_url=_get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"),
        api_key=_clean(_get("MINIMAX_API_KEY")),
        llm_model=_get("MINIMAX_LLM_MODEL", "MiniMax-M3"),
    )
    bl = BailianConfig(
        api_key=_clean(_get("BAILIAN_API_KEY")),
        asr_model=_get("BAILIAN_ASR_MODEL", "paraformer-realtime-v2"),
        ws_url=_get("BAILIAN_WS_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/inference"),
        tts_model=_get("BAILIAN_TTS_MODEL", "cosyvoice-v2"),
        tts_voice=_get("BAILIAN_TTS_VOICE", "longxiaochun_v2"),
    )
    try:
        turns = int(_get("PLAN_TEXT_HISTORY_TURNS", "10"))
    except ValueError:
        turns = 10
    plan = PlanConfig(text_history_turns=max(1, turns))
    return mm, bl, plan


# 模块级当前生效配置(env 为底)
minimax, bailian, plan = build()


def status() -> dict[str, bool]:
    return {"minimax": minimax.ready, "bailian": bailian.ready}

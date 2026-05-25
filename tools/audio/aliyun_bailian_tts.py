"""Alibaba Cloud Model Studio (Bailian/DashScope) text-to-speech provider."""

from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class AliyunBailianTTS(BaseTool):
    name = "aliyun_bailian_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "aliyun_bailian"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = (
        "Set DASHSCOPE_API_KEY to your Alibaba Cloud Model Studio (Bailian) API key.\n"
        "Aliases also accepted: ALIYUN_BAILIAN_API_KEY or BAILIAN_API_KEY.\n"
        "Install the SDK with: pip install dashscope"
    )
    fallback = "google_tts"
    fallback_tools = ["google_tts", "doubao_tts", "elevenlabs_tts", "openai_tts", "piper_tts"]
    agent_skills = ["text-to-speech"]

    capabilities = [
        "text_to_speech",
        "voice_selection",
        "multilingual",
        "mandarin_narration",
    ]
    supports = {
        "voice_cloning": False,
        "multilingual": True,
        "offline": False,
        "native_audio": True,
        "streaming": False,
    }
    best_for = [
        "Mandarin narration through Alibaba Cloud Bailian",
        "Chinese-localized voice generation",
        "API-based production when DashScope access is available",
    ]
    not_good_for = [
        "fully offline production",
        "voice clone matching",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "description": "Text to convert to speech"},
            "voice": {
                "type": "string",
                "default": "Cherry",
                "description": "Bailian/Qwen TTS voice name. Qwen3 default is Cherry; Ethan is a good Mandarin male narration option. CosyVoice examples include longxiaochun.",
            },
            "model": {
                "type": "string",
                "default": "qwen3-tts-flash",
                "description": "Bailian TTS model. Default is qwen3-tts-flash.",
            },
            "format": {
                "type": "string",
                "default": "wav",
                "enum": ["mp3", "wav", "pcm"],
            },
            "sample_rate": {
                "type": "integer",
                "default": 24000,
                "description": "Output sample rate when supported by the selected model.",
            },
            "language_type": {
                "type": "string",
                "default": "Chinese",
                "description": "Qwen TTS language hint, e.g. Chinese or English.",
            },
            "instructions": {
                "type": "string",
                "description": "Optional delivery instructions for qwen3-tts-instruct-flash.",
            },
            "optimize_instructions": {
                "type": "boolean",
                "default": False,
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["text", "voice", "model", "format", "sample_rate"]
    side_effects = ["writes audio file to output_path", "calls Alibaba Cloud Bailian/DashScope API"]
    user_visible_verification = ["Listen to generated audio for Mandarin naturalness and pacing"]

    def _get_api_key(self) -> str | None:
        return (
            os.environ.get("DASHSCOPE_API_KEY")
            or os.environ.get("ALIYUN_BAILIAN_API_KEY")
            or os.environ.get("BAILIAN_API_KEY")
        )

    def get_status(self) -> ToolStatus:
        if not self._get_api_key():
            return ToolStatus.UNAVAILABLE
        try:
            import dashscope.audio.tts_v2  # noqa: F401
        except ImportError:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # Bailian pricing varies by model/region; keep a conservative placeholder
        # so cost accounting remains non-zero without pretending exact billing.
        return round(len(inputs.get("text", "")) * 0.00002, 4)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(success=False, error="No Bailian API key found. " + self.install_instructions)

        start = time.time()
        try:
            result = self._generate(inputs, api_key)
        except ImportError:
            return ToolResult(success=False, error="DashScope SDK is not installed. " + self.install_instructions)
        except Exception as exc:
            return ToolResult(success=False, error=f"Aliyun Bailian TTS failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        result.cost_usd = self.estimate_cost(inputs)
        return result

    def _generate(self, inputs: dict[str, Any], api_key: str) -> ToolResult:
        model = inputs.get("model", "qwen3-tts-flash")
        if str(model).startswith("qwen3-tts"):
            return self._generate_qwen_tts(inputs, api_key)
        return self._generate_cosyvoice(inputs, api_key)

    def _generate_qwen_tts(self, inputs: dict[str, Any], api_key: str) -> ToolResult:
        import dashscope
        import requests

        from tools.analysis.audio_probe import probe_duration

        text = inputs["text"]
        model = inputs.get("model", "qwen3-tts-flash")
        voice = inputs.get("voice", "Cherry")
        language_type = inputs.get("language_type", "Chinese")
        output_path = Path(inputs.get("output_path", "aliyun_bailian_tts.wav"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        kwargs: dict[str, Any] = {
            "model": model,
            "api_key": api_key,
            "text": text,
            "voice": voice,
            "language_type": language_type,
            "stream": False,
        }
        if inputs.get("instructions"):
            kwargs["instructions"] = inputs["instructions"]
            kwargs["optimize_instructions"] = bool(inputs.get("optimize_instructions", False))

        response = dashscope.MultiModalConversation.call(**kwargs)
        status_code = getattr(response, "status_code", None)
        if status_code and int(status_code) >= 400:
            code = getattr(response, "code", "")
            message = getattr(response, "message", "")
            raise RuntimeError(f"DashScope Qwen TTS request failed: {code} {message}".strip())

        audio_url = self._extract_qwen_audio_url(response)
        if not audio_url:
            raise RuntimeError(f"DashScope Qwen TTS response did not include output.audio.url: {response}")

        download = requests.get(audio_url, timeout=(10, 120))
        download.raise_for_status()

        if "output_path" not in inputs:
            suffix = self._suffix_from_url(audio_url) or ".wav"
            output_path = output_path.with_suffix(suffix)
        output_path.write_bytes(download.content)

        audio_duration = probe_duration(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "voice": voice,
                "format": output_path.suffix.lstrip(".") or "wav",
                "language_type": language_type,
                "text_length": len(text),
                "audio_duration_seconds": round(audio_duration, 2) if audio_duration else None,
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
            model=f"{model}/{voice}",
        )

    def _generate_cosyvoice(self, inputs: dict[str, Any], api_key: str) -> ToolResult:
        from dashscope.audio.tts_v2 import SpeechSynthesizer
        from dashscope.audio.tts_v2.speech_synthesizer import AudioFormat

        from tools.analysis.audio_probe import probe_duration

        text = inputs["text"]
        model = inputs.get("model", "cosyvoice-v1")
        voice = inputs.get("voice", "longxiaochun")
        fmt = inputs.get("format", "mp3")
        sample_rate = int(inputs.get("sample_rate", 24000))
        output_path = Path(inputs.get("output_path", f"aliyun_bailian_tts.{fmt}"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        audio_format = self._audio_format(AudioFormat, fmt, sample_rate)
        synthesizer_kwargs: dict[str, Any] = {
            "model": model,
            "voice": voice,
            "format": audio_format,
        }
        os.environ.setdefault("DASHSCOPE_API_KEY", api_key)
        os.environ.setdefault("ALIYUN_BAILIAN_API_KEY", api_key)
        os.environ.setdefault("BAILIAN_API_KEY", api_key)

        synthesizer = SpeechSynthesizer(**synthesizer_kwargs)
        audio = synthesizer.call(text)
        if not audio:
            raise RuntimeError("Bailian TTS returned empty audio data")

        if isinstance(audio, str):
            output_path.write_bytes(Path(audio).read_bytes())
        else:
            output_path.write_bytes(audio)

        audio_duration = probe_duration(output_path)

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "voice": voice,
                "format": fmt,
                "sample_rate": sample_rate,
                "text_length": len(text),
                "audio_duration_seconds": round(audio_duration, 2) if audio_duration else None,
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
            model=f"{model}/{voice}",
        )

    @staticmethod
    def _extract_qwen_audio_url(response: Any) -> str | None:
        output = getattr(response, "output", None)
        if output is None and isinstance(response, dict):
            output = response.get("output")
        audio = None
        if isinstance(output, dict):
            audio = output.get("audio")
        elif output is not None:
            audio = getattr(output, "audio", None)
        if isinstance(audio, dict):
            return audio.get("url")
        if audio is not None:
            return getattr(audio, "url", None)
        return None

    @staticmethod
    def _suffix_from_url(url: str) -> str | None:
        path = urlparse(url).path
        suffix = Path(path).suffix.lower()
        return suffix if suffix in {".wav", ".mp3", ".pcm", ".ogg"} else None

    @staticmethod
    def _audio_format(audio_format_enum: Any, fmt: str, sample_rate: int) -> Any:
        fmt = fmt.lower()
        sample_rate = int(sample_rate)
        if fmt == "mp3":
            bitrate = "128KBPS" if sample_rate in {8000, 16000} else "256KBPS"
            enum_name = f"MP3_{sample_rate}HZ_MONO_{bitrate}"
        elif fmt == "wav":
            enum_name = f"WAV_{sample_rate}HZ_MONO_16BIT"
        elif fmt == "pcm":
            enum_name = f"PCM_{sample_rate}HZ_MONO_16BIT"
        else:
            raise ValueError(f"Unsupported Bailian TTS format: {fmt}")

        value = getattr(audio_format_enum, enum_name, None)
        if value is None:
            supported = ", ".join(
                name for name in dir(audio_format_enum)
                if name.startswith(("MP3_", "WAV_", "PCM_"))
            )
            raise ValueError(f"Unsupported Bailian TTS audio format {enum_name}. Supported: {supported}")
        return value

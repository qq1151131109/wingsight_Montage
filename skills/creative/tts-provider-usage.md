# TTS Provider Usage

Use `tts_selector` for narration unless the user or approved production plan names a concrete provider. The selector reads live registry status; do not infer availability from old key assumptions.

## Runtime Notes

| Tool | Provider | Env | Notes |
|---|---|---|---|
| `aliyun_bailian_tts` | Alibaba Cloud Bailian / DashScope | `DASHSCOPE_API_KEY` | Configured on this machine. Default model is `qwen3-tts-flash`, default voice is `Cherry`. |
| `doubao_tts` | Volcengine Doubao Speech | `DOUBAO_SPEECH_API_KEY` | Strong Mandarin narration with async task flow and timing metadata. |
| `elevenlabs_tts` | ElevenLabs | `ELEVENLABS_API_KEY` | Premium expressive voice and voice cloning workflows. |
| `openai_tts` | OpenAI | `OPENAI_API_KEY` | General TTS fallback when OpenAI key is configured. |
| `piper_tts` | Local Piper | install only | Offline/free fallback, less expressive. |

`aliyun_bailian_tts` accepts `DASHSCOPE_API_KEY` first, with `ALIYUN_BAILIAN_API_KEY` and `BAILIAN_API_KEY` as aliases. Qwen3 TTS models use `dashscope.MultiModalConversation.call`; CosyVoice models use `dashscope.audio.tts_v2.SpeechSynthesizer`. If the provider fails, check DashScope SDK installation/version before treating it as a prompt or content problem.

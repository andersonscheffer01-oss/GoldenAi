from .models import ModelProfile


DEFAULT_MODELS = {
    ModelProfile.FAST: ("gemini", "gemini-3.8-flash"),
    ModelProfile.VOICE_FAST: ("groq", "qwen/qwen3.8-27b"),
    ModelProfile.GENERAL: ("gemini", "gemini-3.8-flash"),
    ModelProfile.DEEP: ("gemini", "gemini-3.1-pro-preview"),
    ModelProfile.CODING: ("groq", "qwen/qwen3.8-27b"),
    ModelProfile.VISION: ("ollama", "qwen2.5vl:7b"),
    ModelProfile.OFFLINE: ("ollama", "qwen2.5-coder:14b"),
}

PROVIDER_MODELS = {
    "groq": {
        ModelProfile.FAST: "qwen/qwen3.8-27b", ModelProfile.VOICE_FAST: "qwen/qwen3.8-27b",
        ModelProfile.GENERAL: "qwen/qwen3.8-27b",
        ModelProfile.DEEP: "openai/gpt-oss-120b", ModelProfile.CODING: "qwen/qwen3.8-27b"},
    "openrouter": {profile: "openrouter/free" for profile in ModelProfile},
    "gemini": {profile: ("gemini-3.1-pro-preview" if profile == ModelProfile.DEEP
                           else "gemini-3.8-flash") for profile in ModelProfile},
    "ollama": {profile: ("qwen2.5vl:7b" if profile == ModelProfile.VISION else
                           "qwen2.5-coder:14b") for profile in ModelProfile},
    "omniroute": {
        ModelProfile.FAST: "auto/fast", ModelProfile.VOICE_FAST: "auto/fast",
        ModelProfile.GENERAL: "auto", ModelProfile.DEEP: "auto/smart",
        ModelProfile.CODING: "auto/coding", ModelProfile.VISION: "auto",
        ModelProfile.OFFLINE: "auto/offline",
    },
}

PROVIDER_ORDER = ("groq", "openrouter", "gemini", "omniroute", "ollama")
MAX_TRANSIENT_RETRIES = 1
PROVIDER_TIMEOUT_SECONDS = 8.0
VOICE_FAST_TIMEOUT_SECONDS = 2.5
# Inferência local (CPU) é lenta: SECRET e fallbacks locais precisam de
# janela maior que os 8 s do cloud. VOICE_FAST local mantém 6 s (falha
# rápido em vez de travar a voz). Env: JARVIS_LOCAL_TIMEOUT_SECONDS.
LOCAL_TIMEOUT_SECONDS = 45.0

SECRET_MARKERS = frozenset({
    "password", "passwd", "senha", "token", "api_key", "apikey",
    "authorization", "cookie", "credential", "credentials", "secret",
})

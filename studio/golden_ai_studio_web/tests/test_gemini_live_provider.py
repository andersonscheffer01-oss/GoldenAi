import asyncio

import jarvis_core.voice_service as voice_service_module
from jarvis_core.gemini_live_provider import (
    GEMINI_LIVE_MODEL_CANDIDATES,
    GEMINI_LIVE_PREBUILT_VOICES,
    GeminiLiveConfig,
    GeminiLiveDuplexSession,
    GeminiLiveProvider,
    GoogleGenAILiveTransport,
    normalize_gemini_live_voice,
)
from jarvis_core.voice_service import VoiceService, _safe_voice_detail
from jarvis_core.personality_profiles import PERSONALITIES, get_personality
from jarvis_core.realtime_voice.audio_input import FakeAudioInputProvider


class FakeTransport:
    def __init__(self):
        self.connected = False
        self.sent = []
        self.interrupted = 0
        self.audio_ended = 0
        self.closed = False

    async def connect(self, **kwargs):
        self.connected = True
        self.connect_kwargs = kwargs

    async def send_audio(self, pcm):
        self.sent.append(bytes(pcm))

    async def end_audio(self):
        self.audio_ended += 1

    async def receive(self):
        yield b"chunk-1"
        yield b"chunk-2"

    async def interrupt(self):
        self.interrupted += 1

    async def close(self):
        self.closed = True


class FakeBlob:
    def __init__(self, *, data, mime_type):
        self.data = data
        self.mime_type = mime_type


class FakeLiveSession:
    def __init__(self):
        self.sent = []

    async def send_realtime_input(self, **kwargs):
        self.sent.append(kwargs)

    async def receive(self):
        message = type("Message", (), {})()
        message.server_content = type("Content", (), {})()
        message.server_content.model_turn = type("Turn", (), {})()
        part = type("Part", (), {})()
        part.inline_data = type("Inline", (), {"data": b"remote-audio"})()
        message.server_content.model_turn.parts = [part]
        yield message


class ExplicitAudioLiveSession:
    """SDK-shaped session exposing both fields explicitly."""

    def __init__(self):
        self.sent = []

    async def send_realtime_input(self, *, media=None, audio=None,
                                  audio_stream_end=None):
        self.sent.append({"media": media, "audio": audio,
                          "audio_stream_end": audio_stream_end})


class TurnedLiveSession:
    """The SDK ends receive() after turn_complete but keeps the session alive."""

    def __init__(self):
        self.calls = 0

    async def receive(self):
        self.calls += 1
        message = type("Message", (), {})()
        message.server_content = type("Content", (), {})()
        message.server_content.model_turn = type("Turn", (), {})()
        message.server_content.turn_complete = self.calls == 1
        part = type("Part", (), {})()
        part.inline_data = type("Inline", (), {"data": f"turn-{self.calls}".encode()})()
        message.server_content.model_turn.parts = [part]
        yield message


class DataOnlyLiveSession:
    """Matches the official LiveServerMessage.data convenience property."""

    def __init__(self):
        self.calls = 0

    async def receive(self):
        self.calls += 1
        if self.calls > 1:
            return
        message = type("Message", (), {})()
        message.data = b"official-data-audio"
        message.server_content = type("Content", (), {})()
        message.server_content.turn_complete = True
        yield message


class FakeLiveContext:
    def __init__(self):
        self.session = FakeLiveSession()
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.session

    async def __aexit__(self, *_args):
        self.exited = True


class SlowLiveContext(FakeLiveContext):
    async def __aenter__(self):
        await asyncio.sleep(1)
        return await super().__aenter__()


class ModelUnavailableContext:
    async def __aenter__(self):
        raise Exception("404 model not found")

    async def __aexit__(self, *_args):
        return None


class PrematureCloseContext:
    async def __aenter__(self):
        error = RuntimeError("no close frame received or sent")
        error.rcvd = type("Close", (), {"code": 1006, "reason": "abnormal closure"})()
        raise error

    async def __aexit__(self, *_args):
        return None


class FakeGenAIClient:
    def __init__(self, *, api_key):
        self.api_key = api_key
        self.context = FakeLiveContext()
        self.aio = type("Aio", (), {})()
        self.aio.live = type("Live", (), {})()
        def connect(**kwargs):
            self.connect_kwargs = kwargs
            return self.context
        self.aio.live.connect = connect


def test_provider_is_transport_injected_and_does_not_connect_on_init():
    transport = FakeTransport()
    provider = GeminiLiveProvider(transport=transport, config=GeminiLiveConfig(voice="Kore"))
    assert not provider.connected
    asyncio.run(provider.connect(system_instruction="estilo seguro"))
    asyncio.run(provider.send_audio(b"pcm"))
    asyncio.run(provider.end_audio())
    assert transport.connect_kwargs["voice"] == "Kore"
    assert transport.sent == [b"pcm"]
    assert transport.audio_ended == 1
    assert asyncio.run(_collect(provider)) == [b"chunk-1", b"chunk-2"]
    asyncio.run(provider.interrupt())
    asyncio.run(provider.close())
    assert transport.interrupted == 1 and transport.closed


def test_voice_service_routes_canonical_frames_to_gemini_and_bounded_output(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_LIVE", "1")

    class FakeLive:
        def __init__(self):
            self.connected = True
            self.sent = []
            self.audio_ended = 0
            self.responses = asyncio.Queue()

        def diagnostics(self):
            return {"started": True, "provider": {"connected": True}}

        async def send_audio(self, pcm):
            self.sent.append(bytes(pcm))

        async def end_audio(self):
            self.audio_ended += 1

        async def receive_audio(self):
            return await self.responses.get()

        async def interrupt(self):
            return None

    class FakeOutput:
        is_active = True

        def __init__(self):
            self.chunks = []
            self.cancelled = False

        def enqueue(self, chunk):
            self.chunks.append(chunk)
            return True

        def cancel(self, _reason=""):
            self.cancelled = True
            self.is_active = False

    async def exercise():
        service = VoiceService()
        live = FakeLive()
        output = FakeOutput()
        service.attach_gemini_live_provider(live)
        holder = {}

        def factory(**kwargs):
            provider = FakeAudioInputProvider(**kwargs)
            holder["provider"] = provider
            return provider

        started = await service.start_gemini_live_audio(
            device="usb-test", output=output, provider_factory=factory)
        holder["provider"].emit_frame(b"\x01" * 960)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await live.responses.put(b"\x02" * 480)
        await asyncio.sleep(0)
        metrics = service.gemini_audio_status()["metrics"]
        assert "output" in service.gemini_audio_status()
        capture_stopped = await service.stop_gemini_live_capture()
        stopped = await service.stop_gemini_live_audio()
        return started, capture_stopped, stopped, live, output, metrics

    started, capture_stopped, stopped, live, output, metrics = asyncio.run(exercise())
    assert started["ok"] is True
    assert capture_stopped["ok"] is True
    assert live.audio_ended == 1
    assert live.sent == [b"\x01" * 960]
    assert metrics["frames_sent"] == 1
    assert metrics["audio_chunks_received"] == 1
    assert output.chunks[0].sample_rate == 24000
    assert stopped["stopped"] is True and output.cancelled


def test_stopping_gemini_audio_clears_preview_marker():
    async def exercise():
        service = VoiceService()
        service._gemini_preview_active = True
        service._gemini_preview_text = "preview"
        await service.stop_gemini_live_audio()
        return service.gemini_audio_status()

    status = asyncio.run(exercise())
    assert status["preview_active"] is False


def test_gemini_output_bridge_uses_burst_buffer_for_native_live(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_LIVE", "1")
    created = {}

    class FakeOutput:
        is_active = True

        def __init__(self, **kwargs):
            created.update(kwargs)

        def enqueue(self, chunk):
            del chunk
            return True

        def cancel(self, _reason=""):
            self.is_active = False

    class FakeLive:
        connected = True

        def __init__(self):
            self.responses = asyncio.Queue()

        def diagnostics(self):
            return {"started": True, "provider": {"connected": True}}

        async def receive_audio(self):
            return await self.responses.get()

    monkeypatch.setattr(voice_service_module, "SoundDeviceAudioOutputProvider", FakeOutput)

    async def exercise():
        service = VoiceService()
        live = FakeLive()
        service.attach_gemini_live_provider(live)
        started = await service.start_gemini_live_audio(capture=False)
        await live.responses.put(b"\x01" * 480)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await service.stop_gemini_live_audio()
        return started

    started = asyncio.run(exercise())
    assert started["ok"] is True
    assert created["maxsize"] == 128
    assert created["startup_silence_ms"] == 120


def test_gemini_interrupt_cancels_output_and_allows_next_turn_to_recreate_sink():
    class FakeOutput:
        is_active = True

        def __init__(self):
            self.cancelled = False

        def cancel(self, _reason=""):
            self.cancelled = True
            self.is_active = False

    class FakeLive:
        connected = True

        def diagnostics(self):
            return {"started": True, "provider": {"connected": True}}

        async def interrupt(self):
            return None

    async def exercise():
        service = VoiceService()
        live = FakeLive()
        service.attach_gemini_live_provider(live)
        output = FakeOutput()
        service._gemini_output = output
        result = await service.interrupt_gemini_live_audio()
        return result, output, service._gemini_output

    result, output, current = asyncio.run(exercise())
    assert result["ok"] is True
    assert output.cancelled is True
    assert current is None


def test_gemini_ptt_mutes_capture_without_disabling_native_output_bridge(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_LIVE", "1")

    class FakeLive:
        connected = True

        def diagnostics(self):
            return {"started": True, "provider": {"connected": True}}

        async def receive_audio(self):
            return await asyncio.Queue().get()

    async def exercise():
        service = VoiceService()
        service.attach_gemini_live_provider(FakeLive())
        holder = {}

        def factory(**kwargs):
            provider = FakeAudioInputProvider(**kwargs)
            holder["provider"] = provider
            return provider

        bridge = await service.start_gemini_live_audio(capture=False)
        started = await service.start_gemini_live_capture(
            device="usb-test", provider_factory=factory)
        muted = await service.stop_gemini_live_capture()
        bridge_active = muted["audio"]["bridge_active"]
        await service.stop_gemini_live_audio()
        return bridge, started, muted, bridge_active

    bridge, started, muted, bridge_active = asyncio.run(exercise())
    assert bridge["ok"] is True and bridge["capture"] is False
    assert started["ok"] is True and started["capture"] is True
    assert muted["ok"] is True and muted["capture"] is False
    assert bridge_active is True


def test_voice_service_sends_typed_turn_through_existing_live_audio_owner(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_LIVE", "1")

    class FakeLive:
        connected = True

        def __init__(self):
            self.sent = []

        def diagnostics(self):
            return {"started": True, "provider": {"connected": True}}

        async def send_text(self, text):
            self.sent.append(text)

    async def exercise():
        service = VoiceService()
        live = FakeLive()
        service.attach_gemini_live_provider(live)
        service._audio_input_provider = type("Input", (), {"is_running": True})()
        service._gemini_audio_queue = asyncio.Queue()
        service._gemini_audio_receiver = type("Receiver", (), {"done": lambda self: False})()
        result = await service.send_gemini_live_text("pergunta escrita")
        return result, live.sent

    result, sent = asyncio.run(exercise())
    assert result["ok"] is True
    assert result["text_sent"] is True
    assert sent == ["pergunta escrita"]


def test_official_transport_is_lazy_authenticated_and_audio_only():
    clients = []

    def factory(**kwargs):
        client = FakeGenAIClient(**kwargs)
        clients.append(client)
        return client

    transport = GoogleGenAILiveTransport(
        model="gemini-live-test",
        credential_provider=lambda: "local-test-key",
        client_factory=factory,
        blob_factory=FakeBlob,
    )

    async def exercise():
        await transport.connect(voice="Aoede", language="pt-BR", system_instruction="seguro")
        await transport.send_audio(b"pcm")
        chunks = [chunk async for chunk in transport.receive()]
        await transport.interrupt()
        await transport.close()
        return chunks

    assert asyncio.run(exercise()) == [b"remote-audio"]
    assert clients[0].api_key == "local-test-key"
    sent = clients[0].context.session.sent[0]
    assert sent["media"].data == b"pcm"
    assert sent["media"].mime_type == "audio/pcm;rate=16000"
    assert clients[0].connect_kwargs["config"]["speech_config"]["language_code"] == "pt-BR"
    config = clients[0].connect_kwargs["config"]
    assert "thinking_config" not in config
    assert "proactive_audio" not in config
    assert "enable_affective_dialog" not in config
    assert clients[0].context.exited is True


def test_official_transport_prefers_audio_field_for_explicit_sdk_signature():
    session = ExplicitAudioLiveSession()
    transport = GoogleGenAILiveTransport(
        model="gemini-live-test", credential_provider=lambda: "local-test-key",
        client_factory=lambda **kwargs: FakeGenAIClient(**kwargs), blob_factory=FakeBlob,
    )
    transport._session = session
    transport._types = type("Types", (), {"Blob": FakeBlob})

    asyncio.run(transport.send_audio(b"pcm"))

    assert session.sent[0]["audio"].data == b"pcm"
    assert session.sent[0]["media"] is None


def test_voice_service_audio_sender_records_failure_and_stops_capture():
    class BrokenProvider:
        connected = True

        async def send_audio(self, _pcm):
            raise RuntimeError("received 1007 invalid argument")

        def diagnostics(self):
            return {"transport": {"last_error": "gemini_live_transport_send_failed: 1007"}}

    class InputProvider:
        is_running = True

        def __init__(self):
            self.stopped = 0

        def stop(self):
            self.stopped += 1
            self.is_running = False

    async def exercise():
        service = VoiceService()
        service._gemini_live_provider = BrokenProvider()
        service._gemini_audio_queue = asyncio.Queue()
        input_provider = InputProvider()
        service._audio_input_provider = input_provider
        task = asyncio.create_task(service._gemini_send_loop())
        await service._gemini_audio_queue.put(b"pcm")
        await task
        return service, input_provider, service._gemini_audio_queue.qsize()

    service, input_provider, queue_size = asyncio.run(exercise())
    assert input_provider.stopped == 1
    assert queue_size == 0
    assert service._last_recovery["error"] == "GEMINI_LIVE_AUDIO_SEND_FAILED"
    assert "1007" in service._last_recovery["detail"]


def test_official_transport_reopens_receive_iterator_after_turn_complete():
    transport = GoogleGenAILiveTransport(
        model="gemini-live-test", credential_provider=lambda: "local-test-key",
        client_factory=lambda **kwargs: FakeGenAIClient(**kwargs), blob_factory=FakeBlob,
    )
    session = TurnedLiveSession()
    transport._session = session

    chunks = asyncio.run(_collect_transport(transport))

    assert chunks == [b"turn-1", b"turn-2"]
    assert session.calls == 2
    assert transport.diagnostics()["turn_complete_events"] == 1


def test_official_transport_publishes_interim_transcript_at_generation_boundary():
    class TranscriptSession:
        def __init__(self):
            self.calls = 0

        async def receive(self):
            self.calls += 1
            if self.calls > 1:
                return
            message = type("Message", (), {})()
            content = type("Content", (), {})()
            content.interim_input_transcription = type("Transcription", (), {"text": "olá Jarvis"})()
            content.generation_complete = True
            content.model_turn = type("Turn", (), {"parts": []})()
            message.server_content = content
            yield message

    transport = GoogleGenAILiveTransport(
        model="gemini-live-test", credential_provider=lambda: "local-test-key"
    )
    transport._session = TranscriptSession()
    assert asyncio.run(_collect_transport(transport)) == []
    transcription = transport.diagnostics()["transcription"]
    assert transcription["input"] == "olá Jarvis"
    assert transcription["sequence"] == 1


def test_text_preview_sends_an_explicit_user_role():
    class CaptureSession:
        async def send_client_content(self, **kwargs):
            self.kwargs = kwargs

    class Part:
        def __init__(self, *, text):
            self.text = text

    class Content:
        def __init__(self, *, role, parts):
            self.role = role
            self.parts = parts

    transport = GoogleGenAILiveTransport(
        model="gemini-live-test", credential_provider=lambda: "local-test-key"
    )
    session = CaptureSession()
    transport._session = session
    transport._types = type("Types", (), {"Content": Content, "Part": Part})
    asyncio.run(transport.send_text("teste"))
    content = session.kwargs["turns"][0]
    assert content.role == "user"
    assert content.parts[0].text == "teste"
    assert session.kwargs["turn_complete"] is True


def test_setup_only_uses_minimal_audio_config_and_closes_without_receiver():
    clients = []

    def factory(**kwargs):
        client = FakeGenAIClient(**kwargs)
        clients.append(client)
        return client

    transport = GoogleGenAILiveTransport(
        model="gemini-live-test", credential_provider=lambda: "local-test-key",
        client_factory=factory, blob_factory=FakeBlob,
    )
    result = asyncio.run(transport.setup_only(timeout_seconds=1))
    assert result["ok"] is True
    assert result["setup_only"] is True
    assert clients[0].connect_kwargs["config"] == {"response_modalities": ["AUDIO"]}
    events = [item["event"] for item in result["diagnostics"]["lifecycle_events"]]
    assert events == ["CONNECT_START", "SETUP_COMPLETE", "SESSION_CLOSED"]
    assert clients[0].context.exited is True
    assert transport._session is None


def test_real_client_factory_receives_explicit_v1beta_without_changing_setup_config():
    captured = {}

    class FakeHttpOptions:
        def __init__(self, *, api_version):
            self.api_version = api_version

    class FakeTypes:
        HttpOptions = FakeHttpOptions

    def factory(*, api_key, http_options, vertexai):
        captured["api_key"] = api_key
        captured["http_options"] = http_options
        captured["vertexai"] = vertexai
        return FakeGenAIClient(api_key=api_key)

    transport = GoogleGenAILiveTransport(
        model="gemini-3.8-live", credential_provider=lambda: "local-test-key",
        client_factory=factory, blob_factory=FakeBlob,
    )
    transport._types = FakeTypes
    result = asyncio.run(transport.setup_only(timeout_seconds=1))

    assert result["ok"] is True
    assert captured["api_key"] == "local-test-key"
    assert captured["http_options"].api_version == "v1beta"
    assert captured["vertexai"] is False
    assert result["diagnostics"]["runtime"]["api_version"] == "v1beta"
    assert result["diagnostics"]["model"] == "gemini-3.8-live"


def test_setup_only_exposes_sanitized_runtime_and_credential_metadata():
    clients = []

    def factory(**kwargs):
        client = FakeGenAIClient(**kwargs)
        client._api_client = type("ApiClient", (), {})()
        client._api_client._http_options = type("HttpOptions", (), {"api_version": "v1beta"})()
        clients.append(client)
        return client

    transport = GoogleGenAILiveTransport(
        model="gemini-3.8-live", credential_provider=lambda: "local-test-secret",
        client_factory=factory, blob_factory=FakeBlob,
        runtime_instance_id="runtime-test-123",
    )
    result = asyncio.run(transport.setup_only(timeout_seconds=1))
    diagnostics = result["diagnostics"]
    assert diagnostics["credential"] == {
        "present": True, "resolution": "succeeded", "error_category": None,
    }
    assert diagnostics["runtime"]["api_version"] == "v1beta"
    assert diagnostics["runtime"]["model"] == "gemini-3.8-live"
    assert diagnostics["runtime"]["runtime_instance_id"] == "runtime-test-123"
    assert diagnostics["runtime"]["correlation_id"]
    assert diagnostics["correlation_id"] == diagnostics["session_id"]
    assert "local-test-secret" not in repr(diagnostics)
    assert [event["event"] for event in diagnostics["lifecycle_events"]] == [
        "CONNECT_START", "SETUP_COMPLETE", "SESSION_CLOSED",
    ]


def test_connection_diagnostics_expose_backend_loop_and_only_environment_presence(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "https://secret-proxy.example.invalid/token")
    monkeypatch.setenv("SSL_CERT_FILE", "C:\\private\\ca.pem")
    transport = GoogleGenAILiveTransport(
        model="gemini-3.8-live", credential_provider=lambda: "local-test-secret",
        client_factory=lambda **kwargs: FakeGenAIClient(**kwargs), blob_factory=FakeBlob,
    )
    result = asyncio.run(transport.setup_only(timeout_seconds=1))
    diagnostics = result["diagnostics"]
    connection = diagnostics["connection"]
    assert connection["backend"] == "gemini_developer_api"
    assert connection["event_loop_class"]
    assert connection["event_loop_policy"]
    assert connection["proxy_env_present"]["HTTPS_PROXY"] is True
    assert connection["tls_env_present"]["SSL_CERT_FILE"] is True
    assert "secret-proxy" not in repr(diagnostics)
    assert "private" not in repr(diagnostics)
    assert "local-test-secret" not in repr(diagnostics)


def test_credential_resolution_failure_is_categorized_without_secret_details():
    def denied_credential():
        raise RuntimeError("DPAPI_UNAVAILABLE: secret material omitted")

    transport = GoogleGenAILiveTransport(
        model="gemini-3.8-live", credential_provider=denied_credential,
        client_factory=lambda **kwargs: FakeGenAIClient(**kwargs), blob_factory=FakeBlob,
    )
    try:
        asyncio.run(transport.setup_only(timeout_seconds=1))
    except RuntimeError as exc:
        assert str(exc) == "DPAPI_UNAVAILABLE: secret material omitted"
    else:
        raise AssertionError("credential failure was accepted")
    diagnostics = transport.diagnostics()
    assert diagnostics["phase"] == "credential"
    assert diagnostics["credential"] == {
        "present": None, "resolution": "failed", "error_category": "dpapi_error",
    }
    assert diagnostics["last_error"] == "gemini_live_credential_resolution_failed"
    assert "secret material" not in repr(diagnostics)
    assert [event["event"] for event in diagnostics["lifecycle_events"]] == [
        "CONNECT_START", "AUTH_ERROR", "SESSION_CLOSED",
    ]


def test_setup_only_timeout_emits_sanitized_lifecycle_and_closes():
    def factory(**kwargs):
        client = FakeGenAIClient(**kwargs)
        client.context = SlowLiveContext()
        client.aio.live.connect = lambda **_kwargs: client.context
        return client

    transport = GoogleGenAILiveTransport(
        model="gemini-live-test", credential_provider=lambda: "local-test-key",
        client_factory=factory, blob_factory=FakeBlob,
    )
    try:
        asyncio.run(transport.setup_only(timeout_seconds=0.01))
    except RuntimeError as exc:
        assert str(exc) == "gemini_live_setup_timeout"
    else:
        raise AssertionError("setup-only timeout did not fail")
    events = [item["event"] for item in transport.diagnostics()["lifecycle_events"]]
    assert events == ["CONNECT_START", "TIMEOUT", "SESSION_CLOSED"]
    assert transport.diagnostics()["last_error_category"] == "timeout"


def test_setup_only_preserves_premature_websocket_close_stage_and_code():
    def factory(**kwargs):
        client = FakeGenAIClient(**kwargs)
        client.context = PrematureCloseContext()
        client.aio.live.connect = lambda **_kwargs: client.context
        return client

    transport = GoogleGenAILiveTransport(
        model="gemini-3.8-live", credential_provider=lambda: "local-test-key",
        client_factory=factory, blob_factory=FakeBlob,
    )
    try:
        asyncio.run(transport.setup_only(timeout_seconds=1))
    except RuntimeError as exc:
        assert str(exc) == "no close frame received or sent"
    else:
        raise AssertionError("premature close was accepted")
    diagnostics = transport.diagnostics()
    assert diagnostics["phase"] == "setup_wait"
    assert diagnostics["last_error_category"] == "websocket_closed"
    assert diagnostics["close_code"] == 1006
    assert diagnostics["remote_close_reason"] == "abnormal closure"
    assert diagnostics["lifecycle_events"][1]["event"] == "CLOSED_BEFORE_SETUP"


def test_transport_classifies_tls_and_proxy_failures_without_network_access():
    assert GoogleGenAILiveTransport._error_category(Exception("TLS certificate verify failed")) == "tls_error"
    assert GoogleGenAILiveTransport._error_category(Exception("proxy connection socket failure")) == "network_error"


def test_official_transport_consumes_sdk_data_property_without_duplicate_structured_audio():
    transport = GoogleGenAILiveTransport(
        model="gemini-live-test", credential_provider=lambda: "local-test-key",
        client_factory=lambda **kwargs: FakeGenAIClient(**kwargs), blob_factory=FakeBlob,
    )
    transport._session = DataOnlyLiveSession()

    assert asyncio.run(_collect_transport(transport)) == [b"official-data-audio"]
    assert transport.diagnostics()["audio_events"] == 1


async def _collect_transport(transport):
    return [chunk async for chunk in transport.receive()]


def test_official_transport_rejects_missing_credentials_without_client_creation():
    created = []

    def factory(**kwargs):
        created.append(kwargs)
        return FakeGenAIClient(**kwargs)

    transport = GoogleGenAILiveTransport(
        model="gemini-live-test",
        credential_provider=lambda: "",
        client_factory=factory,
        blob_factory=FakeBlob,
    )
    try:
        asyncio.run(transport.connect(voice="Aoede", language="pt-BR", system_instruction="seguro"))
    except RuntimeError as exc:
        assert str(exc) == "gemini_live_credentials_missing"
    else:
        raise AssertionError("missing credentials were accepted")
    assert created == []


def test_native_audio_model_omits_explicit_language_code():
    clients = []

    def factory(**kwargs):
        client = FakeGenAIClient(**kwargs)
        clients.append(client)
        return client

    transport = GoogleGenAILiveTransport(
        model="gemini-3.8-live", credential_provider=lambda: "local-test-key",
        client_factory=factory, blob_factory=FakeBlob,
    )
    asyncio.run(transport.connect(voice="Fenrir", language="pt-BR", system_instruction="seguro"))
    assert "language_code" not in clients[0].connect_kwargs["config"]["speech_config"]


def test_model_candidates_keep_primary_and_deduplicate_alternatives():
    transport = GoogleGenAILiveTransport(
        model=GEMINI_LIVE_MODEL_CANDIDATES[0],
        model_candidates=GEMINI_LIVE_MODEL_CANDIDATES + (GEMINI_LIVE_MODEL_CANDIDATES[0],),
        credential_provider=lambda: "local-test-key",
        client_factory=lambda **kwargs: FakeGenAIClient(**kwargs),
        blob_factory=FakeBlob,
    )
    assert transport.diagnostics()["model_candidates"] == list(GEMINI_LIVE_MODEL_CANDIDATES)


def test_connection_closed_is_not_classified_as_model_fallback():
    transport = GoogleGenAILiveTransport(
        model="gemini-3.8-live", credential_provider=lambda: "local-test-key"
    )
    assert transport._error_category(Exception("ConnectionClosedError: no close frame received")) == "websocket_closed"
    assert transport._error_category(
        Exception("received 1007 (invalid frame payload data) Request contains an invalid argument")
    ) == "configuration_invalid"


def test_voice_service_diagnostic_boundary_redacts_credentials_and_tokens():
    detail = _safe_voice_detail(
        "https://example.test/live?key=fake-provider-key-1234567890&token=fake-token"
    )
    assert "fake-provider-key" not in detail
    assert "token=fake-token" not in detail
    assert "[REDACTED]" in detail


def test_model_specific_rejection_can_fallback_once():
    clients = []

    def factory(**kwargs):
        client = FakeGenAIClient(**kwargs)
        if not clients:
            client.context = ModelUnavailableContext()
        clients.append(client)
        return client

    transport = GoogleGenAILiveTransport(
        model="gemini-3.8-live",
        model_candidates=("gemini-3.8-live", "gemini-3.1-flash-live-preview"),
        credential_provider=lambda: "local-test-key",
        client_factory=factory,
        blob_factory=FakeBlob,
    )
    asyncio.run(transport.connect(voice="Fenrir", language="pt-BR", system_instruction="seguro"))
    diagnostics = transport.diagnostics()
    assert diagnostics["model_attempts"] == ["gemini-3.8-live", "gemini-3.1-flash-live-preview"]
    assert diagnostics["model"] == "gemini-3.1-flash-live-preview"
    assert diagnostics["model_fallbacks"][0]["reason"] == "model_unavailable"


async def _collect(provider):
    return [chunk async for chunk in provider.receive_audio()]


def test_provider_reconnect_and_metrics():
    transport = FakeTransport()
    provider = GeminiLiveProvider(transport=transport)
    asyncio.run(provider.connect())
    asyncio.run(provider.reconnect())
    assert provider.metrics.reconnects == 1
    assert provider.diagnostics()["fallback_available"] is False


def test_provider_disconnect_is_reusable_and_close_remains_terminal():
    transport = FakeTransport()
    provider = GeminiLiveProvider(transport=transport)

    async def exercise():
        await provider.connect()
        await provider.disconnect()
        reusable = provider.diagnostics()
        await provider.connect()
        await provider.close()
        terminal = provider.diagnostics()
        return reusable, terminal

    reusable, terminal = asyncio.run(exercise())
    assert reusable["connected"] is False
    assert reusable["closed"] is False
    assert terminal["closed"] is True


def test_provider_diagnostics_include_transport_error_metadata_without_failing_status():
    class DiagnosticTransport(FakeTransport):
        def diagnostics(self):
            return {"last_error": "HTTP 401 key=[REDACTED]", "last_error_class": "AuthError", "close_code": 1008}

    provider = GeminiLiveProvider(transport=DiagnosticTransport())
    diagnostics = provider.diagnostics()
    assert diagnostics["transport"]["last_error_class"] == "AuthError"
    assert diagnostics["transport"]["close_code"] == 1008


def test_duplex_session_is_bounded_and_interruptible_without_remote_transport():
    transport = FakeTransport()
    provider = GeminiLiveProvider(
        transport=transport,
        config=GeminiLiveConfig(voice="Charon", system_instruction="seguro"),
    )
    async def exercise():
        session = GeminiLiveDuplexSession(provider, max_output_chunks=2)
        started = await session.start()
        await session.send_audio(b"pcm")
        first = await session.receive_audio()
        second = await session.receive_audio()
        await session.interrupt()
        diagnostics = session.diagnostics()
        await session.close()
        return started, first, second, diagnostics
    started, first, second, diagnostics = asyncio.run(exercise())
    assert started["ok"] is True
    assert (first, second) == (b"chunk-1", b"chunk-2")
    assert diagnostics["provider"]["metrics"]["sent_chunks"] == 1
    assert transport.interrupted == 1 and transport.closed


def test_duplex_session_reconnects_without_creating_a_second_provider():
    transport = FakeTransport()
    provider = GeminiLiveProvider(transport=transport)

    async def exercise():
        session = GeminiLiveDuplexSession(provider)
        await session.start()
        result = await session.reconnect(system_instruction="reconectar com segurança")
        diagnostics = session.diagnostics()
        await session.close()
        return result, diagnostics

    result, diagnostics = asyncio.run(exercise())
    assert result["ok"] is True
    assert result["reconnected"] is True
    assert result["generation"] == 2
    assert diagnostics["provider"]["metrics"]["reconnects"] == 1


def test_duplex_disconnect_keeps_singleton_session_reusable():
    transport = FakeTransport()
    provider = GeminiLiveProvider(transport=transport)
    session = GeminiLiveDuplexSession(provider)

    async def exercise():
        await session.start()
        await session.disconnect()
        after_disconnect = session.diagnostics()
        restarted = await session.start()
        await session.close()
        return after_disconnect, restarted

    after_disconnect, restarted = asyncio.run(exercise())
    assert after_disconnect["started"] is False
    assert after_disconnect["provider"]["closed"] is False
    assert restarted["started"] is True
    assert restarted["generation"] == 2


def test_voice_service_keeps_gemini_live_disabled_without_local_effective_mode():
    transport = FakeTransport()
    provider = GeminiLiveProvider(transport=transport)
    service = VoiceService()
    service.attach_gemini_live_provider(provider)
    profile = service.configure_conversation_profile(personality="mordomo", voice="Kore")
    assert profile["personality"] == "mordomo"
    assert profile["voice"] == "Kore"
    assert profile["effective_mode"] == "gemini_live_unavailable"
    result = asyncio.run(service.connect_gemini_live())
    assert result["ok"] is False
    assert result["error"] == "GEMINI_LIVE_DISABLED"
    assert transport.connected is False


def test_gemini_voice_catalog_rejects_invalid_names_before_network():
    assert {"Charon", "Sulafat", "Sadachbia", "Sadaltager"}.issubset(GEMINI_LIVE_PREBUILT_VOICES)
    assert normalize_gemini_live_voice(" Charon ") == "Charon"
    try:
        normalize_gemini_live_voice("not-a-gemini-voice")
    except ValueError as exc:
        assert str(exc) == "GEMINI_VOICE_UNSUPPORTED"
    else:
        raise AssertionError("unsupported voice was accepted")


def test_voice_change_during_live_session_requests_bounded_reconnect():
    class ConnectedLive:
        connected = True
        provider = None

    service = VoiceService()
    service.attach_gemini_live_provider(ConnectedLive())
    result = service.configure_conversation_profile(voice="Kore")
    assert result["voice"] == "Kore"
    assert result["voice_change_requires_reconnect"] is True
    assert result["voice_change_scope"] == "current_session_reconnect"
    assert result["profile_change_requires_reconnect"] is True


def test_voice_service_rejects_invalid_profile_without_mutating_voice():
    service = VoiceService()
    before = service.conversation_profile()["voice"]
    try:
        service.configure_conversation_profile(voice="invalid-voice")
    except ValueError as exc:
        assert str(exc) == "GEMINI_VOICE_UNSUPPORTED"
    else:
        raise AssertionError("invalid profile voice was accepted")
    assert service.conversation_profile()["voice"] == before


def test_voice_service_routes_enabled_session_without_tool_authority(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_LIVE", "1")
    transport = FakeTransport()
    provider = GeminiLiveProvider(transport=transport)
    session = GeminiLiveDuplexSession(provider)
    service = VoiceService()
    service.attach_gemini_live_provider(session)

    async def exercise():
        connected = await service.connect_gemini_live()
        sent = await service.send_gemini_live_audio(b"pcm")
        received = await service.receive_gemini_live_audio()
        interrupted = await service.interrupt_gemini_live()
        await service.disconnect_gemini_live()
        return connected, sent, received, interrupted

    connected, sent, received, interrupted = asyncio.run(exercise())
    assert connected["ok"] is True
    assert sent == {"ok": True, "bytes": 3}
    assert received["ok"] is True
    assert received["pcm"] in {b"chunk-1", b"chunk-2"}
    assert interrupted["interrupted"] is True
    assert transport.sent == [b"pcm"]


def test_all_cyberbot_personalities_are_presentation_only_catalog_entries():
    expected = {"equilibrado", "brincalhao", "ignorante", "malandro", "profissional",
                "rigoroso", "mordomo", "amigo", "direto", "motivador", "narrador",
                "amoroso", "sarcastico"}
    assert set(PERSONALITIES) == expected
    assert get_personality("unknown").id == "equilibrado"

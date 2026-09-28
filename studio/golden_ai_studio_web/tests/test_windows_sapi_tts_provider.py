"""Focused Windows SAPI provider tests.

Mock tests never touch COM or audio devices.  The real test renders one
bounded sample into SAPI memory only and is skipped outside Windows.
"""

from __future__ import annotations

import struct
import sys
from types import SimpleNamespace

import pytest

from jarvis_core.voice_foundation import VoiceCancellation, VoiceCancelledError
from jarvis_core.voice_tts import (
    FakeAudioOutputProvider,
    TextToSpeechProvider,
    VoiceAudioPipeline,
    WindowsSapiTTSProvider,
)


class _FakePythonCom:
    def __init__(self):
        self.initialized = 0
        self.uninitialized = 0

    def CoInitialize(self):
        self.initialized += 1

    def CoUninitialize(self):
        self.uninitialized += 1


class _FakeToken:
    def __init__(self, description="Microsoft Maria Desktop - Portuguese(Brazil)", language="416"):
        self.description = description
        self.language = language

    def GetDescription(self):
        return self.description

    def GetAttribute(self, name):
        return self.language if name == "Language" else ""


class _FakeTokens:
    def __init__(self, tokens):
        self._tokens = list(tokens)
        self.Count = len(self._tokens)

    def Item(self, index):
        return self._tokens[index]


class _FakeWaveFormat:
    FormatTag = 1
    Channels = 1
    SamplesPerSec = 22050
    AvgBytesPerSec = 44100
    BlockAlign = 2
    BitsPerSample = 16


class _FakeMemoryStream:
    def __init__(self, wave_format=None, data=None):
        self.Format = SimpleNamespace(
            Type=22,
            GetWaveFormatEx=lambda: wave_format or _FakeWaveFormat(),
        )
        self._data = data or struct.pack("<hhhh", 0, 1000, -1000, 2000)

    def GetData(self):
        return self._data


class _FakeVoice:
    def __init__(self, tokens, speak_failure=None):
        self._tokens = _FakeTokens(tokens)
        self.AudioOutputStream = None
        self.Voice = None
        self.spoken = []
        self.speak_failure = speak_failure

    def GetVoices(self):
        return self._tokens

    def Speak(self, text):
        if self.speak_failure is not None:
            raise self.speak_failure
        self.spoken.append(text)


class _FakeDispatch:
    def __init__(self, *, tokens=None, wave_format=None, data=None, failure=None, speak_failure=None):
        self.voice = _FakeVoice(tokens or [_FakeToken()], speak_failure=speak_failure)
        self.stream = _FakeMemoryStream(wave_format=wave_format, data=data)
        self.failure = failure

    def __call__(self, name):
        if self.failure is not None:
            raise self.failure
        if name == "SAPI.SpVoice":
            return self.voice
        if name == "SAPI.SpMemoryStream":
            return self.stream
        raise AssertionError(name)


def _provider(**kwargs):
    pythoncom = _FakePythonCom()
    dispatch = _FakeDispatch(**kwargs)
    provider = WindowsSapiTTSProvider(
        dispatch=dispatch,
        pythoncom_module=pythoncom,
    )
    return provider, dispatch, pythoncom


def test_sapi_provider_selects_exact_voice_and_matches_contract():
    provider, dispatch, pythoncom = _provider(
        tokens=[_FakeToken("Microsoft Zira Desktop - English (United States)") , _FakeToken()]
    )

    provider.warm()
    chunks = list(provider.stream(
        "Olá. Esta é uma validação em português do Brasil. ç ã õ á é í ó ú 123.",
        cancellation=VoiceCancellation(),
        session_id="session-1",
        turn_id=2,
        generation=3,
    ))

    assert isinstance(provider, TextToSpeechProvider)
    assert dispatch.voice.Voice.description == provider.DEFAULT_VOICE_DESCRIPTION
    assert dispatch.voice.spoken[0].startswith("Olá.")
    assert len(chunks) == 1
    assert chunks[0].identity == ("session-1", 2, 3)
    assert chunks[0].sample_rate == 22050
    assert chunks[0].channels == 1
    assert chunks[0].sample_format == "s16le"
    assert chunks[0].is_final is True
    assert chunks[0].metadata["container"] == "raw_pcm"
    assert pythoncom.initialized == pythoncom.uninitialized == 2


def test_sapi_provider_rejects_missing_voice_without_fallback():
    provider, _, _ = _provider(tokens=[_FakeToken("Microsoft Zira Desktop - English (United States)")])

    with pytest.raises(RuntimeError, match="sapi_voice_not_found"):
        provider.warm()


def test_sapi_provider_rejects_unsupported_output_format():
    provider, _, _ = _provider(wave_format=SimpleNamespace(
        FormatTag=6,
        Channels=1,
        SamplesPerSec=22050,
        BlockAlign=2,
        BitsPerSample=16,
    ))
    provider.warm()

    with pytest.raises(RuntimeError, match="sapi_unsupported_output_format"):
        list(provider.stream(
            "teste",
            cancellation=VoiceCancellation(),
            session_id="s",
            turn_id=1,
            generation=1,
        ))


def test_sapi_provider_empty_text_and_lifecycle_are_bounded():
    provider, _, _ = _provider()
    provider.warm()
    assert list(provider.stream(
        "",
        cancellation=VoiceCancellation(),
        session_id="s",
        turn_id=1,
        generation=1,
    )) == []
    provider.release()
    provider.release()
    with pytest.raises(RuntimeError, match="sapi_provider_released"):
        provider.warm()
    replacement, _, _ = _provider()
    replacement.warm()
    replacement.release()


def test_sapi_pipeline_rejects_old_generation_before_output():
    provider, _, _ = _provider()
    output = FakeAudioOutputProvider()
    pipeline = VoiceAudioPipeline(provider, output)

    first = pipeline.speak(
        "resposta antiga",
        session_id="s",
        turn_id=1,
        generation=1,
    )
    old_chunk = output.accepted[0]
    assert first.ok is True

    pipeline.begin_turn(session_id="s", turn_id=2, generation=2)
    assert pipeline.accept_chunk(old_chunk) is False
    assert output.queued == ()
    pipeline.release()


def test_sapi_provider_error_is_bounded_by_pipeline():
    provider, _, _ = _provider(speak_failure=RuntimeError("sapi unavailable"))
    output = FakeAudioOutputProvider()
    pipeline = VoiceAudioPipeline(provider, output)
    result = pipeline.speak("falha", session_id="s", turn_id=1, generation=1)

    assert result.ok is False
    assert output.accepted == []
    pipeline.release()


def test_sapi_provider_cancel_blocks_pcm_before_delivery():
    provider, _, _ = _provider()
    provider.warm()
    provider.cancel()

    with pytest.raises(VoiceCancelledError, match="sapi_cancelled"):
        list(provider.stream(
            "cancelar antes da entrega",
            cancellation=VoiceCancellation(),
            session_id="s",
            turn_id=1,
            generation=1,
        ))
    provider.release()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows SAPI is Windows-only")
def test_real_maria_synthesis_is_memory_only_and_valid_pcm():
    provider = WindowsSapiTTSProvider()
    provider.warm()
    text = "Olá. Esta é uma validação local da voz do Jarvis em português do Brasil. ç ã õ á é í ó ú 123."

    chunks = provider.synthesize(
        text,
        cancellation=VoiceCancellation(),
        session_id="real-sapi-session",
        turn_id=1,
        generation=1,
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.pcm
    assert len(chunk.pcm) % (chunk.channels * 2) == 0
    assert len(set(chunk.pcm)) > 2
    assert any(chunk.pcm)
    duration_ms = len(chunk.pcm) * 1000 / (chunk.sample_rate * chunk.channels * 2)
    assert duration_ms > 0
    assert provider.last_format == {
        "source_sample_rate": 22050,
        "source_channels": 1,
        "source_bits_per_sample": 16,
        "source_block_align": 2,
        "output_sample_rate": 22050,
        "output_channels": 1,
        "output_bits_per_sample": 16,
    }
    provider.release()

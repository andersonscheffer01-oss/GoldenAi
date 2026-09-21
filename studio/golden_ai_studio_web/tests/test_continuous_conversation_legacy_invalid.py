"""
INVALID LEGACY P1.4C TEST
DO NOT USE FOR ACCEPTANCE
Bypasses VoiceService runtime.

This test manually:
- Uses JarvisVoice.process_voice_command() for wake/follow-up decisions
- Simulates InputStream for mic capture
- Manually constructs context messages
- Does NOT exercise VoiceService._loop(), _barge_in_monitor_loop(),
  _capture_followup_after_barge_in(), or build_messages()

DO NOT USE. See test_continuous_conversation.py for the real test.
"""

import os
import sys
import time
import threading
import json

os.environ["JARVIS_STREAMING_VOICE"] = "1"
os.environ["JARVIS_BARGE_IN"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np


def speak_text(text):
    import edge_tts, subprocess, tempfile, asyncio
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    async def gen():
        c = edge_tts.Communicate(text, "pt-BR-FranciscaNeural", rate="+4%", pitch="-2Hz")
        await c.save(path)
    asyncio.run(gen())
    uri = "file:///" + os.path.abspath(path).replace("\\", "/")
    ps = (
        "Add-Type -AssemblyName PresentationCore;"
        "$p = New-Object System.Windows.Media.MediaPlayer;"
        f"$p.Open([Uri]'{uri}');"
        "for($i=0;$i -lt 50 -and -not $p.NaturalDuration.HasTimeSpan;$i++)"
        "{Start-Sleep -Milliseconds 100};"
        "if($p.NaturalDuration.HasTimeSpan)"
        "{$d=[math]::Ceiling($p.NaturalDuration.TimeSpan.TotalSeconds+0.5)}"
        "else{$d=8};"
        "$p.Play(); Start-Sleep -Seconds $d; $p.Close()"
    )
    start = time.time()
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", ps],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    proc.wait()
    elapsed_ms = (time.time() - start) * 1000
    try: os.unlink(path)
    except: pass
    return elapsed_ms, proc


def transcribe_audio(audio_bytes, samplerate=16000):
    try:
        from jarvis_core.voice import get_voice
        voice = get_voice()
        result = voice.transcribe_audio_bytes(audio_bytes, samplerate)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def wait_for_key(msg):
    input(f"\n  >>> {msg} <<<\n  Press ENTER when ready...")


def main():
    print("=" * 60)
    print("  P1.4C CONTINUOUS CONVERSATION TEST (LEGACY - INVALID)")
    print("  This test bypasses VoiceService runtime.")
    print("=" * 60)

    results = {}

    tts_text = (
        "Vou explicar o projeto Golden AI em detalhes. "
        "O Golden é um sistema de trading algoritmico que utiliza "
        "inteligência artificial para automatizar operações no mercado "
        "financeiro. Ele foi desenvolvido para auxiliar traders no "
        "gerenciamento de risco e tomada de decisões. O sistema inclui "
        "múltiplos módulos como o scanner, o risk engine, e o validation engine."
    )

    print("\n  STEP 1: Starting TTS playback...")
    wait_for_key("Put on your headset, get ready to interrupt")

    tts_done = threading.Event()
    tts_start_time = [None]
    tts_elapsed = [0]

    def run_tts():
        tts_start_time[0] = time.monotonic()
        elapsed, _ = speak_text(tts_text)
        tts_elapsed[0] = elapsed
        tts_done.set()

    tts_thread = threading.Thread(target=run_tts, daemon=True)
    tts_thread.start()
    time.sleep(1.0)

    print("\n  STEP 2: Monitoring mic...")
    print("  >> SAY: 'NÃO, QUERO SABER SOMENTE DA MEMÓRIA' <<")

    import sounddevice as sd

    speech_detected_at = None
    speech_frames = []
    blocksize = 1024
    samplerate = 16000
    speech_count = 0

    try:
        with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16", blocksize=blocksize) as stream:
            while not tts_done.is_set():
                data, _ = stream.read(blocksize)
                rms = float(np.abs(data).mean())
                if rms >= 400:
                    speech_count += 1
                    if speech_count >= 3 and speech_detected_at is None:
                        speech_detected_at = time.monotonic()
                else:
                    speech_count = max(0, speech_count - 1)
                if speech_detected_at is not None:
                    speech_frames.append(data.copy())
    except Exception as e:
        print(f"  [ERROR] Mic: {e}")

    tts_done.wait(timeout=20)

    if speech_frames:
        import wave, io
        audio = np.concatenate(speech_frames)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes(audio.tobytes())
        audio_bytes = buf.getvalue()
        stt_result = transcribe_audio(audio_bytes, samplerate)
        transcript = str(stt_result.get("text") or "").strip()
    else:
        transcript = ""

    print(f"  Transcript: '{transcript}'")

    # Legacy: uses JarvisVoice directly
    from jarvis_core.voice import JarvisVoice
    voice = JarvisVoice()
    if transcript:
        action = voice.process_voice_command(transcript)
        print(f"  Action: {action.get('action')}")
    else:
        print("  No transcript")

    os.environ["JARVIS_STREAMING_VOICE"] = "0"
    os.environ["JARVIS_BARGE_IN"] = "0"
    print("  LEGACY TEST COMPLETE — DO NOT USE FOR ACCEPTANCE")


if __name__ == "__main__":
    main()

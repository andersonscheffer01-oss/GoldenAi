"""Pre-check for P1.4B.1 live smoke test."""
import os

print("=== PRE-CHECK ===")
print()

# 1. Provider check
print("1. PROVIDER:")
groq_key = os.getenv("GROQ_API_KEY")
if groq_key:
    print(f"   GROQ_API_KEY: set ({len(groq_key)} chars)")
else:
    print("   GROQ_API_KEY: NOT SET")

# 2. Edge TTS
print()
print("2. EDGE TTS:")
try:
    import edge_tts
    print(f"   edge_tts version: {edge_tts.__version__}")
except ImportError:
    print("   edge_tts: NOT INSTALLED")

# 3. Streaming flag
print()
print("3. STREAMING FLAG:")
flag = os.getenv("JARVIS_STREAMING_VOICE", "0")
print(f"   JARVIS_STREAMING_VOICE={flag}")

# 4. Audio output
print()
print("4. AUDIO OUTPUT:")
try:
    import sounddevice as sd
    devices = sd.query_devices()
    output_devices = [d for d in devices if d["max_output_channels"] > 0]
    print(f"   Output devices: {len(output_devices)}")
    for d in output_devices[:3]:
        name = d["name"]
        print(f"     - {name}")
except Exception as e:
    print(f"   sounddevice error: {e}")

# 5. httpx (for Groq streaming)
print()
print("5. HTTPX:")
try:
    import httpx
    print(f"   httpx version: {httpx.__version__}")
except ImportError:
    print("   httpx: NOT INSTALLED")

# 6. WPF MediaPlayer (for playback)
print()
print("6. WPF PLAYBACK:")
import subprocess
result = subprocess.run(
    ["powershell", "-NoProfile", "-Command", "Add-Type -AssemblyName PresentationCore; Write-Output 'OK'"],
    capture_output=True, text=True, timeout=10
)
if "OK" in result.stdout:
    print("   WPF MediaPlayer: OK")
else:
    print(f"   WPF MediaPlayer: FAILED - {result.stderr[:100]}")

print()
print("=== PRE-CHECK COMPLETE ===")

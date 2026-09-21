"""Sequential audio player for streaming TTS.

Plays audio chunks via WPF MediaPlayer using subprocess.Popen
for real-time cancellation support.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from jarvis_core.streaming.tts_pipeline import AudioChunk

log = logging.getLogger(__name__)


class AudioPlayer:
    """Plays AudioChunks sequentially via WPF MediaPlayer.

    Uses subprocess.Popen for real-time cancellation.
    Supports threading.Event for cross-thread cancel.
    """

    def __init__(self):
        self._playing = False
        self._current_process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    async def play(
        self,
        chunk: AudioChunk,
        cancel_event: Optional[threading.Event] = None,
    ) -> float:
        """Play an audio chunk. Returns playback duration in ms.

        Uses WPF MediaPlayer via PowerShell with Popen for real stop.
        Checks cancel_event periodically for cross-thread cancellation.
        """
        if not chunk.audio_path or not Path(chunk.audio_path).exists():
            log.warning("Audio file missing for chunk %d", chunk.index)
            return 0

        self._playing = True
        start = time.perf_counter()

        try:
            uri = Path(chunk.audio_path).resolve().as_uri()
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

            with self._lock:
                self._current_process = subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            # Wait in executor, checking cancel periodically
            await asyncio.get_event_loop().run_in_executor(
                None, self._wait_for_process, cancel_event
            )

        except Exception as e:
            log.warning("Playback failed for chunk %d: %s", chunk.index, e)
        finally:
            with self._lock:
                self._current_process = None
            self._playing = False

        duration = (time.perf_counter() - start) * 1000
        return duration

    def _wait_for_process(
        self, cancel_event: Optional[threading.Event] = None
    ) -> None:
        """Wait for subprocess, checking cancel_event every 100ms.

        Called from thread pool executor. Thread-safe.
        """
        while True:
            with self._lock:
                proc = self._current_process

            if proc is None:
                return

            try:
                # Check if process finished
                retcode = proc.wait(timeout=0.1)
                return  # Process finished normally
            except subprocess.TimeoutExpired:
                # Process still running — check cancel
                if cancel_event and cancel_event.is_set():
                    self._terminate_process()
                    return

    def _terminate_process(self) -> None:
        """Terminate the subprocess and its children safely.

        Only terminates the process belonging to this player instance.
        Never kills generic powershell.exe processes.
        """
        with self._lock:
            proc = self._current_process

        if proc is None:
            return

        try:
            # First try clean terminate
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
                log.debug("Process terminated cleanly (pid=%d)", proc.pid)
                return
            except subprocess.TimeoutExpired:
                pass

            # Force kill if terminate didn't work
            proc.kill()
            try:
                proc.wait(timeout=1.0)
                log.debug("Process killed (pid=%d)", proc.pid)
            except subprocess.TimeoutExpired:
                log.warning("Process did not die after kill (pid=%d)", proc.pid)

        except Exception as e:
            log.warning("Error terminating process: %s", e)
        finally:
            with self._lock:
                self._current_process = None

    def stop(self) -> None:
        """Immediate stop — can be called from any thread.

        Terminates the current playback process.
        """
        self._terminate_process()
        self._playing = False

    async def wait_for_speech_end(self, timeout: float = 30.0) -> None:
        """Wait for current playback to finish."""
        start = time.perf_counter()
        while self._playing and (time.perf_counter() - start) < timeout:
            await asyncio.sleep(0.05)

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def current_pid(self) -> Optional[int]:
        """Get PID of current process (for testing)."""
        with self._lock:
            if self._current_process:
                return self._current_process.pid
            return None

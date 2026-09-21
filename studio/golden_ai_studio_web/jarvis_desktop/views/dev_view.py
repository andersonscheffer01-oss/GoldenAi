"""Aba DEV V2: painel tecnico (SHADOW + telemetria + providers + tasks)."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget


class DevView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Developer — Orchestrator SHADOW"))
        self.box = QTextEdit()
        self.box.setProperty("class", "console")
        self.box.setReadOnly(True)
        layout.addWidget(self.box, 1)

    def render(self, orch, providers, brain, tasks, voice=None):
        orch = orch or {}
        last = (orch.get("last_decision") or {}) if isinstance(orch, dict) else {}
        prim = (providers or {}).get("primary") or {}
        provs = [f"{p.get('name')}:{p.get('state')}" for p in (providers or {}).get("providers", [])]
        counts = {}
        for t in tasks or []:
            counts[str(t.get("status"))] = counts.get(str(t.get("status")), 0) + 1
        vent = ((voice or {}).get("last_event") or {}) if isinstance(voice, dict) else {}
        vtim = vent.get("timings") or {}
        vlevel = (voice or {}).get("level") or {}
        vstt = (voice or {}).get("stt") or {}
        vmic = (vstt.get("mic") or {}) if isinstance(vstt, dict) else {}
        vcap = (vstt.get("last_capture") or {}) if isinstance(vstt, dict) else {}
        ready = ((providers or {}).get("readiness") or {}) if isinstance(providers, dict) else {}
        lines = [
            f"ORCHESTRATOR: {(orch.get('mode', 'shadow') or 'shadow').upper()}",
            f"ROUTE: {last.get('route', '--')}",
            f"SKILL: {last.get('skill', '--')}",
            f"PROFILE: {last.get('model_profile', '--')}",
            f"PROVIDER: {prim.get('actual_provider', '--')}  MODEL: {prim.get('actual_model', '--')}",
            f"REQUESTED: {prim.get('requested_provider', '--')} / {prim.get('requested_model', '--')}",
            f"FALLBACK: {prim.get('fallback', '--')}  REASON: {prim.get('fallback_reason', '--')}",
            f"CONFIDENCE: {last.get('confidence', '--')}",
            f"TOOL COUNT: {last.get('tool_count', '--')}",
            f"PROVIDERS HEALTH: {', '.join(provs) or '--'}",
            f"TASK MANAGER: {counts or '--'}",
            f"BRAIN: {(brain or {}).get('model', '--')} tools={(brain or {}).get('tools_from_registry', '--')}",
            f"VOICE: {(voice or {}).get('state', '--')} level={vlevel.get('rms', '--')} "
            f"age={vlevel.get('age_ms', '--')}ms",
            f"STT: {vstt.get('model', '--')} {vstt.get('compute_type', '--')} "
            f"beam={vstt.get('beam_size', '--')} warmup={(vstt.get('warmup') or {}).get('state', '--')}",
            f"AUDIO GATE: floor={vstt.get('noise_floor', '--')} "
            f"threshold={vstt.get('speech_threshold', '--')} silence={vstt.get('silence_seconds', '--')}s",
            f"VOICE EVENT: id={vent.get('id', '--')} route={vent.get('route', '--')} "
            f"utterance={vent.get('utterance_id', '--')} conf={vent.get('confidence', '--')}",
            f"MIC: {vmic.get('name', '--')} idx={vmic.get('index', '--')} "
            f"{vmic.get('host_api', '--')} {vmic.get('capture_samplerate', '--')}Hz/"
            f"nativo={vmic.get('native_samplerate', '--')}Hz ch={vmic.get('capture_channels', '--')}",
            f"AUDIO: peak={vtim.get('peak', vcap.get('peak', '--'))} "
            f"clip={vtim.get('clipped_samples', vcap.get('clipped_samples', '--'))} "
            f"nearclip={vtim.get('near_clip_samples', vcap.get('near_clip_samples', '--'))} "
            f"pre_roll={vtim.get('pre_roll_ms', vcap.get('pre_roll_ms', '--'))}ms "
            f"end_sil={vtim.get('silence_wait_ms', vcap.get('silence_wait_ms', '--'))}ms/"
            f"alvo={vtim.get('end_silence_target_ms', '--')}ms",
            f"RAW: {vtim.get('raw_transcript', vstt.get('last_transcription', '--'))}",
            f"NORMALIZED: {vent.get('heard', '--')}",
            f"STT CONF: {vtim.get('stt_confidence', '--')} "
            f"logprob={vtim.get('avg_logprob', '--')} "
            f"nospeech={vtim.get('no_speech_prob', '--')} "
            f"compr={vtim.get('compression_ratio', '--')} "
            f"beam={vstt.get('beam_size', '--')} prompt={len(str(vstt.get('initial_prompt', '')))}ch",
            f"VOICE ROUTE: {vent.get('route', '--')} profile={vtim.get('profile', '--')} "
            f"provider={vtim.get('provider_actual', '--')} model={vtim.get('model_actual', '--')}",
            f"VOICE PERF: TTFT={vtim.get('time_to_first_token_ms', '--')}ms "
            f"generation={vtim.get('generation_ms', '--')}ms "
            f"tts={vtim.get('tts_start_ms', '--')}ms total={vtim.get('total_turn_ms', '--')}ms",
            f"VOICE MS: {vtim or '--'}",
            f"READY: {ready.get('state', '--')} core={ready.get('core_ready_ms', '--')}ms "
            f"full={ready.get('full_ready_ms', '--')}ms "
            f"reg={ready.get('provider_registration_ms', '--')}ms "
            f"health={ready.get('provider_health_ms', '--')}ms "
            f"sttwarm={ready.get('stt_warmup_ms', '--')}ms "
            f"{ready.get('degraded_reason', '')}",
        ]
        self.box.setPlainText("\n".join(lines))

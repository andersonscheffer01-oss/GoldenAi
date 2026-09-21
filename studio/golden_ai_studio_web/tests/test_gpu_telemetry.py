import json

from jarvis_desktop import gpu


def test_wmi_backend_exception_returns_controlled_unavailable(monkeypatch):
    monkeypatch.setattr(gpu, "_run_wmi_json", lambda: (_ for _ in ()).throw(OSError("driver")))

    result = gpu.get_gpu_info(force=True)

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "wmi_unavailable"
    assert result["name"] is None


def test_wmi_timeout_returns_controlled_unavailable(monkeypatch):
    monkeypatch.setattr(gpu, "_run_wmi_json", lambda: None)

    result = gpu.get_gpu_info(force=True)

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "wmi_unavailable"


def test_gpu_unavailable_does_not_raise(monkeypatch):
    monkeypatch.setattr(gpu, "_cim_video_controllers", lambda: [])

    result = gpu.get_gpu_info(force=True)

    assert result["status"] == "UNAVAILABLE"
    assert result["vram_total_human"] is None
    assert result["util_percent"] is None


def test_amd_detection_without_dynamic_metrics_is_partial(monkeypatch):
    monkeypatch.setattr(gpu, "_run_wmi_json", lambda: json.dumps({
        "Name": "AMD Radeon RX 9060 XT",
        "AdapterRAM": 16 * 1024 ** 3,
    }))

    result = gpu.get_gpu_info(force=True)

    assert result["name"] == "AMD Radeon RX 9060 XT"
    assert result["status"] == "PARTIAL"
    assert result["reason"] == "dynamic_metrics_unavailable"
    assert result["util_percent"] is None
    assert result["vram_used_human"] is None
    assert result["vram_total_human"] is None

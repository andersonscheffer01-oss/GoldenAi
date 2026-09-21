"""Timezone-aware normalization for timestamps supplied by external providers."""

from datetime import datetime, timezone


def normalize_external_timestamp(raw, source_timezone=""):
    """Return auditable raw, normalized and local-display timestamp fields."""
    result = {
        "timestamp_raw": raw,
        "normalized_timestamp": "",
        "display_timestamp": "",
        "timezone_source": str(source_timezone or "unknown"),
    }
    if raw in (None, ""):
        return result
    try:
        value = float(raw)
        aware = datetime.fromtimestamp(value, timezone.utc)
        local = aware.astimezone()
        result.update({
            "normalized_timestamp": aware.isoformat(),
            "display_timestamp": local.strftime("%H:%M"),
            "timezone_source": "epoch_utc_to_system_local",
            "display_timezone": str(local.tzinfo or "system_local"),
        })
        return result
    except (TypeError, ValueError, OSError, OverflowError):
        pass
    text = str(raw).strip()
    try:
        aware = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        result["display_timestamp"] = text
        result["timezone_source"] = "source_unspecified"
        return result
    if aware.tzinfo is None:
        result["display_timestamp"] = text
        result["timezone_source"] = "source_unspecified"
        return result
    local = aware.astimezone()
    result.update({
        "normalized_timestamp": aware.astimezone(timezone.utc).isoformat(),
        "display_timestamp": local.strftime("%H:%M"),
        "timezone_source": source_timezone or "iso8601_offset_to_system_local",
        "display_timezone": str(local.tzinfo or "system_local"),
    })
    return result

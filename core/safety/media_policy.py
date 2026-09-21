from __future__ import annotations


UNTRUSTED_SOURCES = {"video", "audio", "pdf", "image", "subtitle", "transcript"}


def classify_content_source(source_type: str) -> str:
    if str(source_type).lower() in UNTRUSTED_SOURCES:
        return "UNTRUSTED_DATA"
    return "INTERNAL_OR_UNKNOWN"


def is_untrusted_content(source_type: str) -> bool:
    return classify_content_source(source_type) == "UNTRUSTED_DATA"

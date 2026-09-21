from .models import URLValidationResult, WebContent, DownloadResult
from .url_validator import (
    validate_url,
    validate_download_url,
    is_dangerous_protocol,
    is_executable_extension,
    is_allowed_download_extension,
    ALLOWED_PROTOCOLS,
    BLOCKED_PROTOCOLS,
    EXECUTABLE_EXTENSIONS,
    MAX_DOWNLOAD_SIZE,
    MAX_FETCH_SIZE,
)
from .content_sanitizer import (
    extract_text_from_html,
    sanitize_content,
    detect_injection_attempts,
    is_safe_as_reference,
)


def __getattr__(name):
    if name == 'InternetService':
        from .service import InternetService
        return InternetService
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

"""Device Pairing V1 — Secure LAN device registration for Jarvis.

ARCHITECTURE:
  Device pairing COMPLEMENTS the existing AuthManager.
  AuthManager remains the authority for gateway authentication.
  Device tokens are accepted BY AuthManager as an alternative to the shared token.

FLOW:
  1. PC generates pairing code (short-lived, single-use)
  2. Code displayed locally only (PC screen)
  3. iPhone enters code
  4. Gateway validates code
  5. Device registered, device-specific token issued
  6. Pairing code invalidated
  7. Future connections use device token (no code needed)

SECURITY:
  - Pairing codes: 8 chars, alphanumeric, uppercase only
  - Single-use, TTL 5 minutes, max 3 attempts per code
  - Device tokens: 48-byte URL-safe, hashed for storage
  - Tokens never logged in plaintext
  - Revoked devices rejected
  - All pairing attempts audited
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import string
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.device_pairing")

# ─── Constants ────────────────────────────────────────────────

_PAIRING_CODE_LENGTH = 8
_PAIRING_CODE_TTL = 300  # 5 minutes
_PAIRING_MAX_ATTEMPTS = 3
_PAIRING_CLEANUP_INTERVAL = 60  # seconds
_DEVICE_STORE_FILE = "golden_runtime.db"  # reuse existing DB path
_MAX_DEVICES = 20

# Character set: uppercase + digits (no ambiguous chars like 0/O, 1/I/L)
_PAIRING_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _generate_pairing_code() -> str:
    """Generate a random 8-char pairing code."""
    return "".join(secrets.choice(_PAIRING_CHARS) for _ in range(_PAIRING_CODE_LENGTH))


def _hash_token(token: str) -> str:
    """Hash device token for safe storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_device_token() -> str:
    """Generate a 48-byte URL-safe device token."""
    return secrets.token_urlsafe(48)


@dataclass
class PairingCode:
    """A pending pairing code."""
    code: str
    created_at: float
    expires_at: float
    attempts: int = 0
    used: bool = False
    source_ip: str = ""


@dataclass
class Device:
    """A registered device."""
    device_id: str
    device_name: str
    device_type: str  # "iphone", "ipad", "android", "desktop", "unknown"
    created_at: float
    paired_at: float
    last_seen: float
    token_hash: str
    revoked: bool = False
    revoked_at: Optional[float] = None
    ip_address: str = ""
    capabilities: Dict[str, Any] = field(default_factory=dict)


class DevicePairingService:
    """Manages device pairing and device token authentication.

    COMPLEMENTS AuthManager — does NOT replace it.
    AuthManager.verify_device_token() is called by this service
    to validate device tokens.
    """

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = data_dir or str(Path.cwd())
        self._pairing_codes: Dict[str, PairingCode] = {}
        self._devices: Dict[str, Device] = {}  # device_id → Device
        self._lock = threading.Lock()
        self._device_token_map: Dict[str, str] = {}  # token_hash → device_id
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False

        # Load existing devices
        self._load_devices()

    def start(self) -> None:
        """Start cleanup thread."""
        if self._running:
            return
        self._running = True
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True, name="device-pairing-cleanup"
        )
        self._cleanup_thread.start()
        logger.info("Device pairing service started")

    def stop(self) -> None:
        """Stop cleanup thread."""
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        logger.info("Device pairing service stopped")

    # ─── Pairing Code Management ──────────────────────────────

    def create_pairing_code(self, source_ip: str = "") -> str:
        """Generate a new pairing code. Returns the plaintext code.

        The code is valid for _PAIRING_CODE_TTL seconds.
        Only one active code at a time (new code invalidates previous).
        """
        with self._lock:
            # Invalidate any existing codes
            self._pairing_codes.clear()

            code = _generate_pairing_code()
            now = time.time()
            pairing = PairingCode(
                code=code,
                created_at=now,
                expires_at=now + _PAIRING_CODE_TTL,
                source_ip=source_ip,
            )
            self._pairing_codes[code] = pairing
            logger.info(f"Pairing code created (expires in {_PAIRING_CODE_TTL}s)")
            return code

    def validate_pairing_code(
        self, code: str, source_ip: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Validate a pairing code. Returns device info dict if valid, None otherwise.

        After successful validation, the code is marked as used.
        """
        code = code.strip().upper()

        with self._lock:
            pairing = self._pairing_codes.get(code)

            if pairing is None:
                logger.warning(f"Invalid pairing code attempt from {source_ip}")
                return None

            if pairing.used:
                logger.warning(f"Used pairing code attempt from {source_ip}")
                return None

            now = time.time()
            if now > pairing.expires_at:
                logger.warning(f"Expired pairing code attempt from {source_ip}")
                self._pairing_codes.pop(code, None)
                return None

            pairing.attempts += 1
            if pairing.attempts > _PAIRING_MAX_ATTEMPTS:
                logger.warning(f"Pairing code max attempts exceeded from {source_ip}")
                self._pairing_codes.pop(code, None)
                return None

            # Mark as used
            pairing.used = True

            logger.info(f"Pairing code validated from {source_ip}")
            return {
                "valid": True,
                "source_ip": source_ip,
            }

    def complete_pairing(
        self,
        device_name: str,
        device_type: str = "unknown",
        source_ip: str = "",
        capabilities: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Complete pairing and register a new device.

        Returns device info + token, or None if pairing not available.
        """
        with self._lock:
            # Find the used pairing code
            used_code = None
            for code, pairing in self._pairing_codes.items():
                if pairing.used:
                    used_code = code
                    break

            if used_code is None:
                logger.warning("No valid pairing code for complete_pairing")
                return None

            # Check device limit
            active_devices = [d for d in self._devices.values() if not d.revoked]
            if len(active_devices) >= _MAX_DEVICES:
                logger.warning(f"Device limit reached ({_MAX_DEVICES})")
                return None

            # Generate device token
            token = _generate_device_token()
            token_hash = _hash_token(token)

            now = time.time()
            device_id = f"dev_{secrets.token_hex(12)}"

            device = Device(
                device_id=device_id,
                device_name=device_name.strip()[:120] or "iPhone",
                device_type=device_type.strip()[:40] or "unknown",
                created_at=now,
                paired_at=now,
                last_seen=now,
                token_hash=token_hash,
                ip_address=source_ip,
                capabilities=capabilities or {},
            )

            self._devices[device_id] = device
            self._device_token_map[token_hash] = device_id

            # Remove used pairing code
            self._pairing_codes.pop(used_code, None)

            # Persist
            self._save_devices()

            logger.info(f"Device paired: {device_id} ({device_name})")
            return {
                "device_id": device_id,
                "device_name": device.device_name,
                "device_type": device.device_type,
                "token": token,
                "paired_at": device.paired_at,
            }

    # ─── Device Token Authentication ──────────────────────────

    def verify_device_token(self, token: str) -> Optional[Device]:
        """Verify a device token and return the device if valid.

        Returns None if token is invalid, revoked, or unknown.
        """
        if not token:
            return None

        token_hash = _hash_token(token)

        with self._lock:
            device_id = self._device_token_map.get(token_hash)
            if device_id is None:
                return None

            device = self._devices.get(device_id)
            if device is None:
                return None

            if device.revoked:
                logger.warning(f"Revoked device attempted auth: {device_id}")
                return None

            # Update last_seen
            device.last_seen = time.time()
            self._save_devices()

            return device

    def authenticate_device(self, token: str, source_ip: str = "") -> bool:
        """Authenticate a device token. Returns True if valid.

        Called by AuthManager to validate device tokens.
        """
        device = self.verify_device_token(token)
        if device is None:
            return False

        with self._lock:
            device.ip_address = source_ip
            device.last_seen = time.time()
            self._save_devices()

        return True

    # ─── Device Management ────────────────────────────────────

    def revoke_device(self, device_id: str) -> bool:
        """Revoke a device. Returns True if device was found and revoked."""
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                return False

            device.revoked = True
            device.revoked_at = time.time()

            # Remove from token map
            self._device_token_map.pop(device.token_hash, None)

            self._save_devices()
            logger.info(f"Device revoked: {device_id}")
            return True

    def list_devices(self, include_revoked: bool = False) -> List[Dict[str, Any]]:
        """List all devices."""
        with self._lock:
            devices = []
            for device in self._devices.values():
                if not include_revoked and device.revoked:
                    continue
                devices.append({
                    "device_id": device.device_id,
                    "device_name": device.device_name,
                    "device_type": device.device_type,
                    "created_at": device.created_at,
                    "paired_at": device.paired_at,
                    "last_seen": device.last_seen,
                    "revoked": device.revoked,
                    "ip_address": device.ip_address,
                    "capabilities": device.capabilities,
                })
            return devices

    def get_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific device."""
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                return None
            return {
                "device_id": device.device_id,
                "device_name": device.device_name,
                "device_type": device.device_type,
                "created_at": device.created_at,
                "paired_at": device.paired_at,
                "last_seen": device.last_seen,
                "revoked": device.revoked,
                "ip_address": device.ip_address,
                "capabilities": device.capabilities,
            }

    # ─── Persistence ──────────────────────────────────────────

    def _save_devices(self) -> None:
        """Save devices to JSON file."""
        try:
            store_path = Path(self._data_dir) / "device_registry.json"
            data = {}
            for device_id, device in self._devices.items():
                data[device_id] = {
                    "device_id": device.device_id,
                    "device_name": device.device_name,
                    "device_type": device.device_type,
                    "created_at": device.created_at,
                    "paired_at": device.paired_at,
                    "last_seen": device.last_seen,
                    "token_hash": device.token_hash,
                    "revoked": device.revoked,
                    "revoked_at": device.revoked_at,
                    "ip_address": device.ip_address,
                    "capabilities": device.capabilities,
                }
            store_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save devices: {e}")

    def _load_devices(self) -> None:
        """Load devices from JSON file."""
        try:
            store_path = Path(self._data_dir) / "device_registry.json"
            if not store_path.exists():
                return

            data = json.loads(store_path.read_text(encoding="utf-8"))
            for device_id, info in data.items():
                device = Device(
                    device_id=info["device_id"],
                    device_name=info["device_name"],
                    device_type=info["device_type"],
                    created_at=info["created_at"],
                    paired_at=info["paired_at"],
                    last_seen=info["last_seen"],
                    token_hash=info["token_hash"],
                    revoked=info.get("revoked", False),
                    revoked_at=info.get("revoked_at"),
                    ip_address=info.get("ip_address", ""),
                    capabilities=info.get("capabilities", {}),
                )
                self._devices[device_id] = device
                if not device.revoked:
                    self._device_token_map[device.token_hash] = device_id

            logger.info(f"Loaded {len(self._devices)} devices from registry")
        except Exception as e:
            logger.error(f"Failed to load devices: {e}")

    # ─── Cleanup ──────────────────────────────────────────────

    def _cleanup_loop(self) -> None:
        """Periodically clean up expired pairing codes."""
        while self._running:
            time.sleep(_PAIRING_CLEANUP_INTERVAL)
            self._cleanup_expired_codes()

    def _cleanup_expired_codes(self) -> None:
        """Remove expired pairing codes."""
        now = time.time()
        with self._lock:
            expired = [
                code for code, pairing in self._pairing_codes.items()
                if now > pairing.expires_at
            ]
            for code in expired:
                del self._pairing_codes[code]
            if expired:
                logger.debug(f"Cleaned up {len(expired)} expired pairing codes")

    # ─── Status ───────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Return pairing service status."""
        with self._lock:
            active_codes = sum(1 for p in self._pairing_codes.values() if not p.used)
            active_devices = sum(1 for d in self._devices.values() if not d.revoked)
            return {
                "active_pairing_codes": active_codes,
                "active_devices": active_devices,
                "total_devices": len(self._devices),
                "running": self._running,
            }


# ─── Singleton ────────────────────────────────────────────────

_instance: Optional[DevicePairingService] = None
_instance_lock = threading.Lock()


def get_device_pairing_service(data_dir: Optional[str] = None) -> DevicePairingService:
    """Get or create the device pairing service singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DevicePairingService(data_dir=data_dir)
    return _instance

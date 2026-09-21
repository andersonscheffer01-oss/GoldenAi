"""TLS/SSL Context — Local CA + Server Certificate for Golden/Jarvis.

ARCHITECTURE:
  Root CA (self-signed, persistent)
      ↓ signs
  Server Certificate (per-LAN-IP, SAN-based)

DESIGN:
  - FAIL CLOSED: invalid/missing certs → startup error, never fallback to HTTP
  - NO auto-generation during normal startup
  - Explicit CLI commands: init, renew-server, status
  - Private keys never served, logged, or exposed via API
  - Root CA exportable as .pem and .cer for device trust

USAGE:
  python -m jarvis_core.ssl_context init
  python -m jarvis_core.ssl_context renew-server
  python -m jarvis_core.ssl_context status
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import ssl
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

logger = logging.getLogger("jarvis.ssl")

# ─── Paths ────────────────────────────────────────────────────

_CERTS_DIR = Path(r"C:\GoldenAI\certs")

_CA_CERT_PATH = _CERTS_DIR / "golden-local-ca.pem"
_CA_KEY_PATH = _CERTS_DIR / "golden-local-ca.key"
_SERVER_CERT_PATH = _CERTS_DIR / "golden-local-server.pem"
_SERVER_KEY_PATH = _CERTS_DIR / "golden-local-server.key"
_METADATA_PATH = _CERTS_DIR / "metadata.json"

# ─── Constants ────────────────────────────────────────────────

_CA_SUBJECT = "Golden AI Local Root CA"
_SERVER_SUBJECT = "Golden AI Local Server"
_CA_VALIDITY_DAYS = 3650  # 10 years
_SERVER_VALIDITY_DAYS = 365  # < 825 mandatory
_CA_KEY_SIZE = 4096
_SERVER_KEY_SIZE = 2048
_MIN_SERVER_VALIDITY_DAYS = 30
_MAX_SERVER_VALIDITY_DAYS = 825


# ─── Certificate Generation ──────────────────────────────────

def _generate_ca_key() -> rsa.RSAPrivateKey:
    """Generate RSA private key for Root CA."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=_CA_KEY_SIZE,
    )


def _generate_server_key() -> rsa.RSAPrivateKey:
    """Generate RSA private key for server certificate."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=_SERVER_KEY_SIZE,
    )


def _get_san_entries(lan_ip: Optional[str] = None) -> List[x509.GeneralName]:
    """Build SAN entries for server certificate."""
    san_names = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        x509.IPAddress(ipaddress.IPv6Address("::1")),
    ]
    if lan_ip and lan_ip not in ("127.0.0.1", "localhost"):
        try:
            san_names.append(x509.IPAddress(ipaddress.IPv4Address(lan_ip)))
        except Exception:
            logger.warning(f"Invalid LAN IP for SAN: {lan_ip}")
    return san_names


def _detect_lan_ip() -> Optional[str]:
    """Detect current LAN IP via lan_config."""
    try:
        from .lan_config import get_best_private_ip
        return get_best_private_ip()
    except Exception:
        return None


def generate_ca() -> Tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Generate a new Root CA certificate and private key.

    Returns:
        (certificate, private_key) tuple
    """
    key = _generate_ca_key()

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, _CA_SUBJECT),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Golden AI"),
    ])

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=_CA_VALIDITY_DAYS))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                key_cert_sign=True,
                crl_sign=True,
                digital_signature=False,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return cert, key


def generate_server_cert(
    ca_cert: x509.Certificate,
    ca_key: rsa.RSAPrivateKey,
    lan_ip: Optional[str] = None,
) -> Tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Generate a server certificate signed by the given CA.

    Args:
        ca_cert: The CA certificate to sign with
        ca_key: The CA private key
        lan_ip: Current LAN IP for SAN (detected if not provided)

    Returns:
        (certificate, private_key) tuple
    """
    if lan_ip is None:
        lan_ip = _detect_lan_ip()

    key = _generate_server_key()

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, _SERVER_SUBJECT),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Golden AI"),
    ])

    san_entries = _get_san_entries(lan_ip)
    now = datetime.now(timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=_SERVER_VALIDITY_DAYS))
        .add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                key_cert_sign=False,
                crl_sign=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return cert, key


# ─── File I/O ─────────────────────────────────────────────────

def _save_pem_cert(cert: x509.Certificate, path: Path) -> None:
    """Save certificate as PEM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _save_pem_key(key: rsa.RSAPrivateKey, path: Path) -> None:
    """Save private key as PEM (no encryption for local use)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def _save_cer_cert(cert: x509.Certificate, path: Path) -> None:
    """Save certificate as DER .cer (public only, for device trust)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cert.public_bytes(serialization.Encoding.DER))


def _load_ca_cert() -> Optional[x509.Certificate]:
    """Load Root CA certificate from disk."""
    if not _CA_CERT_PATH.exists():
        return None
    try:
        pem_data = _CA_CERT_PATH.read_bytes()
        return x509.load_pem_x509_certificate(pem_data)
    except Exception as e:
        logger.error(f"Failed to load CA cert: {e}")
        return None


def _load_ca_key() -> Optional[rsa.RSAPrivateKey]:
    """Load Root CA private key from disk."""
    if not _CA_KEY_PATH.exists():
        return None
    try:
        pem_data = _CA_KEY_PATH.read_bytes()
        return serialization.load_pem_private_key(pem_data, password=None)
    except Exception as e:
        logger.error(f"Failed to load CA key: {e}")
        return None


def _load_server_cert() -> Optional[x509.Certificate]:
    """Load server certificate from disk."""
    if not _SERVER_CERT_PATH.exists():
        return None
    try:
        pem_data = _SERVER_CERT_PATH.read_bytes()
        return x509.load_pem_x509_certificate(pem_data)
    except Exception as e:
        logger.error(f"Failed to load server cert: {e}")
        return None


def _load_server_key() -> Optional[rsa.RSAPrivateKey]:
    """Load server private key from disk."""
    if not _SERVER_KEY_PATH.exists():
        return None
    try:
        pem_data = _SERVER_KEY_PATH.read_bytes()
        return serialization.load_pem_private_key(pem_data, password=None)
    except Exception as e:
        logger.error(f"Failed to load server key: {e}")
        return None


def _fingerprint_hex(cert: x509.Certificate) -> str:
    """Get SHA-256 fingerprint of certificate as hex string."""
    fp = cert.fingerprint(hashes.SHA256())
    return ":".join(f"{b:02X}" for b in fp)


def _save_metadata(
    ca_cert: x509.Certificate,
    server_cert: x509.Certificate,
    lan_ip: Optional[str],
) -> None:
    """Save certificate metadata (fingerprints, dates, SANs)."""
    san_names = []
    try:
        san_ext = server_cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
        for name in san_ext.value:
            san_names.append(str(name.value))
    except x509.ExtensionNotFound:
        pass

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ca_fingerprint": _fingerprint_hex(ca_cert),
        "ca_subject": ca_cert.subject.rfc4514_string(),
        "ca_not_valid_before": ca_cert.not_valid_before_utc.isoformat(),
        "ca_not_valid_after": ca_cert.not_valid_after_utc.isoformat(),
        "server_fingerprint": _fingerprint_hex(server_cert),
        "server_subject": server_cert.subject.rfc4514_string(),
        "server_not_valid_before": server_cert.not_valid_before_utc.isoformat(),
        "server_not_valid_after": server_cert.not_valid_after_utc.isoformat(),
        "server_san": san_names,
        "lan_ip": lan_ip,
    }
    _METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    _METADATA_PATH.write_text(json.dumps(metadata, indent=2))


def _load_metadata() -> Optional[Dict[str, Any]]:
    """Load certificate metadata."""
    if not _METADATA_PATH.exists():
        return None
    try:
        return json.loads(_METADATA_PATH.read_text())
    except Exception:
        return None


# ─── Validation ───────────────────────────────────────────────

def validate_certificates() -> Dict[str, Any]:
    """Validate existing certificates. Returns validation result.

    This does NOT generate anything. It only checks what exists.
    Used at startup with GOLDEN_SSL=1.
    """
    result = {
        "valid": False,
        "ca_exists": False,
        "server_exists": False,
        "ca_cert": None,
        "server_cert": None,
        "errors": [],
    }

    # Check CA
    ca_cert = _load_ca_cert()
    if ca_cert is None:
        result["errors"].append("CA certificate not found")
        return result
    result["ca_exists"] = True
    result["ca_cert"] = ca_cert

    # Check CA key
    ca_key = _load_ca_key()
    if ca_key is None:
        result["errors"].append("CA private key not found")
        return result

    # Check CA is actually a CA
    try:
        bc_ext = ca_cert.extensions.get_extension_for_class(x509.BasicConstraints)
        if not bc_ext.value.ca:
            result["errors"].append("CA certificate is not a CA (BasicConstraints.ca=false)")
            return result
    except x509.ExtensionNotFound:
        result["errors"].append("CA certificate missing BasicConstraints extension")
        return result

    # Check CA key usage
    try:
        ku_ext = ca_cert.extensions.get_extension_for_class(x509.KeyUsage)
        if not ku_ext.value.key_cert_sign:
            result["errors"].append("CA certificate missing keyCertSign key usage")
            return result
    except x509.ExtensionNotFound:
        result["errors"].append("CA certificate missing KeyUsage extension")
        return result

    # Check CA not expired
    now = datetime.now(timezone.utc)
    if ca_cert.not_valid_after_utc < now:
        result["errors"].append("CA certificate expired")
        return result

    # Check server cert
    server_cert = _load_server_cert()
    if server_cert is None:
        result["errors"].append("Server certificate not found")
        return result
    result["server_exists"] = True
    result["server_cert"] = server_cert

    # Check server key
    server_key = _load_server_key()
    if server_key is None:
        result["errors"].append("Server private key not found")
        return result

    # Check server cert not expired
    if server_cert.not_valid_after_utc < now:
        result["errors"].append("Server certificate expired")
        return result

    # Check server cert validity range
    validity_days = (server_cert.not_valid_after_utc - server_cert.not_valid_before_utc).days
    if validity_days > _MAX_SERVER_VALIDITY_DAYS:
        result["errors"].append(
            f"Server certificate validity ({validity_days} days) exceeds max ({_MAX_SERVER_VALIDITY_DAYS})"
        )
        return result

    # Check server cert is NOT a CA
    try:
        bc_ext = server_cert.extensions.get_extension_for_class(x509.BasicConstraints)
        if bc_ext.value.ca:
            result["errors"].append("Server certificate is a CA (should not be)")
            return result
    except x509.ExtensionNotFound:
        pass  # OK - no BasicConstraints means not a CA

    # Check server cert EKU
    try:
        eku_ext = server_cert.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        )
        if ExtendedKeyUsageOID.SERVER_AUTH not in eku_ext.value:
            result["errors"].append("Server certificate missing serverAuth EKU")
            return result
        if ExtendedKeyUsageOID.CLIENT_AUTH in eku_ext.value:
            result["errors"].append("Server certificate has clientAuth EKU (not allowed)")
            return result
    except x509.ExtensionNotFound:
        result["errors"].append("Server certificate missing ExtendedKeyUsage extension")
        return result

    # Check server cert SAN
    try:
        san_ext = server_cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
        san_dns = san_ext.value.get_values_for_type(x509.DNSName)
        san_ips = san_ext.value.get_values_for_type(x509.IPAddress)
        if "localhost" not in san_dns:
            result["errors"].append("Server certificate SAN missing 'localhost' DNS")
            return result
        has_loopback = any(
            str(ip) in ("127.0.0.1", "::1") for ip in san_ips
        )
        if not has_loopback:
            result["errors"].append("Server certificate SAN missing loopback IP")
            return result
    except x509.ExtensionNotFound:
        result["errors"].append("Server certificate missing SubjectAlternativeName")
        return result

    # Check signature chain
    try:
        ca_public_key = ca_cert.public_key()
        ca_public_key.verify(
            server_cert.signature,
            server_cert.tbs_certificate_bytes,
            padding=padding.PKCS1v15(),
            algorithm=server_cert.signature_hash_algorithm,
        )
    except Exception as e:
        result["errors"].append(f"Server cert signature verification failed: {e}")
        return result

    # Check key usage on server cert
    try:
        ku_ext = server_cert.extensions.get_extension_for_class(x509.KeyUsage)
        if not ku_ext.value.digital_signature:
            result["errors"].append("Server cert missing digitalSignature key usage")
            return result
        if not ku_ext.value.key_encipherment:
            result["errors"].append("Server cert missing keyEncipherment key usage")
            return result
    except x509.ExtensionNotFound:
        result["errors"].append("Server certificate missing KeyUsage extension")
        return result

    result["valid"] = True
    return result


# ─── SSLContext Loading ───────────────────────────────────────

def load_ssl_context() -> ssl.SSLContext:
    """Load SSL context from existing certificates.

    FAIL CLOSED: raises on any error.

    Returns:
        ssl.SSLContext ready for HTTPS/WSS

    Raises:
        FileNotFoundError: if certificates are missing
        ssl.SSLError: if certificates are invalid
        RuntimeError: if validation fails
    """
    # Validate first
    validation = validate_certificates()
    if not validation["valid"]:
        errors = "; ".join(validation["errors"])
        raise RuntimeError(f"Certificate validation failed: {errors}")

    # Create SSL context
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    # Load server cert chain (server cert + CA cert)
    ctx.load_cert_chain(
        certfile=str(_SERVER_CERT_PATH),
        keyfile=str(_SERVER_KEY_PATH),
    )

    # Load CA cert for client verification (optional, for future mTLS)
    ctx.load_verify_locations(cafile=str(_CA_CERT_PATH))

    # Security hardening
    ctx.check_hostname = False  # Server side doesn't check hostname
    ctx.verify_mode = ssl.CERT_NONE  # We don't require client certs (no mTLS)

    return ctx


def get_cert_info() -> Dict[str, Any]:
    """Get public certificate information (no private keys)."""
    info = {
        "ca_cert_path": str(_CA_CERT_PATH),
        "server_cert_path": str(_SERVER_CERT_PATH),
        "ca_exists": _CA_CERT_PATH.exists(),
        "server_exists": _SERVER_CERT_PATH.exists(),
        "metadata": _load_metadata(),
    }

    ca_cert = _load_ca_cert()
    if ca_cert:
        info["ca_fingerprint"] = _fingerprint_hex(ca_cert)
        info["ca_not_valid_after"] = ca_cert.not_valid_after_utc.isoformat()

    server_cert = _load_server_cert()
    if server_cert:
        info["server_fingerprint"] = _fingerprint_hex(server_cert)
        info["server_not_valid_after"] = server_cert.not_valid_after_utc.isoformat()
        try:
            san_ext = server_cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            )
            info["server_san"] = [str(v) for v in san_ext.value]
        except x509.ExtensionNotFound:
            info["server_san"] = []

    return info


# ─── CLI Commands ─────────────────────────────────────────────

def cmd_init() -> int:
    """CLI: Initialize certificates (CA + server cert).

    Creates:
        certs/golden-local-ca.pem
        certs/golden-local-ca.key
        certs/golden-local-ca.cer
        certs/golden-local-server.pem
        certs/golden-local-server.key
        certs/metadata.json
    """
    _CERTS_DIR.mkdir(parents=True, exist_ok=True)

    # Check if CA already exists
    if _CA_CERT_PATH.exists():
        print(f"[SSL] Root CA already exists: {_CA_CERT_PATH}")
        print("[SSL] Use 'renew-server' to regenerate server cert only.")
        ca_cert = _load_ca_cert()
        ca_key = _load_ca_key()
        if ca_cert is None or ca_key is None:
            print("[SSL] ERROR: CA cert/key corrupted. Delete and re-run 'init'.")
            return 1
    else:
        # Generate new CA
        print("[SSL] Generating Root CA (RSA 4096, SHA-256)...")
        ca_cert, ca_key = generate_ca()
        _save_pem_cert(ca_cert, _CA_CERT_PATH)
        _save_pem_key(ca_key, _CA_KEY_PATH)
        _save_cer_cert(ca_cert, _CERTS_DIR / "golden-local-ca.cer")
        print(f"[SSL]   CA cert: {_CA_CERT_PATH}")
        print(f"[SSL]   CA key:  {_CA_KEY_PATH}")
        print(f"[SSL]   CA .cer: {_CERTS_DIR / 'golden-local-ca.cer'}")

    # Detect LAN IP
    lan_ip = _detect_lan_ip()
    if lan_ip:
        print(f"[SSL] Detected LAN IP: {lan_ip}")
    else:
        print("[SSL] No LAN IP detected, using loopback only in SAN")

    # Generate server cert
    print("[SSL] Generating server certificate (RSA 2048, SHA-256)...")
    server_cert, server_key = generate_server_cert(ca_cert, ca_key, lan_ip)
    _save_pem_cert(server_cert, _SERVER_CERT_PATH)
    _save_pem_key(server_key, _SERVER_KEY_PATH)

    # Save metadata
    _save_metadata(ca_cert, server_cert, lan_ip)

    # Print public info
    print("")
    print("=" * 60)
    print("  Golden AI — TLS Certificates Generated")
    print("=" * 60)
    print(f"  CA Fingerprint:     {_fingerprint_hex(ca_cert)}")
    print(f"  Server Fingerprint: {_fingerprint_hex(server_cert)}")
    print(f"  Server SAN:         {', '.join(str(v) for v in _get_san_entries(lan_ip))}")
    print(f"  Server EKU:         serverAuth")
    print(f"  Server Valid Until: {server_cert.not_valid_after_utc.strftime('%Y-%m-%d')}")
    print("=" * 60)
    print("")
    print("  TRUST PROCEDURE:")
    print(f"  Windows: certutil -addstore -user Root {_CERTS_DIR / 'golden-local-ca.cer'}")
    print(f"  iPhone:  Transfer {_CERTS_DIR / 'golden-local-ca.cer'} and install")
    print("")
    print("  STARTUP:")
    print("  set GOLDEN_SSL=1")
    print("  python server_agent.py")
    print("")

    return 0


def cmd_renew_server() -> int:
    """CLI: Renew server certificate (same CA, new SANs)."""
    ca_cert = _load_ca_cert()
    ca_key = _load_ca_key()
    if ca_cert is None or ca_key is None:
        print("[SSL] ERROR: Root CA not found. Run 'init' first.")
        return 1

    # Detect current LAN IP
    lan_ip = _detect_lan_ip()
    if lan_ip:
        print(f"[SSL] Detected LAN IP: {lan_ip}")
    else:
        print("[SSL] No LAN IP detected, using loopback only in SAN")

    # Generate new server cert
    print("[SSL] Renewing server certificate...")
    server_cert, server_key = generate_server_cert(ca_cert, ca_key, lan_ip)
    _save_pem_cert(server_cert, _SERVER_CERT_PATH)
    _save_pem_key(server_key, _SERVER_KEY_PATH)

    # Update metadata
    _save_metadata(ca_cert, server_cert, lan_ip)

    print(f"[SSL] Server cert renewed: {_SERVER_CERT_PATH}")
    print(f"[SSL] Fingerprint: {_fingerprint_hex(server_cert)}")
    print(f"[SSL] SAN: {', '.join(str(v) for v in _get_san_entries(lan_ip))}")
    print(f"[SSL] Valid until: {server_cert.not_valid_after_utc.strftime('%Y-%m-%d')}")

    return 0


def cmd_status() -> int:
    """CLI: Show certificate status."""
    info = get_cert_info()

    print("")
    print("=" * 60)
    print("  Golden AI — TLS Certificate Status")
    print("=" * 60)

    if not info["ca_exists"]:
        print("  Root CA:            NOT FOUND")
        print("  Server Certificate: NOT FOUND")
        print("")
        print("  Run: python -m jarvis_core.ssl_context init")
        print("=" * 60)
        return 1

    print(f"  Root CA:            EXISTS")
    print(f"  CA Fingerprint:     {info.get('ca_fingerprint', 'N/A')}")
    print(f"  CA Valid Until:     {info.get('ca_not_valid_after', 'N/A')}")

    if not info["server_exists"]:
        print("  Server Certificate: NOT FOUND")
        print("")
        print("  Run: python -m jarvis_core.ssl_context init")
        print("=" * 60)
        return 1

    print(f"  Server Certificate: EXISTS")
    print(f"  Server Fingerprint: {info.get('server_fingerprint', 'N/A')}")
    print(f"  Server SAN:         {', '.join(info.get('server_san', []))}")
    print(f"  Server Valid Until: {info.get('server_not_valid_after', 'N/A')}")

    # Validation
    validation = validate_certificates()
    if validation["valid"]:
        print(f"  Validation:         PASS")
    else:
        print(f"  Validation:         FAIL")
        for err in validation["errors"]:
            print(f"    - {err}")

    print("=" * 60)
    return 0 if validation["valid"] else 1


def cmd_add_trust() -> int:
    """CLI: Add Root CA to Windows Current User trust store."""
    if not _CA_CERT_PATH.exists():
        print("[SSL] ERROR: Root CA not found. Run 'init' first.")
        return 1

    cer_path = _CERTS_DIR / "golden-local-ca.cer"
    if not cer_path.exists():
        print("[SSL] ERROR: .cer file not found. Run 'init' first.")
        return 1

    print("[SSL] Adding Root CA to Windows Current User trust store...")
    print(f"[SSL]   Source: {cer_path}")

    try:
        import subprocess
        result = subprocess.run(
            [
                "certutil",
                "-addstore",
                "-user",
                "Root",
                str(cer_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("[SSL] Root CA added to trust store successfully.")
            print("[SSL] WINDOWS_CA_TRUSTED: YES")
            return 0
        else:
            print(f"[SSL] ERROR: certutil failed: {result.stderr}")
            print("[SSL] WINDOWS_CA_TRUSTED: NO")
            return 1
    except Exception as e:
        print(f"[SSL] ERROR: {e}")
        print("[SSL] WINDOWS_CA_TRUSTED: NO")
        return 1


# ─── Module Entry Point ───────────────────────────────────────

def main() -> None:
    """CLI entry point for python -m jarvis_core.ssl_context."""
    if len(sys.argv) < 2:
        print("Usage: python -m jarvis_core.ssl_context <command>")
        print("")
        print("Commands:")
        print("  init          Generate CA + server certificates")
        print("  renew-server  Renew server certificate (same CA)")
        print("  status        Show certificate status")
        print("  add-trust     Add Root CA to Windows trust store")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "init":
        sys.exit(cmd_init())
    elif command == "renew-server":
        sys.exit(cmd_renew_server())
    elif command == "status":
        sys.exit(cmd_status())
    elif command == "add-trust":
        sys.exit(cmd_add_trust())
    else:
        print(f"Unknown command: {command}")
        print("Commands: init, renew-server, status, add-trust")
        sys.exit(1)


if __name__ == "__main__":
    main()

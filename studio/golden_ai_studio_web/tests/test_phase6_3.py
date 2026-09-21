"""Phase 6.3 — HTTPS/WSS TLS Tests

Tests for:
  - Certificate generation (CA + server)
  - Certificate validation (fail closed)
  - SSLContext loading
  - Origin validation with SSL
  - Gateway WSS support
  - Private key protection
  - Service Worker under HTTPS
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# Ensure we can import from the project
_ROOT = Path(r"C:\GoldenAI")
_STUDIO = _ROOT / "studio" / "golden_ai_studio_web"
if str(_STUDIO) not in sys.path:
    sys.path.insert(0, str(_STUDIO))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from jarvis_core.ssl_context import (
    _CA_CERT_PATH,
    _CA_KEY_PATH,
    _SERVER_CERT_PATH,
    _SERVER_KEY_PATH,
    _CERTS_DIR,
    _METADATA_PATH,
    _get_san_entries,
    _fingerprint_hex,
    generate_ca,
    generate_server_cert,
    validate_certificates,
    load_ssl_context,
    get_cert_info,
)
from jarvis_core.lan_config import (
    LanConfig,
    get_lan_config,
    validate_origin,
    add_lan_origin,
    is_private_ip,
)


# ─── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def ca_pair():
    """Generate a fresh CA key + cert for testing."""
    cert, key = generate_ca()
    yield cert, key


@pytest.fixture
def server_pair(ca_pair):
    """Generate a fresh server key + cert signed by test CA."""
    ca_cert, ca_key = ca_pair
    cert, key = generate_server_cert(ca_cert, ca_key, lan_ip="192.168.1.100")
    yield cert, key, ca_cert, ca_key


@pytest.fixture
def temp_certs(tmp_path):
    """Create temporary certificate files for testing."""
    ca_cert, ca_key = generate_ca()
    server_cert, server_key = generate_server_cert(ca_cert, ca_key, lan_ip="127.0.0.1")

    ca_cert_path = tmp_path / "test-ca.pem"
    ca_key_path = tmp_path / "test-ca.key"
    server_cert_path = tmp_path / "test-server.pem"
    server_key_path = tmp_path / "test-server.key"

    ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    ca_key_path.write_bytes(
        ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    server_cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    server_key_path.write_bytes(
        server_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    return {
        "ca_cert": ca_cert,
        "ca_key": ca_key,
        "server_cert": server_cert,
        "server_key": server_key,
        "ca_cert_path": ca_cert_path,
        "ca_key_path": ca_key_path,
        "server_cert_path": server_cert_path,
        "server_key_path": server_key_path,
        "tmp_path": tmp_path,
    }


# ─── Certificate Generation Tests ────────────────────────────

class TestCertificateGeneration:
    """Test CA and server certificate generation."""

    def test_ca_basic_constraint_is_ca(self, ca_pair):
        ca_cert, _ = ca_pair
        bc = ca_cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert bc.value.ca is True
        assert bc.critical is True

    def test_ca_has_key_cert_sign(self, ca_pair):
        ca_cert, _ = ca_pair
        ku = ca_cert.extensions.get_extension_for_class(x509.KeyUsage)
        assert ku.value.key_cert_sign is True
        assert ku.value.crl_sign is True
        assert ku.critical is True

    def test_ca_path_length_zero(self, ca_pair):
        ca_cert, _ = ca_pair
        bc = ca_cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert bc.value.path_length == 0

    def test_ca_does_not_have_server_auth(self, ca_pair):
        ca_cert, _ = ca_pair
        with pytest.raises(x509.ExtensionNotFound):
            ca_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)

    def test_ca_validity_10_years(self, ca_pair):
        ca_cert, _ = ca_pair
        validity = ca_cert.not_valid_after_utc - ca_cert.not_valid_before_utc
        assert validity.days >= 3600  # ~10 years
        assert validity.days <= 3700

    def test_server_cert_is_not_ca(self, server_pair):
        server_cert, _, _, _ = server_pair
        try:
            bc = server_cert.extensions.get_extension_for_class(x509.BasicConstraints)
            assert bc.value.ca is False
        except x509.ExtensionNotFound:
            pass  # No BasicConstraints also means not a CA

    def test_server_cert_has_server_auth_eku(self, server_pair):
        server_cert, _, _, _ = server_pair
        eku = server_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        assert ExtendedKeyUsageOID.SERVER_AUTH in eku.value

    def test_server_cert_does_not_have_client_auth(self, server_pair):
        server_cert, _, _, _ = server_pair
        eku = server_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        assert ExtendedKeyUsageOID.CLIENT_AUTH not in eku.value

    def test_server_cert_has_digital_signature(self, server_pair):
        server_cert, _, _, _ = server_pair
        ku = server_cert.extensions.get_extension_for_class(x509.KeyUsage)
        assert ku.value.digital_signature is True

    def test_server_cert_has_key_encipherment(self, server_pair):
        server_cert, _, _, _ = server_pair
        ku = server_cert.extensions.get_extension_for_class(x509.KeyUsage)
        assert ku.value.key_encipherment is True

    def test_server_cert_validity_within_limit(self, server_pair):
        server_cert, _, _, _ = server_pair
        validity = server_cert.not_valid_after_utc - server_cert.not_valid_before_utc
        assert validity.days <= 825
        assert validity.days >= 30

    def test_server_cert_signed_by_ca(self, server_pair):
        server_cert, _, ca_cert, ca_key = server_pair
        ca_public_key = ca_cert.public_key()
        ca_public_key.verify(
            server_cert.signature,
            server_cert.tbs_certificate_bytes,
            padding=padding.PKCS1v15(),
            algorithm=server_cert.signature_hash_algorithm,
        )

    def test_server_cert_san_has_localhost(self, server_pair):
        server_cert, _, _, _ = server_pair
        san = server_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        dns_names = san.value.get_values_for_type(x509.DNSName)
        assert "localhost" in dns_names

    def test_server_cert_san_has_loopback(self, server_pair):
        server_cert, _, _, _ = server_pair
        san = server_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        ip_addrs = san.value.get_values_for_type(x509.IPAddress)
        assert any(str(ip) in ("127.0.0.1", "::1") for ip in ip_addrs)

    def test_server_cert_san_has_lan_ip(self, server_pair):
        server_cert, _, _, _ = server_pair
        san = server_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        ip_addrs = san.value.get_values_for_type(x509.IPAddress)
        assert any("192.168.1.100" in str(ip) for ip in ip_addrs)

    def test_server_cert_sha256_or_better(self, server_pair):
        server_cert, _, _, _ = server_pair
        assert server_cert.signature_hash_algorithm.name in ("sha256", "sha384", "sha512")

    def test_server_key_rsa_2048(self, server_pair):
        _, server_key, _, _ = server_pair
        assert isinstance(server_key, rsa.RSAPrivateKey)
        assert server_key.key_size >= 2048

    def test_ca_key_rsa_4096(self, ca_pair):
        _, ca_key = ca_pair
        assert isinstance(ca_key, rsa.RSAPrivateKey)
        assert ca_key.key_size >= 4096


# ─── Certificate Validation Tests ─────────────────────────────

class TestCertificateValidation:
    """Test validate_certificates() function."""

    def test_valid_certs_pass(self, temp_certs):
        with patch("jarvis_core.ssl_context._CA_CERT_PATH", temp_certs["ca_cert_path"]), \
             patch("jarvis_core.ssl_context._CA_KEY_PATH", temp_certs["ca_key_path"]), \
             patch("jarvis_core.ssl_context._SERVER_CERT_PATH", temp_certs["server_cert_path"]), \
             patch("jarvis_core.ssl_context._SERVER_KEY_PATH", temp_certs["server_key_path"]):
            result = validate_certificates()
            assert result["valid"] is True
            assert len(result["errors"]) == 0

    def test_missing_ca_fails(self, temp_certs):
        with patch("jarvis_core.ssl_context._CA_CERT_PATH", temp_certs["tmp_path"] / "nonexistent.pem"), \
             patch("jarvis_core.ssl_context._CA_KEY_PATH", temp_certs["ca_key_path"]), \
             patch("jarvis_core.ssl_context._SERVER_CERT_PATH", temp_certs["server_cert_path"]), \
             patch("jarvis_core.ssl_context._SERVER_KEY_PATH", temp_certs["server_key_path"]):
            result = validate_certificates()
            assert result["valid"] is False
            assert any("CA certificate not found" in e for e in result["errors"])

    def test_missing_server_cert_fails(self, temp_certs):
        with patch("jarvis_core.ssl_context._CA_CERT_PATH", temp_certs["ca_cert_path"]), \
             patch("jarvis_core.ssl_context._CA_KEY_PATH", temp_certs["ca_key_path"]), \
             patch("jarvis_core.ssl_context._SERVER_CERT_PATH", temp_certs["tmp_path"] / "nonexistent.pem"), \
             patch("jarvis_core.ssl_context._SERVER_KEY_PATH", temp_certs["server_key_path"]):
            result = validate_certificates()
            assert result["valid"] is False
            assert any("Server certificate not found" in e for e in result["errors"])

    def test_missing_server_key_fails(self, temp_certs):
        with patch("jarvis_core.ssl_context._CA_CERT_PATH", temp_certs["ca_cert_path"]), \
             patch("jarvis_core.ssl_context._CA_KEY_PATH", temp_certs["ca_key_path"]), \
             patch("jarvis_core.ssl_context._SERVER_CERT_PATH", temp_certs["server_cert_path"]), \
             patch("jarvis_core.ssl_context._SERVER_KEY_PATH", temp_certs["tmp_path"] / "nonexistent.key"):
            result = validate_certificates()
            assert result["valid"] is False
            assert any("Server private key not found" in e for e in result["errors"])

    def test_expired_server_cert_fails(self, temp_certs):
        from cryptography.x509.oid import NameOID
        from datetime import datetime, timedelta, timezone

        ca_cert = temp_certs["ca_cert"]
        ca_key = temp_certs["ca_key"]

        # Generate expired server cert
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Expired")])
        now = datetime.now(timezone.utc)
        expired_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=400))
            .not_valid_after(now - timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256())
        )

        expired_cert_path = temp_certs["tmp_path"] / "expired.pem"
        expired_cert_path.write_bytes(expired_cert.public_bytes(serialization.Encoding.PEM))

        with patch("jarvis_core.ssl_context._CA_CERT_PATH", temp_certs["ca_cert_path"]), \
             patch("jarvis_core.ssl_context._CA_KEY_PATH", temp_certs["ca_key_path"]), \
             patch("jarvis_core.ssl_context._SERVER_CERT_PATH", expired_cert_path), \
             patch("jarvis_core.ssl_context._SERVER_KEY_PATH", temp_certs["server_key_path"]):
            result = validate_certificates()
            assert result["valid"] is False
            assert any("expired" in e.lower() for e in result["errors"])

    def test_missing_san_fails(self, temp_certs):
        from cryptography.x509.oid import NameOID
        from datetime import datetime, timedelta, timezone

        ca_cert = temp_certs["ca_cert"]
        ca_key = temp_certs["ca_key"]

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "No SAN")])
        now = datetime.now(timezone.utc)
        no_san_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256())
        )

        no_san_path = temp_certs["tmp_path"] / "no-san.pem"
        no_san_path.write_bytes(no_san_cert.public_bytes(serialization.Encoding.PEM))

        with patch("jarvis_core.ssl_context._CA_CERT_PATH", temp_certs["ca_cert_path"]), \
             patch("jarvis_core.ssl_context._CA_KEY_PATH", temp_certs["ca_key_path"]), \
             patch("jarvis_core.ssl_context._SERVER_CERT_PATH", no_san_path), \
             patch("jarvis_core.ssl_context._SERVER_KEY_PATH", temp_certs["server_key_path"]):
            result = validate_certificates()
            assert result["valid"] is False
            assert any("SubjectAlternativeName" in e for e in result["errors"])


# ─── SSLContext Loading Tests ─────────────────────────────────

class TestSSLContextLoading:
    """Test load_ssl_context() function."""

    def test_load_ssl_context_returns_ssl_context(self, temp_certs):
        with patch("jarvis_core.ssl_context._CA_CERT_PATH", temp_certs["ca_cert_path"]), \
             patch("jarvis_core.ssl_context._CA_KEY_PATH", temp_certs["ca_key_path"]), \
             patch("jarvis_core.ssl_context._SERVER_CERT_PATH", temp_certs["server_cert_path"]), \
             patch("jarvis_core.ssl_context._SERVER_KEY_PATH", temp_certs["server_key_path"]):
            ctx = load_ssl_context()
            assert isinstance(ctx, ssl.SSLContext)

    def test_load_ssl_context_tls_1_2_minimum(self, temp_certs):
        with patch("jarvis_core.ssl_context._CA_CERT_PATH", temp_certs["ca_cert_path"]), \
             patch("jarvis_core.ssl_context._CA_KEY_PATH", temp_certs["ca_key_path"]), \
             patch("jarvis_core.ssl_context._SERVER_CERT_PATH", temp_certs["server_cert_path"]), \
             patch("jarvis_core.ssl_context._SERVER_KEY_PATH", temp_certs["server_key_path"]):
            ctx = load_ssl_context()
            assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2

    def test_load_ssl_context_missing_cert_raises(self, temp_certs):
        with patch("jarvis_core.ssl_context._CA_CERT_PATH", temp_certs["tmp_path"] / "nonexistent"), \
             patch("jarvis_core.ssl_context._CA_KEY_PATH", temp_certs["ca_key_path"]), \
             patch("jarvis_core.ssl_context._SERVER_CERT_PATH", temp_certs["server_cert_path"]), \
             patch("jarvis_core.ssl_context._SERVER_KEY_PATH", temp_certs["server_key_path"]):
            with pytest.raises(RuntimeError, match="validation failed"):
                load_ssl_context()


# ─── Origin Validation Tests ──────────────────────────────────

class TestOriginValidation:
    """Test origin validation with SSL enabled/disabled."""

    def test_http_origin_allowed_when_ssl_off(self):
        # Reset allowed origins
        from jarvis_core import lan_config
        lan_config._ALLOWED_ORIGINS = {
            "http://127.0.0.1", "http://localhost", "http://[::1]",
            "https://127.0.0.1", "https://localhost", "https://[::1]",
        }
        result = validate_origin("http://192.168.1.100:8765", "127.0.0.1", ssl_enabled=False)
        # Should be checked against allowed origins (not automatically rejected)
        # Since we didn't add HTTP LAN origin, it should be rejected
        assert result is False

    def test_http_origin_rejected_when_ssl_on(self):
        result = validate_origin("http://192.168.1.100:8765", "127.0.0.1", ssl_enabled=True)
        assert result is False

    def test_https_origin_allowed_when_ssl_on(self):
        from jarvis_core import lan_config
        lan_config._ALLOWED_ORIGINS.add("https://192.168.1.100:8765")
        result = validate_origin("https://192.168.1.100:8765", "127.0.0.1", ssl_enabled=True)
        assert result is True

    def test_localhost_http_allowed_even_with_ssl(self):
        # Localhost HTTP is allowed for dev
        result = validate_origin("http://127.0.0.1:8765", "127.0.0.1", ssl_enabled=True)
        assert result is True

    def test_localhost_https_allowed_with_ssl(self):
        result = validate_origin("https://localhost:8765", "127.0.0.1", ssl_enabled=True)
        assert result is True

    def test_no_origin_allowed(self):
        result = validate_origin(None, "127.0.0.1", ssl_enabled=True)
        assert result is True

    def test_add_lan_origin_https_when_ssl(self):
        from jarvis_core import lan_config
        lan_config._ALLOWED_ORIGINS.clear()
        lan_config._ALLOWED_ORIGINS.update({
            "http://127.0.0.1", "https://127.0.0.1",
        })
        add_lan_origin("192.168.1.100", ssl_enabled=True)
        assert "https://192.168.1.100" in lan_config._ALLOWED_ORIGINS
        assert "https://192.168.1.100:8765" in lan_config._ALLOWED_ORIGINS

    def test_add_lan_origin_http_when_no_ssl(self):
        from jarvis_core import lan_config
        lan_config._ALLOWED_ORIGINS.clear()
        lan_config._ALLOWED_ORIGINS.update({
            "http://127.0.0.1", "https://127.0.0.1",
        })
        add_lan_origin("192.168.1.100", ssl_enabled=False)
        assert "http://192.168.1.100" in lan_config._ALLOWED_ORIGINS
        assert "http://192.168.1.100:8765" in lan_config._ALLOWED_ORIGINS


# ─── LanConfig SSL Tests ──────────────────────────────────────

class TestLanConfigSSL:
    """Test LanConfig SSL integration."""

    def test_ssl_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            lc = LanConfig()
            assert lc.ssl_enabled is False

    def test_ssl_enabled_via_env(self):
        with patch.dict(os.environ, {"GOLDEN_SSL": "1"}):
            lc = LanConfig()
            assert lc.ssl_enabled is True

    def test_ws_scheme_ssl_on(self):
        with patch.dict(os.environ, {"GOLDEN_SSL": "1"}):
            lc = LanConfig()
            assert lc.ws_scheme == "wss"

    def test_ws_scheme_ssl_off(self):
        with patch.dict(os.environ, {}, clear=True):
            lc = LanConfig()
            assert lc.ws_scheme == "ws"

    def test_http_scheme_ssl_on(self):
        with patch.dict(os.environ, {"GOLDEN_SSL": "1"}):
            lc = LanConfig()
            assert lc.http_scheme == "https"

    def test_http_scheme_ssl_off(self):
        with patch.dict(os.environ, {}, clear=True):
            lc = LanConfig()
            assert lc.http_scheme == "http"

    def test_status_includes_ssl(self):
        with patch.dict(os.environ, {"GOLDEN_SSL": "1"}):
            lc = LanConfig()
            status = lc.status()
            assert "ssl_enabled" in status
            assert status["ssl_enabled"] is True
            assert status["ws_scheme"] == "wss"
            assert status["http_scheme"] == "https"


# ─── Private Key Protection Tests ─────────────────────────────

class TestPrivateKeyProtection:
    """Test that private keys are not exposed."""

    def test_private_key_not_in_web_root(self):
        """Private keys should not be in studio/ web root."""
        studio_dir = Path(r"C:\GoldenAI\studio\golden_ai_studio_web")
        for key_name in ["golden-local-ca.key", "golden-local-server.key"]:
            key_path = studio_dir / key_name
            assert not key_path.exists(), f"Private key found in web root: {key_path}"

    def test_certs_dir_not_in_web_root(self):
        """certs/ directory should not be inside studio/ web root."""
        studio_dir = Path(r"C:\GoldenAI\studio\golden_ai_studio_web")
        certs_in_studio = studio_dir / "certs"
        assert not certs_in_studio.exists(), "certs/ directory found in web root"

    def test_metadata_does_not_contain_keys(self, temp_certs):
        """metadata.json should not contain private key material."""
        from jarvis_core.ssl_context import _save_metadata
        _save_metadata(temp_certs["ca_cert"], temp_certs["server_cert"], "192.168.1.100")
        metadata = json.loads(_METADATA_PATH.read_text())
        for key in metadata:
            assert "private" not in key.lower()
            assert "key" not in key.lower() or "fingerprint" in key.lower()


# ─── SAN Entry Tests ──────────────────────────────────────────

class TestSANEntries:
    """Test SAN entry generation."""

    def test_san_entries_localhost(self):
        san = _get_san_entries(None)
        dns = [str(e.value) for e in san if isinstance(e, x509.DNSName)]
        assert "localhost" in dns

    def test_san_entries_loopback_ip(self):
        san = _get_san_entries(None)
        ips = [str(e.value) for e in san if isinstance(e, x509.IPAddress)]
        assert "127.0.0.1" in ips

    def test_san_entries_ipv6_loopback(self):
        san = _get_san_entries(None)
        ips = [str(e.value) for e in san if isinstance(e, x509.IPAddress)]
        assert "::1" in ips

    def test_san_entries_includes_lan_ip(self):
        san = _get_san_entries("192.168.1.100")
        ips = [str(e.value) for e in san if isinstance(e, x509.IPAddress)]
        assert "192.168.1.100" in ips

    def test_san_entries_excludes_lan_ip_if_loopback(self):
        san = _get_san_entries("127.0.0.1")
        ips = [str(e.value) for e in san if isinstance(e, x509.IPAddress)]
        # Should not duplicate 127.0.0.1
        assert ips.count("127.0.0.1") == 1


# ─── Root CA Persistence Tests ────────────────────────────────

class TestRootCAPersistence:
    """Test that Root CA persists across operations."""

    def test_root_ca_not_regenerated_on_init_if_exists(self, temp_certs):
        """If CA exists, init should not regenerate it."""
        with patch("jarvis_core.ssl_context._CA_CERT_PATH", temp_certs["ca_cert_path"]), \
             patch("jarvis_core.ssl_context._CA_KEY_PATH", temp_certs["ca_key_path"]):
            ca_cert1 = temp_certs["ca_cert"]
            fp1 = _fingerprint_hex(ca_cert1)
            # Loading should return same cert
            from jarvis_core.ssl_context import _load_ca_cert
            ca_cert2 = _load_ca_cert()
            fp2 = _fingerprint_hex(ca_cert2)
            assert fp1 == fp2


# ─── Gateway SSL Tests ────────────────────────────────────────

class TestGatewaySSL:
    """Test Gateway SSL integration."""

    def test_gateway_accepts_ssl_context(self):
        from jarvis_core.gateway.gateway import Gateway
        mock_service = MagicMock()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        gw = Gateway(mock_service, ssl_context=ctx)
        assert gw.ssl_context is ctx

    def test_gateway_default_no_ssl(self):
        from jarvis_core.gateway.gateway import Gateway
        mock_service = MagicMock()
        gw = Gateway(mock_service)
        assert gw.ssl_context is None


# ─── Metadata Tests ───────────────────────────────────────────

class TestMetadata:
    """Test certificate metadata."""

    def test_metadata_contains_fingerprints(self, temp_certs):
        from jarvis_core.ssl_context import _save_metadata, _load_metadata
        _save_metadata(temp_certs["ca_cert"], temp_certs["server_cert"], "192.168.1.100")
        meta = _load_metadata()
        assert "ca_fingerprint" in meta
        assert "server_fingerprint" in meta
        assert len(meta["ca_fingerprint"]) > 0
        assert len(meta["server_fingerprint"]) > 0

    def test_metadata_contains_san(self, temp_certs):
        from jarvis_core.ssl_context import _save_metadata, _load_metadata
        _save_metadata(temp_certs["ca_cert"], temp_certs["server_cert"], "192.168.1.100")
        meta = _load_metadata()
        assert "server_san" in meta
        assert len(meta["server_san"]) > 0

    def test_metadata_contains_dates(self, temp_certs):
        from jarvis_core.ssl_context import _save_metadata, _load_metadata
        _save_metadata(temp_certs["ca_cert"], temp_certs["server_cert"], "192.168.1.100")
        meta = _load_metadata()
        assert "ca_not_valid_after" in meta
        assert "server_not_valid_after" in meta


# ─── Fingerprints Tests ───────────────────────────────────────

class TestFingerprints:
    """Test fingerprint generation."""

    def test_fingerprint_hex_format(self, ca_pair):
        ca_cert, _ = ca_pair
        fp = _fingerprint_hex(ca_cert)
        # Should be colon-separated hex pairs
        parts = fp.split(":")
        assert len(parts) == 32  # SHA-256 = 32 bytes
        for part in parts:
            assert len(part) == 2
            assert all(c in "0123456789ABCDEF" for c in part)

    def test_fingerprint_deterministic(self, ca_pair):
        ca_cert, _ = ca_pair
        fp1 = _fingerprint_hex(ca_cert)
        fp2 = _fingerprint_hex(ca_cert)
        assert fp1 == fp2


# ─── Cert File Structure Tests ────────────────────────────────

class TestCertFileStructure:
    """Test expected certificate file structure."""

    def test_expected_files_defined(self):
        assert _CA_CERT_PATH.name == "golden-local-ca.pem"
        assert _CA_KEY_PATH.name == "golden-local-ca.key"
        assert _SERVER_CERT_PATH.name == "golden-local-server.pem"
        assert _SERVER_KEY_PATH.name == "golden-local-server.key"
        assert _METADATA_PATH.name == "metadata.json"
        assert _CERTS_DIR.name == "certs"

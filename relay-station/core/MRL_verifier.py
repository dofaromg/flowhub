"""
MRL_verifier.py — ed25519 signature sign / verify for MRL particles

origin_signature : MrLiouWord
version          : 1.0
created_at       : 2026-05-11
source           : MRL_RelayStation v0.1
law              : LAW-2 ADDITIVE_RESOLUTION

Depends on: cryptography>=41  (pip install cryptography)
Falls back to a warning if cryptography is not installed.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature

    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

_DEFAULT_IDENTITY_DIR = Path(__file__).parent.parent / "identity"
_PRIV_FILE = _DEFAULT_IDENTITY_DIR / "id_ed25519"
_PUB_FILE = _DEFAULT_IDENTITY_DIR / "id_ed25519.pub"


# ---------------------------------------------------------------------------
# Key generation / loading
# ---------------------------------------------------------------------------

def generate_keypair(identity_dir: Path | None = None) -> tuple[Path, Path]:
    """
    Generate a new ed25519 keypair and write to identity_dir.

    Returns:
        (private_key_path, public_key_path)
    Raises:
        RuntimeError: if cryptography package is not installed.
    """
    _require_crypto()
    idir = Path(identity_dir) if identity_dir else _DEFAULT_IDENTITY_DIR
    idir.mkdir(parents=True, exist_ok=True)
    priv_path = idir / "id_ed25519"
    pub_path = idir / "id_ed25519.pub"

    private_key = Ed25519PrivateKey.generate()
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_path.write_bytes(priv_bytes)
    pub_path.write_bytes(pub_bytes)
    priv_path.chmod(0o600)
    return priv_path, pub_path


def load_private_key(path: Path | None = None) -> "Ed25519PrivateKey":
    """Load private key from PEM file."""
    _require_crypto()
    p = Path(path) if path else _PRIV_FILE
    return serialization.load_pem_private_key(p.read_bytes(), password=None)


def load_public_key(path: Path | None = None) -> "Ed25519PublicKey":
    """Load public key from PEM file."""
    _require_crypto()
    p = Path(path) if path else _PUB_FILE
    return serialization.load_pem_public_key(p.read_bytes())


# ---------------------------------------------------------------------------
# Sign / Verify
# ---------------------------------------------------------------------------

def _canonical_bytes(payload: Any) -> bytes:
    """Produce a stable canonical byte representation of a payload."""
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, bytes):
        return payload
    return str(payload).encode("utf-8")


def sign(payload: Any, private_key_path: Path | None = None) -> str:
    """
    Sign a payload with the ed25519 private key.

    Args:
        payload:          str, bytes, dict, or list to sign.
        private_key_path: Override path to PEM private key.

    Returns:
        Base64-encoded signature string.
    """
    _require_crypto()
    priv = load_private_key(private_key_path)
    data = _canonical_bytes(payload)
    sig_bytes = priv.sign(data)
    return base64.b64encode(sig_bytes).decode("ascii")


def verify(payload: Any, signature_b64: str,
           public_key_path: Path | None = None) -> bool:
    """
    Verify a base64-encoded ed25519 signature against a payload.

    Args:
        payload:         The original payload (same type as passed to sign).
        signature_b64:   Base64-encoded signature string from sign().
        public_key_path: Override path to PEM public key.

    Returns:
        True if valid, False otherwise.
    """
    _require_crypto()
    pub = load_public_key(public_key_path)
    data = _canonical_bytes(payload)
    sig_bytes = base64.b64decode(signature_b64)
    try:
        pub.verify(sig_bytes, data)
        return True
    except InvalidSignature:
        return False


# ---------------------------------------------------------------------------
# Particle manifest signing
# ---------------------------------------------------------------------------

def sign_manifest(manifest: dict, private_key_path: Path | None = None) -> dict:
    """
    Add an 'mrl_signature' field to a particle manifest dict.

    The signature covers a canonical JSON of the manifest (without the
    mrl_signature field itself).
    """
    manifest_clean = {k: v for k, v in manifest.items() if k != "mrl_signature"}
    sig = sign(manifest_clean, private_key_path)
    return {**manifest_clean, "mrl_signature": sig}


def verify_manifest(manifest: dict, public_key_path: Path | None = None) -> bool:
    """Verify the mrl_signature embedded in a manifest dict."""
    sig = manifest.get("mrl_signature")
    if not sig:
        return False
    manifest_clean = {k: v for k, v in manifest.items() if k != "mrl_signature"}
    return verify(manifest_clean, sig, public_key_path)


# ---------------------------------------------------------------------------
# Content hash (SHA-256, CAS-compatible)
# ---------------------------------------------------------------------------

def content_hash(data: Any) -> str:
    """
    Compute SHA-256 content hash of canonical payload bytes.

    Returns:
        'sha256:<hex>' string compatible with OCI CAS addressing.
    """
    raw = _canonical_bytes(data)
    digest = hashlib.sha256(raw).hexdigest()
    return f"sha256:{digest}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_crypto() -> None:
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError(
            "The 'cryptography' package is required for MRL_verifier. "
            "Install it with: pip install cryptography"
        )


def keypair_exists(identity_dir: Path | None = None) -> bool:
    """Return True if both key files exist in identity_dir."""
    idir = Path(identity_dir) if identity_dir else _DEFAULT_IDENTITY_DIR
    return (idir / "id_ed25519").exists() and (idir / "id_ed25519.pub").exists()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="MRL Verifier — ed25519 sign / verify / keygen / hash"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("keygen", help="Generate new ed25519 keypair")

    p_sign = sub.add_parser("sign", help="Sign a text payload")
    p_sign.add_argument("text", help="Text to sign")
    p_sign.add_argument("--key", default=None, help="Path to private key PEM")

    p_verify = sub.add_parser("verify", help="Verify a signature")
    p_verify.add_argument("text", help="Original text")
    p_verify.add_argument("sig", help="Base64 signature")
    p_verify.add_argument("--key", default=None, help="Path to public key PEM")

    p_hash = sub.add_parser("hash", help="Compute SHA-256 content hash")
    p_hash.add_argument("text", help="Text to hash")

    args = parser.parse_args()

    if args.cmd == "keygen":
        priv, pub = generate_keypair()
        print(f"✅ Generated: {priv}  {pub}")

    elif args.cmd == "sign":
        sig = sign(args.text, Path(args.key) if args.key else None)
        print(sig)

    elif args.cmd == "verify":
        ok = verify(args.text, args.sig, Path(args.key) if args.key else None)
        print("✅ Valid" if ok else "❌ Invalid")
        sys.exit(0 if ok else 1)

    elif args.cmd == "hash":
        print(content_hash(args.text))

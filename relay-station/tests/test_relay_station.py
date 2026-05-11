"""
tests/test_relay_station.py — Unit tests for MRL_RelayStation v0.1

Tests cover:
  - Dictionary load and structure
  - Translator: encode / decode / expand / check_syntax
  - LOD levels (symbol / q4 / q8 / fp16)
  - Round-trip encode → decode
  - Aggregator: absorb / search / stats / manifest
  - Router: register / route / broadcast / jump
  - Verifier: content_hash (crypto tests skipped if package absent)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup so tests can import relay-station modules
# ---------------------------------------------------------------------------

_RELAY = Path(__file__).resolve().parent.parent   # relay-station/
sys.path.insert(0, str(_RELAY))

import pytest

from core.MRL_translator import (
    encode, decode, expand, check_syntax, load_dict, build_indexes,
    LOD_LEVELS,
)
from core.MRL_aggregator import MRLAggregator
from core.MRL_router import MRLRouter
from core.MRL_verifier import content_hash, _CRYPTO_AVAILABLE

_DICT_PATH = _RELAY / "dictionary" / "Fluin.Dict.Base.json"

# ===========================================================================
# Dictionary tests
# ===========================================================================

class TestDictionary:
    def test_dict_file_exists(self):
        assert _DICT_PATH.exists(), "Fluin.Dict.Base.json not found"

    def test_dict_loads_clean_json(self):
        raw = json.loads(_DICT_PATH.read_text(encoding="utf-8"))
        assert "_meta" in raw
        entries = {k: v for k, v in raw.items() if k.startswith("fl-")}
        assert len(entries) >= 100, f"Expected ≥100 entries, got {len(entries)}"

    def test_all_required_fields(self):
        entries = load_dict(_DICT_PATH)
        required = {"concept", "zh", "layer", "symbol", "q4", "q8", "fp16", "origin_signature"}
        for key, entry in entries.items():
            missing = required - set(entry.keys())
            assert not missing, f"{key} missing fields: {missing}"

    def test_layers_present(self):
        entries = load_dict(_DICT_PATH)
        layers = {e["layer"] for e in entries.values()}
        assert "L0" in layers
        assert "L1" in layers
        assert "L2" in layers
        assert "L3" in layers
        assert "L4" in layers

    def test_keys_sequential_format(self):
        entries = load_dict(_DICT_PATH)
        import re
        pat = re.compile(r"^fl-\d{3}$")
        for key in entries:
            assert pat.match(key), f"Bad key format: {key}"

    def test_origin_signature_present(self):
        entries = load_dict(_DICT_PATH)
        for key, entry in entries.items():
            assert entry.get("origin_signature") == "MrLiouWord", (
                f"{key} has wrong origin_signature: {entry.get('origin_signature')}"
            )

    def test_build_indexes(self):
        entries = load_dict(_DICT_PATH)
        forward, by_concept, by_zh = build_indexes(entries)
        assert "fl-001" in forward
        assert "system" in by_concept
        assert by_concept["system"] == "fl-001"
        assert "系統" in by_zh
        assert by_zh["系統"] == "fl-001"


# ===========================================================================
# Translator tests
# ===========================================================================

class TestTranslator:
    def test_encode_known_concept(self):
        result = encode("system", dict_path=_DICT_PATH)
        assert "fl-001" in result

    def test_encode_unknown_token(self):
        result = encode("xyzzy", dict_path=_DICT_PATH)
        assert "?xyzzy" in result

    def test_encode_multi_word(self):
        result = encode("system flow memory", dict_path=_DICT_PATH)
        tokens = result.split()
        assert "fl-001" in tokens   # system
        assert "fl-002" in tokens   # flow
        assert "fl-007" in tokens   # memory

    def test_decode_known_key(self):
        result = decode("fl-001", lod="q4", dict_path=_DICT_PATH)
        assert result == "system"

    def test_decode_zh(self):
        result = decode("fl-001", lod="q4", lang="zh", dict_path=_DICT_PATH)
        assert result == "系統"

    def test_decode_all_lod_levels(self):
        for lod in LOD_LEVELS:
            result = decode("fl-001", lod=lod, dict_path=_DICT_PATH)
            assert result, f"Empty decode at lod={lod}"

    def test_round_trip(self):
        """encode then decode at q4 should recover the known concepts."""
        fltnz = encode("system flow memory", dict_path=_DICT_PATH)
        back = decode(fltnz, lod="q4", dict_path=_DICT_PATH)
        assert "system" in back
        assert "flow" in back
        assert "memory" in back

    def test_encode_chinese(self):
        result = encode("系統", dict_path=_DICT_PATH)
        assert "fl-001" in result

    def test_expand_returns_lines(self):
        result = expand(n_lines=3, particles_per_line=2, seed=42, dict_path=_DICT_PATH)
        lines = [l for l in result.splitlines() if l.strip()]
        assert len(lines) == 3

    def test_expand_reproducible(self):
        a = expand(n_lines=5, seed=99, dict_path=_DICT_PATH)
        b = expand(n_lines=5, seed=99, dict_path=_DICT_PATH)
        assert a == b

    def test_check_syntax_ok(self):
        results = check_syntax("fl-001 fl-002 fl-003", dict_path=_DICT_PATH)
        assert all(r["status"] == "OK" for r in results)

    def test_check_syntax_unknown(self):
        results = check_syntax("?xyzzy", dict_path=_DICT_PATH)
        assert any(r["status"] == "UNKNOWN" for r in results)

    def test_check_syntax_invalid(self):
        results = check_syntax("fl-999", dict_path=_DICT_PATH)
        assert any(r["status"] == "INVALID" for r in results)

    def test_invalid_lod_raises(self):
        with pytest.raises(ValueError):
            encode("system", lod="bad_lod", dict_path=_DICT_PATH)


# ===========================================================================
# Aggregator tests
# ===========================================================================

class TestAggregator:
    def test_absorb_file(self):
        agg = MRLAggregator()
        counts = agg.absorb_file(_DICT_PATH, source="test")
        assert counts["absorbed"] >= 100

    def test_duplicate_detection(self):
        agg = MRLAggregator()
        agg.absorb_file(_DICT_PATH, source="first")
        counts2 = agg.absorb_file(_DICT_PATH, source="second")
        assert counts2["absorbed"] == 0
        assert counts2["duplicate"] >= 100

    def test_get_by_key(self):
        agg = MRLAggregator()
        agg.absorb_file(_DICT_PATH)
        rec = agg.get("fl-001")
        assert rec is not None
        assert rec.entry["concept"] == "system"

    def test_by_layer(self):
        agg = MRLAggregator()
        agg.absorb_file(_DICT_PATH)
        l0 = agg.by_layer("L0")
        assert len(l0) >= 5

    def test_search(self):
        agg = MRLAggregator()
        agg.absorb_file(_DICT_PATH)
        results = agg.search("particle")
        assert any(r.key == "fl-076" for r in results)

    def test_stats(self):
        agg = MRLAggregator()
        agg.absorb_file(_DICT_PATH)
        stats = agg.stats()
        assert stats["total_particles"] >= 100
        assert "L0" in stats["layers"]

    def test_manifest_has_particles(self):
        agg = MRLAggregator()
        agg.absorb_file(_DICT_PATH)
        manifest = agg.to_manifest()
        assert "particles" in manifest
        assert len(manifest["particles"]) >= 100

    def test_to_dict_round_trip(self, tmp_path):
        agg = MRLAggregator()
        agg.absorb_file(_DICT_PATH)
        out = tmp_path / "merged.json"
        agg.save_dict(out)
        reloaded = json.loads(out.read_text(encoding="utf-8"))
        assert "fl-001" in reloaded


# ===========================================================================
# Router tests
# ===========================================================================

class TestRouter:
    def test_register_and_route(self):
        router = MRLRouter()
        received: list[dict] = []

        @router.on("main")
        def handler(channel, packet):
            received.append(packet)

        router.route("main", {"fl": "fl-001"})
        assert len(received) == 1
        assert received[0]["fl"] == "fl-001"

    def test_no_handler_no_error(self):
        router = MRLRouter()
        results = router.route("empty_channel", {"data": "x"})
        assert results == []

    def test_broadcast(self):
        router = MRLRouter()
        calls: dict[str, int] = {"a": 0, "b": 0}
        router.register("a", lambda ch, pkt: calls.__setitem__("a", calls["a"] + 1))
        router.register("b", lambda ch, pkt: calls.__setitem__("b", calls["b"] + 1))
        router.broadcast({"data": "x"})
        assert calls["a"] == 1
        assert calls["b"] == 1

    def test_jump(self):
        router = MRLRouter()
        landed: list[str] = []
        router.register("target", lambda ch, pkt: landed.append(ch))
        router.jump("source", "target", {"data": "x"})
        assert landed == ["target"]

    def test_multicast(self):
        router = MRLRouter()
        hits: list[str] = []
        router.register("x", lambda ch, pkt: hits.append("x"))
        router.register("y", lambda ch, pkt: hits.append("y"))
        router.register("z", lambda ch, pkt: hits.append("z"))
        router.multicast(["x", "z"], {"data": "y"})
        assert "x" in hits
        assert "z" in hits
        assert "y" not in hits

    def test_status(self):
        router = MRLRouter()
        router.register("ch1", lambda c, p: None)
        s = router.status()
        assert "ch1" in s["channels"]


# ===========================================================================
# Verifier tests (content hash only — crypto tests require package)
# ===========================================================================

class TestVerifier:
    def test_content_hash_str(self):
        h = content_hash("hello")
        assert h.startswith("sha256:")
        assert len(h) == 7 + 64  # "sha256:" + 64 hex chars

    def test_content_hash_deterministic(self):
        assert content_hash("mrl") == content_hash("mrl")

    def test_content_hash_dict(self):
        h1 = content_hash({"a": 1, "b": 2})
        h2 = content_hash({"b": 2, "a": 1})
        assert h1 == h2  # canonical JSON (sorted keys)

    @pytest.mark.skipif(not _CRYPTO_AVAILABLE, reason="cryptography not installed")
    def test_sign_verify_round_trip(self, tmp_path):
        from core.MRL_verifier import sign, verify, generate_keypair
        priv, pub = generate_keypair(identity_dir=tmp_path)
        payload = "test particle payload"
        sig = sign(payload, private_key_path=priv)
        assert verify(payload, sig, public_key_path=pub)

    @pytest.mark.skipif(not _CRYPTO_AVAILABLE, reason="cryptography not installed")
    def test_verify_fails_tampered(self, tmp_path):
        from core.MRL_verifier import sign, verify, generate_keypair
        priv, pub = generate_keypair(identity_dir=tmp_path)
        sig = sign("original", private_key_path=priv)
        assert not verify("tampered", sig, public_key_path=pub)

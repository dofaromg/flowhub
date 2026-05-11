"""
MRL_relay_api.py — HTTP relay station API (改自 flowagent_api_server.py)

origin_signature : MrLiouWord
version          : 1.0
created_at       : 2026-05-11
source           : FlowAgent.Runtime v46 flowagent_api_server.py + MRL_RelayStation v0.1
law              : LAW-2 ADDITIVE_RESOLUTION

Endpoints:
  GET  /              → health check
  POST /encode        → text → Fluin (LOD: q4 default)
  POST /decode        → Fluin → text
  POST /encode_lod    → text → Fluin at chosen LOD
  POST /sign          → sign a payload
  POST /verify        → verify a signature
  GET  /dict/stats    → particle store statistics
  GET  /dict/search   → search particles

Requires: flask  (pip install flask)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add relay-station root to path so relative imports work when run directly
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

try:
    from flask import Flask, jsonify, request, Response
    _FLASK_AVAILABLE = True
except ImportError:
    _FLASK_AVAILABLE = False

from core.MRL_translator import encode, decode, LOD_LEVELS, check_syntax, check_dict
from core.MRL_verifier import sign, verify, content_hash, keypair_exists, _CRYPTO_AVAILABLE
from core.MRL_aggregator import MRLAggregator

_DICT_PATH = _HERE / "dictionary" / "Fluin.Dict.Base.json"

# ---------------------------------------------------------------------------
# Pre-load aggregator with base dictionary
# ---------------------------------------------------------------------------

_agg = MRLAggregator()
if _DICT_PATH.exists():
    _agg.absorb_file(_DICT_PATH, source="Fluin.Dict.Base.json")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> "Flask":
    if not _FLASK_AVAILABLE:
        raise RuntimeError("Flask is required. Install it with: pip install flask")

    app = Flask(__name__)

    # ----------------------------------------------------------------
    # Health
    # ----------------------------------------------------------------

    @app.get("/")
    def health() -> Response:
        return jsonify({
            "status": "ok",
            "service": "MRL_RelayStation",
            "version": "1.0",
            "origin_signature": "MrLiouWord",
            "endpoints": [
                "POST /encode",
                "POST /decode",
                "POST /encode_lod",
                "POST /sign",
                "POST /verify",
                "GET  /dict/stats",
                "GET  /dict/search?q=<query>&lod=<lod>",
            ],
            "crypto_available": _CRYPTO_AVAILABLE,
            "dict_particles": _agg.stats().get("total_particles", 0),
        })

    # ----------------------------------------------------------------
    # Encode  (text → Fluin)
    # ----------------------------------------------------------------

    @app.post("/encode")
    def api_encode() -> Response:
        body = request.get_json(silent=True) or {}
        text = body.get("text", "")
        if not text:
            return jsonify({"error": "missing 'text' field"}), 400
        lod = body.get("lod", "q4")
        if lod not in LOD_LEVELS:
            return jsonify({"error": f"lod must be one of {LOD_LEVELS}"}), 400
        result = encode(text, lod=lod, dict_path=_DICT_PATH)
        return jsonify({
            "input": text,
            "fltnz": result,
            "lod": lod,
        })

    # ----------------------------------------------------------------
    # Decode  (Fluin → text)
    # ----------------------------------------------------------------

    @app.post("/decode")
    def api_decode() -> Response:
        body = request.get_json(silent=True) or {}
        fltnz = body.get("fltnz", "")
        if not fltnz:
            return jsonify({"error": "missing 'fltnz' field"}), 400
        lod = body.get("lod", "q4")
        lang = body.get("lang", "en")
        if lod not in LOD_LEVELS:
            return jsonify({"error": f"lod must be one of {LOD_LEVELS}"}), 400
        result = decode(fltnz, lod=lod, lang=lang, dict_path=_DICT_PATH)
        return jsonify({
            "input": fltnz,
            "text": result,
            "lod": lod,
            "lang": lang,
        })

    # ----------------------------------------------------------------
    # Encode at multiple LOD levels simultaneously
    # ----------------------------------------------------------------

    @app.post("/encode_lod")
    def api_encode_lod() -> Response:
        body = request.get_json(silent=True) or {}
        text = body.get("text", "")
        if not text:
            return jsonify({"error": "missing 'text' field"}), 400
        fltnz = encode(text, lod="q4", dict_path=_DICT_PATH)
        # decode back at each LOD level
        lod_results: dict[str, str] = {}
        for lod in LOD_LEVELS:
            lod_results[lod] = decode(fltnz, lod=lod, lang="en", dict_path=_DICT_PATH)
        return jsonify({
            "input": text,
            "fltnz": fltnz,
            "decoded_lod": lod_results,
            "zh": decode(fltnz, lod="q4", lang="zh", dict_path=_DICT_PATH),
        })

    # ----------------------------------------------------------------
    # Sign
    # ----------------------------------------------------------------

    @app.post("/sign")
    def api_sign() -> Response:
        if not _CRYPTO_AVAILABLE:
            return jsonify({"error": "cryptography package not installed"}), 503
        body = request.get_json(silent=True) or {}
        payload = body.get("payload")
        if payload is None:
            return jsonify({"error": "missing 'payload' field"}), 400
        if not keypair_exists():
            return jsonify({"error": "No identity keypair found. Run MRL_verifier keygen first."}), 503
        try:
            sig = sign(payload)
            chash = content_hash(payload)
            return jsonify({"signature": sig, "content_hash": chash})
        except Exception:  # noqa: BLE001
            return jsonify({"error": "signing failed"}), 500

    # ----------------------------------------------------------------
    # Verify
    # ----------------------------------------------------------------

    @app.post("/verify")
    def api_verify() -> Response:
        if not _CRYPTO_AVAILABLE:
            return jsonify({"error": "cryptography package not installed"}), 503
        body = request.get_json(silent=True) or {}
        payload = body.get("payload")
        signature = body.get("signature")
        if payload is None or not signature:
            return jsonify({"error": "missing 'payload' or 'signature' field"}), 400
        if not keypair_exists():
            return jsonify({"error": "No identity keypair found."}), 503
        try:
            ok = verify(payload, signature)
            return jsonify({"valid": ok})
        except Exception:  # noqa: BLE001
            return jsonify({"error": "verification failed"}), 500

    # ----------------------------------------------------------------
    # Dictionary stats
    # ----------------------------------------------------------------

    @app.get("/dict/stats")
    def api_dict_stats() -> Response:
        return jsonify(_agg.stats())

    # ----------------------------------------------------------------
    # Dictionary search
    # ----------------------------------------------------------------

    @app.get("/dict/search")
    def api_dict_search() -> Response:
        q = request.args.get("q", "")
        lod = request.args.get("lod", "q8")
        if not q:
            return jsonify({"error": "missing query param 'q'"}), 400
        if lod not in LOD_LEVELS:
            return jsonify({"error": f"lod must be one of {LOD_LEVELS}"}), 400
        results = _agg.search(q)
        return jsonify({
            "query": q,
            "lod": lod,
            "count": len(results),
            "results": [
                {
                    "key": r.key,
                    "concept": r.entry.get("concept"),
                    "zh": r.entry.get("zh"),
                    "layer": r.entry.get("layer"),
                    lod: r.entry.get(lod),
                }
                for r in results
            ],
        })

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MRL Relay API Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app()
    print(f"🚀 MRL_RelayStation API  →  http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=args.debug)

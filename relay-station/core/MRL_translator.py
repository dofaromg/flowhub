"""
MRL_translator.py — Fluin encode / decode / expand / validate  (LOD-aware)

origin_signature : MrLiouWord
version          : 1.0
created_at       : 2026-05-11
source           : FlowAgent.Runtime v46 + MRL_RelayStation v0.1
law              : LAW-2 ADDITIVE_RESOLUTION

LOD levels (analogous to LLM quantization):
  symbol  — single/two-char abbreviation    (~1 token)
  q4      — 1-3 word essence                (~3 tokens)
  q8      — 5-10 word concise phrase        (~8 tokens)
  fp16    — full definition sentence        (~20 tokens)
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# Dictionary loader
# ---------------------------------------------------------------------------

_DEFAULT_DICT = Path(__file__).parent.parent / "dictionary" / "Fluin.Dict.Base.json"

LOD_LEVELS = ("symbol", "q4", "q8", "fp16")


def load_dict(path: Path | None = None) -> dict:
    """Load and return the raw Fluin dictionary JSON."""
    p = Path(path) if path else _DEFAULT_DICT
    with p.open(encoding="utf-8") as fh:
        data = json.load(fh)
    # strip _meta key so only fl-NNN entries remain
    return {k: v for k, v in data.items() if k.startswith("fl-")}


def build_indexes(d: dict) -> tuple[dict, dict, dict]:
    """
    Returns:
        forward   : fl-NNN  → entry dict
        by_concept: concept → fl-NNN
        by_zh     : zh      → fl-NNN
    """
    forward: dict[str, dict] = d
    by_concept: dict[str, str] = {}
    by_zh: dict[str, str] = {}
    for key, entry in d.items():
        if isinstance(entry, dict):
            by_concept[entry.get("concept", "").lower()] = key
            zh = entry.get("zh", "")
            if zh:
                by_zh[zh] = key
    return forward, by_concept, by_zh


# Module-level singletons (lazy-loaded on first use)
_raw: dict | None = None
_forward: dict | None = None
_by_concept: dict | None = None
_by_zh: dict | None = None


def _ensure_loaded(dict_path: Path | None = None) -> None:
    global _raw, _forward, _by_concept, _by_zh
    if _raw is None or dict_path is not None:
        _raw = load_dict(dict_path)
        _forward, _by_concept, _by_zh = build_indexes(_raw)


# ---------------------------------------------------------------------------
# Encoder  (human text → Fluin particle sequence)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z\u4e00-\u9fff]+")


def encode(text: str, lod: str = "q4", dict_path: Path | None = None) -> str:
    """
    Encode a human sentence into a Fluin particle sequence string.

    Unknown tokens are kept as-is (prefixed with '?') so information is not lost.
    Returns a space-separated line of fl-NNN tokens.

    Args:
        text:      Input text (Chinese or English).
        lod:       LOD level to use for display in verbose mode (not used in
                   token output — the output is always fl-NNN keys).
        dict_path: Override dictionary path.
    """
    if lod not in LOD_LEVELS:
        raise ValueError(f"lod must be one of {LOD_LEVELS}, got {lod!r}")
    _ensure_loaded(dict_path)
    tokens = _TOKEN_RE.findall(text.lower())
    particles: list[str] = []
    for tok in tokens:
        key = _by_concept.get(tok) or _by_zh.get(tok)  # type: ignore[index]
        if key:
            particles.append(key)
        else:
            particles.append(f"?{tok}")
    return " ".join(particles)


# ---------------------------------------------------------------------------
# Decoder  (Fluin particle sequence → human text at chosen LOD)
# ---------------------------------------------------------------------------

def decode(fltnz: str, lod: str = "q4", lang: str = "en",
           dict_path: Path | None = None) -> str:
    """
    Decode a Fluin particle sequence back to human text.

    Args:
        fltnz:     Space/newline-separated fl-NNN keys (a .fltnz file or line).
        lod:       LOD level: symbol | q4 | q8 | fp16.
        lang:      Output language — 'en' uses the chosen lod field; 'zh' uses zh field.
        dict_path: Override dictionary path.

    Returns:
        Decoded human-readable string.
    """
    if lod not in LOD_LEVELS:
        raise ValueError(f"lod must be one of {LOD_LEVELS}, got {lod!r}")
    _ensure_loaded(dict_path)
    parts: list[str] = []
    for token in fltnz.split():
        if token.startswith("?"):
            parts.append(token[1:])  # unknown token — restore raw
            continue
        entry = _forward.get(token)  # type: ignore[index]
        if entry is None:
            parts.append(f"[{token}?]")
            continue
        if lang == "zh":
            parts.append(entry.get("zh", entry.get("concept", token)))
        else:
            parts.append(entry.get(lod, entry.get("concept", token)))
    return " ".join(parts)


def decode_file(path: Path, lod: str = "q4", lang: str = "en",
                dict_path: Path | None = None) -> str:
    """Decode an entire .fltnz file preserving blank-line paragraph breaks."""
    text = Path(path).read_text(encoding="utf-8")
    paragraphs: list[str] = []
    for para in text.split("\n\n"):
        lines = [
            decode(line, lod=lod, lang=lang, dict_path=dict_path)
            for line in para.splitlines()
            if line.strip()
        ]
        paragraphs.append("\n".join(lines))
    return "\n\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Expander  (random .fltnz generator)
# ---------------------------------------------------------------------------

def expand(n_lines: int = 5, particles_per_line: int = 4,
           seed: int | None = None, dict_path: Path | None = None) -> str:
    """
    Generate random Fluin particle sequences as a .fltnz string.

    Args:
        n_lines:           Number of utterance lines to generate.
        particles_per_line: Particles per line.
        seed:              Random seed for reproducibility.
        dict_path:         Override dictionary path.

    Returns:
        Multi-line .fltnz string.
    """
    _ensure_loaded(dict_path)
    rng = random.Random(seed)
    keys = list(_forward.keys())  # type: ignore[index]
    lines: list[str] = []
    for _ in range(n_lines):
        chosen = rng.sample(keys, min(particles_per_line, len(keys)))
        lines.append(" ".join(chosen))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Syntax checker  (validate a .fltnz file or string)
# ---------------------------------------------------------------------------

_FLUIN_KEY_RE = re.compile(r"^fl-\d{3}$")
_UNKNOWN_RE = re.compile(r"^\?[A-Za-z\u4e00-\u9fff]+$")


def check_syntax(fltnz: str, dict_path: Path | None = None) -> list[dict]:
    """
    Validate a .fltnz string line by line.

    Returns a list of result dicts:
        { "line": int, "token": str, "status": "OK"|"UNKNOWN"|"INVALID", "message": str }
    """
    _ensure_loaded(dict_path)
    results: list[dict] = []
    for lineno, raw_line in enumerate(fltnz.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        for token in line.split():
            if _UNKNOWN_RE.match(token):
                results.append({
                    "line": lineno,
                    "token": token,
                    "status": "UNKNOWN",
                    "message": f"Passthrough unknown token '{token[1:]}'",
                })
            elif _FLUIN_KEY_RE.match(token):
                if token in _forward:  # type: ignore[operator]
                    results.append({
                        "line": lineno,
                        "token": token,
                        "status": "OK",
                        "message": f"→ {_forward[token].get('concept', '?')}",  # type: ignore[index]
                    })
                else:
                    results.append({
                        "line": lineno,
                        "token": token,
                        "status": "INVALID",
                        "message": f"Key '{token}' not found in dictionary",
                    })
            else:
                results.append({
                    "line": lineno,
                    "token": token,
                    "status": "INVALID",
                    "message": f"Malformed token '{token}' (expected fl-NNN or ?word)",
                })
    return results


def check_syntax_file(path: Path, dict_path: Path | None = None) -> list[dict]:
    """Validate a .fltnz file. Convenience wrapper around check_syntax."""
    return check_syntax(Path(path).read_text(encoding="utf-8"), dict_path=dict_path)


def print_check_report(results: list[dict]) -> None:
    """Pretty-print a syntax check report to stdout."""
    ok = sum(1 for r in results if r["status"] == "OK")
    warn = sum(1 for r in results if r["status"] == "UNKNOWN")
    err = sum(1 for r in results if r["status"] == "INVALID")
    for r in results:
        icon = {"OK": "✅", "UNKNOWN": "⚠️", "INVALID": "❌"}.get(r["status"], "?")
        print(f"  line {r['line']:>4}  {icon}  {r['token']:<12}  {r['message']}")
    print(f"\n  Total: {ok} OK  |  {warn} unknown  |  {err} invalid")


# ---------------------------------------------------------------------------
# Dictionary health check
# ---------------------------------------------------------------------------

def check_dict(dict_path: Path | None = None) -> None:
    """Validate that every entry in the dictionary has the required fields."""
    _ensure_loaded(dict_path)
    required = {"concept", "zh", "layer", "symbol", "q4", "q8", "fp16", "origin_signature"}
    errors: list[str] = []
    for key, entry in _forward.items():  # type: ignore[union-attr]
        missing = required - set(entry.keys())
        if missing:
            errors.append(f"  {key}: missing fields {missing}")
    if errors:
        print("❌ Dictionary validation FAILED:")
        for e in errors:
            print(e)
    else:
        print(f"✅ Dictionary OK — {len(_forward)} entries, all fields present.")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="MRL Translator — Fluin encode/decode/expand/check"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # encode
    p_enc = sub.add_parser("encode", help="Encode text to Fluin")
    p_enc.add_argument("text", help="Input text")
    p_enc.add_argument("--lod", default="q4", choices=LOD_LEVELS)
    p_enc.add_argument("--dict", default=None)

    # decode
    p_dec = sub.add_parser("decode", help="Decode Fluin to text")
    p_dec.add_argument("fltnz", help="Fluin particle sequence")
    p_dec.add_argument("--lod", default="q4", choices=LOD_LEVELS)
    p_dec.add_argument("--lang", default="en", choices=["en", "zh"])
    p_dec.add_argument("--dict", default=None)

    # expand
    p_exp = sub.add_parser("expand", help="Generate random Fluin sequences")
    p_exp.add_argument("--lines", type=int, default=5)
    p_exp.add_argument("--per-line", type=int, default=4, dest="per_line")
    p_exp.add_argument("--seed", type=int, default=None)
    p_exp.add_argument("--dict", default=None)

    # check
    p_chk = sub.add_parser("check", help="Validate a Fluin sequence")
    p_chk.add_argument("fltnz", help="Fluin sequence or @path to .fltnz file")
    p_chk.add_argument("--dict", default=None)

    # check-dict
    p_cd = sub.add_parser("check-dict", help="Validate dictionary completeness")
    p_cd.add_argument("--dict", default=None)

    args = parser.parse_args()
    dp = Path(args.dict) if getattr(args, "dict", None) else None

    if args.cmd == "encode":
        print(encode(args.text, lod=args.lod, dict_path=dp))

    elif args.cmd == "decode":
        print(decode(args.fltnz, lod=args.lod, lang=args.lang, dict_path=dp))

    elif args.cmd == "expand":
        print(expand(n_lines=args.lines, particles_per_line=args.per_line,
                     seed=args.seed, dict_path=dp))

    elif args.cmd == "check":
        raw = args.fltnz
        if raw.startswith("@"):
            raw = Path(raw[1:]).read_text(encoding="utf-8")
        results = check_syntax(raw, dict_path=dp)
        print_check_report(results)
        if any(r["status"] == "INVALID" for r in results):
            sys.exit(1)

    elif args.cmd == "check-dict":
        check_dict(dict_path=dp)

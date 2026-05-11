"""
MRL_relay_console.py — CLI 總控台 (改自 flowagent_console.py)

origin_signature : MrLiouWord
version          : 1.0
created_at       : 2026-05-11
source           : FlowAgent.Runtime v46 flowagent_console.py + MRL_RelayStation v0.1
law              : LAW-2 ADDITIVE_RESOLUTION

12-function interactive console menu (terminal entry point for MRL_RelayStation).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from core.MRL_translator import (
    encode, decode, expand, check_syntax, check_dict,
    print_check_report, LOD_LEVELS, _ensure_loaded,
)
from core.MRL_aggregator import MRLAggregator
from core.MRL_verifier import (
    sign, verify, content_hash, generate_keypair, keypair_exists,
    _CRYPTO_AVAILABLE,
)

_DICT_PATH = _HERE / "dictionary" / "Fluin.Dict.Base.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sep(title: str = "") -> None:
    line = "─" * 56
    if title:
        print(f"\n{line}\n  {title}\n{line}")
    else:
        print(line)


def _ask(prompt: str, default: str = "") -> str:
    try:
        val = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    except (EOFError, KeyboardInterrupt):
        return default
    return val or default


# ---------------------------------------------------------------------------
# Menu actions (1–12)
# ---------------------------------------------------------------------------

def action_01_encode() -> None:
    _sep("1. Encode  text → Fluin")
    text = _ask("Input text")
    lod = _ask("LOD (symbol/q4/q8/fp16)", "q4")
    if lod not in LOD_LEVELS:
        print(f"  ❌ Unknown LOD '{lod}'. Using q4.")
        lod = "q4"
    result = encode(text, lod=lod, dict_path=_DICT_PATH)
    print(f"\n  Fluin: {result}")


def action_02_decode() -> None:
    _sep("2. Decode  Fluin → text")
    fltnz = _ask("Fluin sequence (e.g. fl-001 fl-002)")
    lod = _ask("LOD", "q4")
    lang = _ask("Language (en/zh)", "en")
    result = decode(fltnz, lod=lod, lang=lang, dict_path=_DICT_PATH)
    print(f"\n  Text: {result}")


def action_03_encode_lod() -> None:
    _sep("3. Encode at all LOD levels")
    text = _ask("Input text")
    fltnz = encode(text, lod="q4", dict_path=_DICT_PATH)
    print(f"\n  Fluin:   {fltnz}")
    for lod in LOD_LEVELS:
        print(f"  {lod:6}:  {decode(fltnz, lod=lod, lang='en', dict_path=_DICT_PATH)}")
    print(f"  {'zh':6}:  {decode(fltnz, lod='q4', lang='zh', dict_path=_DICT_PATH)}")


def action_04_expand() -> None:
    _sep("4. Expand  generate random Fluin sequences")
    try:
        n = int(_ask("Number of lines", "5"))
        per = int(_ask("Particles per line", "4"))
        seed_s = _ask("Random seed (blank = random)", "")
        seed = int(seed_s) if seed_s else None
    except ValueError:
        print("  ❌ Invalid number.")
        return
    result = expand(n_lines=n, particles_per_line=per, seed=seed, dict_path=_DICT_PATH)
    print(f"\n{result}")
    save = _ask("Save to file? (path or blank to skip)")
    if save:
        Path(save).write_text(result, encoding="utf-8")
        print(f"  ✅ Saved → {save}")


def action_05_check_syntax() -> None:
    _sep("5. Check syntax of a Fluin sequence")
    src = _ask("Fluin sequence or @path/to/file.fltnz")
    if src.startswith("@"):
        raw = Path(src[1:]).read_text(encoding="utf-8")
    else:
        raw = src
    results = check_syntax(raw, dict_path=_DICT_PATH)
    print()
    print_check_report(results)


def action_06_check_dict() -> None:
    _sep("6. Validate dictionary completeness")
    check_dict(dict_path=_DICT_PATH)


def action_07_absorb() -> None:
    _sep("7. Absorb dictionary file into particle store")
    path = _ask("Path to Fluin dict JSON", str(_DICT_PATH))
    source = _ask("Source label", path)
    agg = MRLAggregator()
    counts = agg.absorb_file(Path(path), source=source)
    print(f"\n  Result: {counts}")
    print(f"  Stats:  {json.dumps(agg.stats(), indent=4)}")
    out = _ask("Save merged manifest to file? (blank to skip)")
    if out:
        agg.save_manifest(Path(out))
        print(f"  ✅ Manifest saved → {out}")


def action_08_search() -> None:
    _sep("8. Search particle dictionary")
    query = _ask("Search query")
    lod = _ask("LOD", "q8")
    agg = MRLAggregator()
    agg.absorb_file(_DICT_PATH, source="base")
    results = agg.search(query)
    if not results:
        print("  No matches found.")
        return
    print(f"\n  Found {len(results)} match(es):\n")
    for r in results:
        lod_val = r.entry.get(lod, r.entry.get("concept", "?"))
        print(f"  {r.key}  {r.entry.get('concept','?'):15}  {r.entry.get('zh',''):6}  "
              f"[{r.entry.get('layer','?')}]  {lod_val}")


def action_09_sign() -> None:
    _sep("9. Sign payload  (ed25519)")
    if not _CRYPTO_AVAILABLE:
        print("  ❌ cryptography package not installed. Run: pip install cryptography")
        return
    if not keypair_exists():
        gen = _ask("No keypair found. Generate one? (y/n)", "y")
        if gen.lower() == "y":
            priv, pub = generate_keypair()
            print(f"  ✅ Generated: {priv}  {pub}")
        else:
            return
    payload = _ask("Payload to sign")
    sig = sign(payload)
    chash = content_hash(payload)
    print(f"\n  Signature:    {sig}")
    print(f"  ContentHash:  {chash}")


def action_10_verify() -> None:
    _sep("10. Verify signature  (ed25519)")
    if not _CRYPTO_AVAILABLE:
        print("  ❌ cryptography package not installed.")
        return
    payload = _ask("Original payload")
    sig = _ask("Base64 signature")
    ok = verify(payload, sig)
    print(f"\n  {'✅ Valid' if ok else '❌ Invalid'}")


def action_11_hash() -> None:
    _sep("11. Content hash  (SHA-256 CAS)")
    payload = _ask("Payload")
    print(f"\n  {content_hash(payload)}")


def action_12_start_api() -> None:
    _sep("12. Start HTTP API server")
    try:
        from MRL_relay_api import create_app  # type: ignore[import]
    except ImportError:
        print("  ❌ Flask not installed. Run: pip install flask")
        return
    host = _ask("Host", "127.0.0.1")
    port_s = _ask("Port", "8787")
    try:
        port = int(port_s)
    except ValueError:
        port = 8787
    print(f"\n  🚀 Starting MRL Relay API at http://{host}:{port}/  (Ctrl-C to stop)\n")
    app = create_app()
    app.run(host=host, port=port, debug=False)


# ---------------------------------------------------------------------------
# Menu dispatch table
# ---------------------------------------------------------------------------

MENU: dict[str, tuple[str, object]] = {
    "1":  ("Encode  text → Fluin", action_01_encode),
    "2":  ("Decode  Fluin → text", action_02_decode),
    "3":  ("Encode at all LOD levels", action_03_encode_lod),
    "4":  ("Expand  generate random Fluin", action_04_expand),
    "5":  ("Check syntax of Fluin sequence", action_05_check_syntax),
    "6":  ("Validate dictionary", action_06_check_dict),
    "7":  ("Absorb dictionary file", action_07_absorb),
    "8":  ("Search particle dictionary", action_08_search),
    "9":  ("Sign payload (ed25519)", action_09_sign),
    "10": ("Verify signature", action_10_verify),
    "11": ("Content hash (SHA-256)", action_11_hash),
    "12": ("Start HTTP API server", action_12_start_api),
}


def show_menu() -> None:
    _sep("MRL RelayStation Console  v1.0")
    for key, (label, _) in MENU.items():
        print(f"  {key:>2}.  {label}")
    _sep()
    print("   q.  Quit")


def run_console() -> None:
    _ensure_loaded(_DICT_PATH)
    while True:
        print()
        show_menu()
        choice = _ask("Select").strip()
        if choice.lower() in ("q", "quit", "exit"):
            print("\n  🌙 Goodbye — MRL_RelayStation offline.\n")
            break
        action_fn = MENU.get(choice, (None, None))[1]
        if action_fn is None:
            print(f"\n  ❓ Unknown option '{choice}'. Try again.")
            continue
        try:
            action_fn()  # type: ignore[call-arg]
        except KeyboardInterrupt:
            print("\n  (interrupted)")
        except Exception as exc:  # noqa: BLE001
            print(f"\n  ❌ Error: {exc}")


if __name__ == "__main__":
    run_console()

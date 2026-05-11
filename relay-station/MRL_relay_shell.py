"""
MRL_relay_shell.py — Interactive Fluin Shell (去模擬化版，改自 flowshell_cli_core.py)

origin_signature : MrLiouWord
version          : 1.0
created_at       : 2026-05-11
source           : FlowAgent.Runtime v46 flowshell_cli_core.py + MRL_RelayStation v0.1
law              : LAW-2 ADDITIVE_RESOLUTION

Real commands (不再是模擬器):
  encode <text>            — encode text to Fluin (fl-001 fl-002 ...)
  decode <fltnz>           — decode Fluin to text
  jump <channel>           — switch active channel (register and route)
  echo <text>              — encode + immediately decode (round-trip echo)
  pulse                    — show current tick / time pulse
  sync                     — sync state from dictionary store
  persona <name>           — set current persona label
  seed <n>                 — set random seed for expander
  expand [n]               — generate n random Fluin lines
  check <fltnz>            — syntax check a sequence
  hash <text>              — compute SHA-256 content hash
  stats                    — show particle store stats
  help                     — list commands
  exit / quit              — exit shell
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from core.MRL_translator import (
    encode, decode, expand, check_syntax, print_check_report,
    LOD_LEVELS, _ensure_loaded,
)
from core.MRL_aggregator import MRLAggregator
from core.MRL_router import MRLRouter
from core.MRL_verifier import content_hash

_DICT_PATH = _HERE / "dictionary" / "Fluin.Dict.Base.json"

# ---------------------------------------------------------------------------
# Shell state
# ---------------------------------------------------------------------------

class ShellState:
    def __init__(self) -> None:
        self.persona: str = "default"
        self.channel: str = "main"
        self.seed: int | None = None
        self.lod: str = "q4"
        self.lang: str = "en"
        self.tick: int = 0
        self.agg: MRLAggregator = MRLAggregator()
        self.router: MRLRouter = MRLRouter()
        # load base dictionary into aggregator
        if _DICT_PATH.exists():
            self.agg.absorb_file(_DICT_PATH, source="Fluin.Dict.Base.json")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_encode(args: list[str], state: ShellState) -> str:
    text = " ".join(args)
    if not text:
        return "Usage: encode <text>"
    result = encode(text, lod=state.lod, dict_path=_DICT_PATH)
    return f"  Fluin: {result}"


def cmd_decode(args: list[str], state: ShellState) -> str:
    fltnz = " ".join(args)
    if not fltnz:
        return "Usage: decode <fl-NNN fl-NNN ...>"
    result = decode(fltnz, lod=state.lod, lang=state.lang, dict_path=_DICT_PATH)
    return f"  Text:  {result}"


def cmd_echo(args: list[str], state: ShellState) -> str:
    text = " ".join(args)
    if not text:
        return "Usage: echo <text>"
    fltnz = encode(text, lod=state.lod, dict_path=_DICT_PATH)
    back = decode(fltnz, lod=state.lod, lang=state.lang, dict_path=_DICT_PATH)
    return f"  Fluin: {fltnz}\n  Echo:  {back}"


def cmd_jump(args: list[str], state: ShellState) -> str:
    if not args:
        return "Usage: jump <channel>"
    prev = state.channel
    state.channel = args[0]
    # register a no-op handler for the new channel if none exists
    if state.router.handler_count(state.channel) == 0:
        state.router.register(state.channel, lambda ch, pkt: None)
    return f"  JUMP  {prev} → {state.channel}"


def cmd_pulse(args: list[str], state: ShellState) -> str:
    state.tick += 1
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return f"  PULSE  tick={state.tick}  channel={state.channel}  ts={ts}"


def cmd_sync(args: list[str], state: ShellState) -> str:
    if _DICT_PATH.exists():
        counts = state.agg.absorb_file(_DICT_PATH, source="Fluin.Dict.Base.json")
        stats = state.agg.stats()
        return (f"  SYNC   particles={stats['total_particles']}"
                f"  absorbed={counts['absorbed']}  dup={counts['duplicate']}")
    return "  ⚠️  Dictionary file not found."


def cmd_persona(args: list[str], state: ShellState) -> str:
    if not args:
        return f"  Persona: {state.persona}"
    state.persona = " ".join(args)
    return f"  Persona set → {state.persona}"


def cmd_seed(args: list[str], state: ShellState) -> str:
    if not args:
        return f"  Seed: {state.seed}"
    try:
        state.seed = int(args[0])
        return f"  Seed set → {state.seed}"
    except ValueError:
        return "  ❌ Seed must be an integer."


def cmd_expand(args: list[str], state: ShellState) -> str:
    n = 5
    if args:
        try:
            n = int(args[0])
        except ValueError:
            return "Usage: expand [n]"
    result = expand(n_lines=n, particles_per_line=4, seed=state.seed,
                    dict_path=_DICT_PATH)
    return result


def cmd_check(args: list[str], state: ShellState) -> str:
    fltnz = " ".join(args)
    if not fltnz:
        return "Usage: check <fl-NNN fl-NNN ...>"
    results = check_syntax(fltnz, dict_path=_DICT_PATH)
    lines: list[str] = []
    ok = sum(1 for r in results if r["status"] == "OK")
    err = sum(1 for r in results if r["status"] == "INVALID")
    for r in results:
        icon = {"OK": "✅", "UNKNOWN": "⚠️", "INVALID": "❌"}.get(r["status"], "?")
        lines.append(f"  {icon}  {r['token']:<12}  {r['message']}")
    lines.append(f"  ─── {ok} OK | {err} invalid")
    return "\n".join(lines)


def cmd_hash(args: list[str], state: ShellState) -> str:
    text = " ".join(args)
    if not text:
        return "Usage: hash <text>"
    return f"  {content_hash(text)}"


def cmd_lod(args: list[str], state: ShellState) -> str:
    if not args:
        return f"  LOD: {state.lod}  (options: {LOD_LEVELS})"
    if args[0] not in LOD_LEVELS:
        return f"  ❌ LOD must be one of {LOD_LEVELS}"
    state.lod = args[0]
    return f"  LOD set → {state.lod}"


def cmd_lang(args: list[str], state: ShellState) -> str:
    if not args:
        return f"  Lang: {state.lang}"
    if args[0] not in ("en", "zh"):
        return "  ❌ lang must be 'en' or 'zh'"
    state.lang = args[0]
    return f"  Lang set → {state.lang}"


def cmd_stats(args: list[str], state: ShellState) -> str:
    import json
    return "  " + json.dumps(state.agg.stats(), indent=4).replace("\n", "\n  ")


def cmd_help(args: list[str], state: ShellState) -> str:
    return """\
  Commands:
    encode <text>      — text → Fluin
    decode <fltnz>     — Fluin → text
    echo <text>        — encode then decode (round-trip)
    expand [n]         — generate n random Fluin lines
    check <fltnz>      — syntax check
    hash <text>        — SHA-256 content hash
    jump <channel>     — switch active channel
    pulse              — show tick and timestamp
    sync               — reload dictionary
    persona [name]     — get/set persona label
    seed [n]           — get/set random seed
    lod [level]        — get/set LOD (symbol/q4/q8/fp16)
    lang [en|zh]       — get/set output language
    stats              — particle store statistics
    help               — this message
    exit / quit        — exit shell"""


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

COMMANDS: dict[str, object] = {
    "encode":  cmd_encode,
    "decode":  cmd_decode,
    "echo":    cmd_echo,
    "expand":  cmd_expand,
    "check":   cmd_check,
    "hash":    cmd_hash,
    "jump":    cmd_jump,
    "pulse":   cmd_pulse,
    "sync":    cmd_sync,
    "persona": cmd_persona,
    "seed":    cmd_seed,
    "lod":     cmd_lod,
    "lang":    cmd_lang,
    "stats":   cmd_stats,
    "help":    cmd_help,
}


# ---------------------------------------------------------------------------
# Shell loop
# ---------------------------------------------------------------------------

def run_shell(welcome: bool = True) -> None:
    _ensure_loaded(_DICT_PATH)
    state = ShellState()

    if welcome:
        print("━" * 56)
        print("  MRL Relay Shell  v1.0  |  origin_signature: MrLiouWord")
        print(f"  Dict: {state.agg.stats()['total_particles']} particles loaded")
        print("  Type 'help' for commands, 'exit' to quit.")
        print("━" * 56)

    while True:
        try:
            line = input(f"\n  [{state.persona}@{state.channel}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  (exit)")
            break

        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("exit", "quit"):
            print("  🌙 MRL Shell offline.")
            break

        handler = COMMANDS.get(cmd)
        if handler is None:
            print(f"  ❓ Unknown command '{cmd}'. Type 'help'.")
            continue

        try:
            output = handler(args, state)  # type: ignore[call-arg]
            if output:
                print(output)
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ Error: {exc}")


if __name__ == "__main__":
    run_shell()

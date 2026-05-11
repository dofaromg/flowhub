# MRL RelayStation v0.1

```
origin_signature : MrLiouWord
version          : 1.0
created_at       : 2026-05-11
law              : LAW-2 ADDITIVE_RESOLUTION (不刪原檔,只複製)
source           : FlowAgent.Runtime v46 喚醒 + ollama 蒸餾 S1-S5 注入
```

> 「母體不是空殼。母體裡早寫好了『街口』。  
>  我們要做的不是發明，是回去把它喚醒，並用 ollama 蒸餾的設計模式注入。」  
> — LAW-2：怎麼過去就怎麼回來。

---

## 目錄結構 / Directory Layout

```
relay-station/
├── core/
│   ├── MRL_translator.py    # 翻譯機: encode / decode / expand / check (LOD-aware)
│   ├── MRL_verifier.py      # ed25519 sign / verify / content-hash (CAS)
│   ├── MRL_router.py        # 頻道路由器: unicast / broadcast / multicast / jump
│   └── MRL_aggregator.py    # 多源粒子聚合器 (CAS dedup + provenance)
├── adapters_in/             # (Phase 4) 外部 → MRL 協議適配器
├── adapters_out/            # (Phase 4) MRL → 外部 協議適配器
├── dictionary/
│   ├── Fluin.Dict.Base.json # 100 條粒子字典 (fl-001 ~ fl-100) + LOD metadata
│   └── Fluin.Structure.md   # 字典綱要與命名規範
├── identity/                # ed25519 keypair (id_ed25519 / id_ed25519.pub)
├── tests/
│   └── test_relay_station.py  # 40 unit tests (pytest)
├── MRL_relay_api.py         # HTTP 街口 (Flask, port 8787)
├── MRL_relay_console.py     # CLI 12-功能總控台
├── MRL_relay_shell.py       # 互動式 Fluin Shell (真實版，非模擬器)
└── requirements.txt
```

---

## 安裝 / Installation

```bash
pip install flask cryptography   # optional: API server + crypto signatures
pip install pytest               # for running tests
```

---

## 快速開始 / Quick Start

### 1. 翻譯機 CLI (Translator)

```bash
cd relay-station

# Encode text → Fluin
python -m core.MRL_translator encode "system flow memory"
# → fl-001 fl-002 fl-007

# Decode Fluin → text at q8 LOD
python -m core.MRL_translator decode "fl-001 fl-002 fl-007" --lod q8
# → core organizing entity  directional movement of particles  persistent state storage unit

# Decode in Chinese
python -m core.MRL_translator decode "fl-001 fl-002" --lang zh
# → 系統 流

# Expand (generate random Fluin sequences)
python -m core.MRL_translator expand --lines 5 --per-line 3

# Syntax check
python -m core.MRL_translator check "fl-001 fl-999 ?unknown"

# Validate dictionary completeness
python -m core.MRL_translator check-dict
```

### 2. Interactive Shell

```bash
python relay-station/MRL_relay_shell.py
```

Shell commands:
| Command | Description |
|---------|-------------|
| `encode <text>` | Text → Fluin |
| `decode <fl-NNN ...>` | Fluin → text |
| `echo <text>` | Round-trip encode then decode |
| `expand [n]` | Generate n random Fluin lines |
| `check <fltnz>` | Syntax check |
| `jump <channel>` | Switch active channel (fl-100) |
| `pulse` | Show tick + timestamp (fl-008) |
| `sync` | Reload dictionary (fl-009) |
| `lod [level]` | Get/set LOD (symbol/q4/q8/fp16) |
| `lang [en\|zh]` | Get/set output language |
| `persona [name]` | Get/set persona label (fl-006) |
| `stats` | Particle store statistics |
| `hash <text>` | SHA-256 content hash |
| `exit` | Exit shell |

### 3. HTTP API Server

```bash
python relay-station/MRL_relay_api.py --host 127.0.0.1 --port 8787
```

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| GET | `/` | — | Health check |
| POST | `/encode` | `{"text":"...", "lod":"q4"}` | Text → Fluin |
| POST | `/decode` | `{"fltnz":"...", "lod":"q8", "lang":"en"}` | Fluin → text |
| POST | `/encode_lod` | `{"text":"..."}` | Text → all LOD levels |
| POST | `/sign` | `{"payload":"..."}` | ed25519 sign |
| POST | `/verify` | `{"payload":"...", "signature":"..."}` | Verify signature |
| GET | `/dict/stats` | — | Particle store stats |
| GET | `/dict/search?q=system&lod=q8` | — | Search dictionary |

```bash
# Example: encode
curl -s -X POST http://127.0.0.1:8787/encode \
  -H 'Content-Type: application/json' \
  -d '{"text":"system flow","lod":"q8"}' | python -m json.tool

# Example: encode all LOD levels
curl -s -X POST http://127.0.0.1:8787/encode_lod \
  -H 'Content-Type: application/json' \
  -d '{"text":"particle distill"}' | python -m json.tool
```

### 4. CLI Console (12-function menu)

```bash
python relay-station/MRL_relay_console.py
```

### 5. Run Tests

```bash
cd relay-station && python -m pytest tests/test_relay_station.py -v
```

---

## 粒子字典 / Particle Dictionary

`dictionary/Fluin.Dict.Base.json` — 100 entries (fl-001 ~ fl-100)

### LOD Levels

| LOD | Description | Tokens |
|-----|-------------|--------|
| `symbol` | 1-2 char abbreviation | ~1 |
| `q4` | 1-3 word essence | ~3 |
| `q8` | 5-10 word phrase | ~8 |
| `fp16` | full definition sentence | ~20 |

### Layer Map

| Layer | Scope | Entry range |
|-------|-------|-------------|
| L0 | Base primitives | fl-001..010, fl-076..077 |
| L1 | Structure & topology | fl-011..020, fl-078 |
| L2 | Operations & process | fl-021..040, fl-079..092, fl-098 |
| L3 | Protocols & comms | fl-041..060, fl-099..100 |
| L4 | Meta & governance | fl-061..075, fl-093..097 |

### Sample Entry

```json
"fl-084": {
  "concept": "distill",
  "zh": "蒸餾",
  "layer": "L2",
  "symbol": "DS",
  "q4": "distill",
  "q8": "purify essence from source",
  "fp16": "The extraction and purification of essential particles from a complex source system.",
  "origin_signature": "MrLiouWord"
}
```

---

## Fluin Notation (.fltnz)

A `.fltnz` file is a plain-text sequence of `fl-NNN` keys:

```
fl-001 fl-002 fl-009
fl-006 fl-007 fl-008
fl-021 fl-054 fl-041
```

- One *utterance* per line (space-separated particles)
- Blank lines separate paragraphs
- Unknown tokens preserved as `?word` (LAW-2: additive)

---

## 建置狀態 / Build Status

| Component | Status | Notes |
|-----------|--------|-------|
| `Fluin.Dict.Base.json` | ✅ 100 entries | LOD + layer + origin |
| `MRL_translator.py` | ✅ encode/decode/expand/check | LOD-aware |
| `MRL_verifier.py` | ✅ ed25519 + SHA-256 CAS | requires `cryptography` |
| `MRL_router.py` | ✅ unicast/broadcast/multicast/jump | in-process |
| `MRL_aggregator.py` | ✅ CAS dedup + manifest | provenance tracking |
| `MRL_relay_api.py` | ✅ HTTP /encode /decode /sign /verify | requires `flask` |
| `MRL_relay_console.py` | ✅ 12-function menu | |
| `MRL_relay_shell.py` | ✅ real commands, not simulator | |
| Tests | ✅ 40/40 pass | |
| `adapters_in/` | ⏳ Phase 4 | ollama/openai/claude adapters |
| `adapters_out/` | ⏳ Phase 4 | particle → protocol |

---

## 下一步 / Next Tasks

| Task | Priority | Description |
|------|----------|-------------|
| TASK-M02 | P1 | LLM hook: dict miss → MRL_Inference (Qwen2.5-32B) fallback |
| TASK-M03 | P2 | Shell: connect jump/echo/pulse/sync to real mrl_particle DB |
| TASK-M04 | P3 | adapters_in/out: ollama / openai / claude / http protocol adapters |
| TASK-M05 | P4 | Integrate as mrl-platform v1/v2 translation layer |

---

*MRL_RelayStation v0.1 — origin_signature: MrLiouWord*

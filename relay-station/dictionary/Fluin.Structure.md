# Fluin.Structure — MRL Particle Dictionary Schema

origin_signature : MrLiouWord  
version          : 2.0  
created_at       : 2026-05-11  
source           : FlowAgent.Runtime v46 + MRL_RelayStation v0.1

---

## 1. Entry Format

Every entry in `Fluin.Dict.Base.json` follows this schema:

```json
{
  "fl-NNN": {
    "concept": "<English keyword>",
    "zh":      "<Traditional Chinese>",
    "layer":   "L0 | L1 | L2 | L3 | L4",
    "symbol":  "<1-2 char abbreviation>",
    "q4":      "<1-3 word essence>",
    "q8":      "<5-10 word concise phrase>",
    "fp16":    "<full definition sentence>",
    "origin_signature": "MrLiouWord"
  }
}
```

---

## 2. Layer Definitions

| Layer | Name | Description |
|-------|------|-------------|
| L0 | Primitives | Base system atoms: system, flow, seed, core, shell, persona, memory, pulse, sync, field, particle, atom |
| L1 | Structure | Topology and spatial organisation: node, channel, bridge, cluster, layer, topology, tree, mesh, hub, root, molecule |
| L2 | Operations | Processing actions: encode, decode, route, merge, split, inject, extract, transform, validate, compress, expand, spawn, absorb, emit, filter, aggregate, index, hash, sign, verify, store, retrieve, lock, unlock, snapshot, restore, distill, atomize, quantize, modulate, wave, amplitude, frequency, resonance, fusion |
| L3 | Protocols | Communication patterns: packet, manifest, chunk, handshake, session, heartbeat, ack, nack, broadcast, unicast, multicast, endpoint, adapter, relay, gateway, tunnel, queue, buffer, stream, batch, echo, jump |
| L4 | Meta / Governance | Laws and meta concepts: law, contract, identity, trust, authority, version, diff, patch, rollback, audit, intent, context, schema, tag, origin, inference, embedding, prompt, response, token |

---

## 3. LOD (Level of Detail) Levels

MRL uses quantized LOD analogous to LLM quantization:

| LOD | Description | Size |
|-----|-------------|------|
| `symbol` | Single character or 2-char abbreviation | ~1 token |
| `q4` | 1–3 word essence — lowest fidelity | ~3 tokens |
| `q8` | 5–10 word concise phrase — medium fidelity | ~8 tokens |
| `fp16` | Full definition sentence — highest fidelity | ~20 tokens |

Consumers choose the LOD appropriate to their bandwidth and reasoning depth.

---

## 4. Fluin Notation (`.fltnz`)

A `.fltnz` file is a sequence of Fluin particle references, one per line:

```
fl-001 fl-002 fl-009
fl-006 fl-007 fl-008
fl-021 fl-054 fl-041
```

Lines represent particle utterances (sentences).  
Whitespace separates particles within an utterance.  
Empty lines separate paragraphs.

---

## 5. Naming Convention

```
fl-NNN
│    │
│    └── 3-digit zero-padded sequence number
└────── "fl" = Fluin
```

Ranges:
- `fl-001` – `fl-010` : L0 Primitives (v1.0 original)
- `fl-011` – `fl-020` : L1 Structure
- `fl-021` – `fl-060` : L2 Operations
- `fl-041` – `fl-060` : L3 Protocols (overlapping L2 tail)
- `fl-061` – `fl-100` : L4 Meta / Governance + Extended concepts

---

## 6. Bidirectional Use

The dictionary supports both directions:

- **Encoder**: `concept → fl-NNN`  
  Look up by `.concept` field → return key.
- **Decoder**: `fl-NNN → concept/zh`  
  Look up by key → return `.concept` or `.zh`.

Reverse index is built at runtime by `MRL_translator.py`.

---

## 7. Extension Guidelines

When adding new entries:

1. Choose the appropriate layer (L0–L4).
2. Assign the next sequential `fl-NNN` key.
3. Fill all six fields: `concept`, `zh`, `layer`, `symbol`, `q4`, `q8`, `fp16`.
4. Set `origin_signature` to your identifier.
5. Validate with `MRL_translator.py --check-dict`.
